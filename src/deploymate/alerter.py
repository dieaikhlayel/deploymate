"""Alerting system for DeployMate."""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List, Optional

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from deploymate.config import AlertConfig
from deploymate.utils.logger import LoggerMixin


class AlerterError(Exception):
    """Custom exception for alerting errors."""
    pass


class AlertManager(LoggerMixin):
    """Manages alert notifications."""
    
    def __init__(self, alert_config: AlertConfig):
        """
        Initialize alert manager.
        
        Args:
            alert_config: Alert configuration
        """
        self.alert_config = alert_config
        self._slack_client: Optional[WebClient] = None
        
        # Initialize Slack client if configured
        if self.alert_config.slack.get('enabled', False):
            webhook_url = self.alert_config.slack.get('webhook_url')
            if webhook_url:
                self._slack_client = WebClient(token=webhook_url)
    
    def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "info",
        channels: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """
        Send alert to configured channels.
        
        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity (info, warning, error)
            channels: List of channels to use ('slack', 'email')
        
        Returns:
            Dictionary with channel statuses
        """
        if channels is None:
            # Use default channels based on severity
            channels = ['slack', 'email']
        
        results = {}
        
        if 'slack' in channels and self.alert_config.slack.get('enabled', False):
            results['slack'] = self._send_slack_alert(title, message, severity)
        
        if 'email' in channels and self.alert_config.email.get('enabled', False):
            results['email'] = self._send_email_alert(title, message, severity)
        
        return results
    
    def _send_slack_alert(self, title: str, message: str, severity: str) -> bool:
        """
        Send alert to Slack.
        
        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use webhook URL if available
            webhook_url = self.alert_config.slack.get('webhook_url')
            if webhook_url:
                color = self._get_severity_color(severity)
                
                payload = {
                    'attachments': [
                        {
                            'color': color,
                            'title': title,
                            'text': message,
                            'footer': 'DeployMate',
                        }
                    ]
                }
                
                response = requests.post(webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                
                self.logger.info(f"Slack alert sent: {title}")
                return True
            
            # Use Slack client if available
            if self._slack_client:
                channel = self.alert_config.slack.get('channel', '#general')
                username = self.alert_config.slack.get('username', 'DeployMate')
                icon_emoji = self.alert_config.slack.get('icon_emoji', ':rocket:')
                
                response = self._slack_client.chat_postMessage(
                    channel=channel,
                    text=f"*{title}*\n{message}",
                    username=username,
                    icon_emoji=icon_emoji,
                )
                
                self.logger.info(f"Slack alert sent: {title}")
                return True
            
            self.logger.warning("Slack is enabled but no webhook or token configured")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack alert: {e}")
            return False
    
    def _send_email_alert(self, title: str, message: str, severity: str) -> bool:
        """
        Send alert via email.
        
        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity
        
        Returns:
            True if successful, False otherwise
        """
        try:
            smtp_host = self.alert_config.email.get('smtp_host')
            smtp_port = self.alert_config.email.get('smtp_port', 587)
            smtp_username = self.alert_config.email.get('smtp_username')
            smtp_password = self.alert_config.email.get('smtp_password')
            from_address = self.alert_config.email.get('from_address', smtp_username)
            recipients = self.alert_config.email.get('recipients', [])
            
            if not all([smtp_host, smtp_username, smtp_password, recipients]):
                self.logger.warning("Email alerts enabled but not fully configured")
                return False
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = from_address
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"[DeployMate] [{severity.upper()}] {title}"
            
            # Add message body
            body = f"""
            <html>
            <body>
                <h2>{title}</h2>
                <p><strong>Severity:</strong> {severity}</p>
                <hr>
                <pre>{message}</pre>
                <hr>
                <p><em>Sent by DeployMate at {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=context)
                server.login(smtp_username, smtp_password)
                server.sendmail(from_address, recipients, msg.as_string())
            
            self.logger.info(f"Email alert sent to {len(recipients)} recipients")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")
            return False
    
    def _get_severity_color(self, severity: str) -> str:
        """
        Get color for Slack message based on severity.
        
        Args:
            severity: Alert severity
        
        Returns:
            Color hex code
        """
        colors = {
            'info': '#36a64f',  # Green
            'warning': '#ffcc00',  # Yellow
            'error': '#ff0000',  # Red
            'critical': '#8b0000',  # Dark red
        }
        
        return colors.get(severity.lower(), '#808080')
    
    def notify_deployment_started(
        self,
        deployment_name: str,
        server_name: str,
        version: str,
    ) -> None:
        """
        Send notification when deployment starts.
        
        Args:
            deployment_name: Name of the deployment
            server_name: Name of the server
            version: Version being deployed
        """
        title = f"Deployment Started: {deployment_name}"
        message = (
            f"Deployment '{deployment_name}' started\n"
            f"Server: {server_name}\n"
            f"Version: {version}"
        )
        
        rules = self.alert_config.notification_rules.get('on_deployment_start', [])
        self.send_alert(title, message, "info", rules)
    
    def notify_deployment_success(
        self,
        deployment_name: str,
        server_name: str,
        version: str,
        duration: float,
    ) -> None:
        """
        Send notification when deployment succeeds.
        
        Args:
            deployment_name: Name of the deployment
            server_name: Name of the server
            version: Deployed version
            duration: Deployment duration
        """
        title = f"Deployment Successful: {deployment_name}"
        message = (
            f"Deployment '{deployment_name}' completed successfully\n"
            f"Server: {server_name}\n"
            f"Version: {version}\n"
            f"Duration: {duration:.2f}s"
        )
        
        rules = self.alert_config.notification_rules.get('on_deployment_success', [])
        self.send_alert(title, message, "info", rules)
    
    def notify_deployment_failure(
        self,
        deployment_name: str,
        server_name: str,
        error_message: str,
    ) -> None:
        """
        Send notification when deployment fails.
        
        Args:
            deployment_name: Name of the deployment
            server_name: Name of the server
            error_message: Error message
        """
        title = f"Deployment Failed: {deployment_name}"
        message = (
            f"Deployment '{deployment_name}' failed\n"
            f"Server: {server_name}\n"
            f"Error: {error_message}"
        )
        
        rules = self.alert_config.notification_rules.get('on_deployment_failure', [])
        self.send_alert(title, message, "error", rules)
    
    def notify_health_check_failure(
        self,
        server_name: str,
        metrics: Dict[str, Any],
    ) -> None:
        """
        Send notification when health check fails.
        
        Args:
            server_name: Name of the server
            metrics: Server metrics
        """
        title = f"Health Check Failed: {server_name}"
        message = (
            f"Health check failed for server '{server_name}'\n"
            f"CPU Usage: {metrics.get('cpu_usage', 'N/A')}%\n"
            f"Memory Usage: {metrics.get('memory_usage', 'N/A')}%\n"
            f"Disk Usage: {metrics.get('disk_usage', 'N/A')}%\n"
            f"Status: {metrics.get('health_status', 'unknown')}"
        )
        
        rules = self.alert_config.notification_rules.get('on_health_check_failure', [])
        self.send_alert(title, message, "error", rules)
    
    def notify_rollback(
        self,
        deployment_name: str,
        server_name: str,
        from_version: str,
        to_version: str,
    ) -> None:
        """
        Send notification when rollback occurs.
        
        Args:
            deployment_name: Name of the deployment
            server_name: Name of the server
            from_version: Version rolled back from
            to_version: Version rolled back to
        """
        title = f"Rollback Performed: {deployment_name}"
        message = (
            f"Rollback performed for '{deployment_name}'\n"
            f"Server: {server_name}\n"
            f"From version: {from_version}\n"
            f"To version: {to_version}"
        )
        
        rules = self.alert_config.notification_rules.get('on_rollback', [])
        self.send_alert(title, message, "warning", rules)