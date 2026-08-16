"""Server monitoring for DeployMate."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import requests
from apscheduler.schedulers.background import BackgroundScheduler

from deploymate.config import ConfigManager, ServerConfig
from deploymate.ssh_manager import SSHManager, SSHManagerPool
from deploymate.utils.logger import LoggerMixin


class MonitoringError(Exception):
    """Custom exception for monitoring errors."""
    pass


class ServerMetrics:
    """Represents server metrics at a point in time."""
    
    def __init__(self, server_name: str):
        """
        Initialize server metrics.
        
        Args:
            server_name: Name of the server
        """
        self.server_name = server_name
        self.timestamp = datetime.now()
        self.cpu_usage: float = 0.0
        self.memory_usage: float = 0.0
        self.memory_total: float = 0.0
        self.memory_available: float = 0.0
        self.disk_usage: float = 0.0
        self.disk_total: float = 0.0
        self.disk_available: float = 0.0
        self.load_average: List[float] = []
        self.uptime: str = ""
        self.processes: int = 0
        self.network_io: Dict[str, int] = {}
        self.health_status: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'server_name': self.server_name,
            'timestamp': self.timestamp.isoformat(),
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'memory_total': self.memory_total,
            'memory_available': self.memory_available,
            'disk_usage': self.disk_usage,
            'disk_total': self.disk_total,
            'disk_available': self.disk_available,
            'load_average': self.load_average,
            'uptime': self.uptime,
            'processes': self.processes,
            'network_io': self.network_io,
            'health_status': self.health_status,
        }


class Monitor(LoggerMixin):
    """Monitors server health and performance."""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        check_interval: int = 60,
        metrics_dir: str = "logs/metrics",
    ):
        """
        Initialize monitor.
        
        Args:
            config_manager: Configuration manager instance
            check_interval: Interval between health checks in seconds
            metrics_dir: Directory to store metrics
        """
        self.config_manager = config_manager
        self.check_interval = check_interval
        self.metrics_dir = Path(metrics_dir)
        self.ssh_pool = SSHManagerPool()
        self.scheduler: Optional[BackgroundScheduler] = None
        self.is_running = False
        self.metrics_history: List[ServerMetrics] = []
        
        # Create metrics directory
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
    
    def check_server_health(self, server: ServerConfig) -> ServerMetrics:
        """
        Check health of a single server.
        
        Args:
            server: Server configuration
        
        Returns:
            ServerMetrics object with health data
        """
        metrics = ServerMetrics(server.name)
        
        try:
            # Get SSH connection
            ssh = self.ssh_pool.get_connection(
                host=server.host,
                username=server.username,
                port=server.port,
                key_path=server.key_path,
                password=server.password,
            )
            
            # Check if server is reachable
            if not ssh.check_connection():
                metrics.health_status = "unreachable"
                return metrics
            
            metrics.health_status = "healthy"
            
            # Get CPU usage
            exit_code, stdout, _ = ssh.execute_command(
                "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1"
            )
            if exit_code == 0 and stdout.strip():
                try:
                    metrics.cpu_usage = float(stdout.strip())
                except ValueError:
                    pass
            
            # Get memory information
            exit_code, stdout, _ = ssh.execute_command(
                "free -m | grep Mem | awk '{print $2, $3, $7}'"
            )
            if exit_code == 0 and stdout.strip():
                try:
                    parts = stdout.strip().split()
                    if len(parts) == 3:
                        metrics.memory_total = float(parts[0])
                        memory_used = float(parts[1])
                        metrics.memory_available = float(parts[2])
                        metrics.memory_usage = (memory_used / metrics.memory_total) * 100
                except (ValueError, ZeroDivisionError):
                    pass
            
            # Get disk usage
            exit_code, stdout, _ = ssh.execute_command(
                "df -k / | tail -1 | awk '{print $2, $3, $4, $5}'"
            )
            if exit_code == 0 and stdout.strip():
                try:
                    parts = stdout.strip().split()
                    if len(parts) == 4:
                        metrics.disk_total = float(parts[0]) / 1024  # MB
                        disk_used = float(parts[1]) / 1024  # MB
                        metrics.disk_available = float(parts[2]) / 1024  # MB
                        metrics.disk_usage = float(parts[3].rstrip('%'))
                except (ValueError, IndexError):
                    pass
            
            # Get load average
            exit_code, stdout, _ = ssh.execute_command("cat /proc/loadavg | awk '{print $1, $2, $3}'")
            if exit_code == 0 and stdout.strip():
                try:
                    metrics.load_average = [float(x) for x in stdout.strip().split()]
                except ValueError:
                    pass
            
            # Get uptime
            exit_code, stdout, _ = ssh.execute_command("uptime -p")
            if exit_code == 0:
                metrics.uptime = stdout.strip()
            
            # Get process count
            exit_code, stdout, _ = ssh.execute_command("ps aux | wc -l")
            if exit_code == 0 and stdout.strip():
                try:
                    metrics.processes = int(stdout.strip()) - 1  # Subtract header line
                except ValueError:
                    pass
            
            # Get network I/O
            exit_code, stdout, _ = ssh.execute_command(
                "cat /proc/net/dev | grep eth0 | awk '{print $2, $10}'"
            )
            if exit_code == 0 and stdout.strip():
                try:
                    parts = stdout.strip().split()
                    if len(parts) == 2:
                        metrics.network_io = {
                            'received_bytes': int(parts[0]),
                            'transmitted_bytes': int(parts[1]),
                        }
                except (ValueError, IndexError):
                    pass
            
        except Exception as e:
            self.logger.error(f"Error checking health of {server.name}: {e}")
            metrics.health_status = "error"
        
        return metrics
    
    def check_all_servers(self) -> List[ServerMetrics]:
        """
        Check health of all configured servers.
        
        Returns:
            List of ServerMetrics objects
        """
        metrics_list = []
        
        for server in self.config_manager.servers:
            self.logger.info(f"Checking health of {server.name}")
            metrics = self.check_server_health(server)
            metrics_list.append(metrics)
            
            # Save individual metrics
            self._save_metrics(metrics)
        
        # Add to history
        self.metrics_history.extend(metrics_list)
        
        return metrics_list
    
    def start_monitoring(self) -> None:
        """Start continuous monitoring in background."""
        if self.is_running:
            self.logger.warning("Monitoring is already running")
            return
        
        self.logger.info(
            f"Starting monitoring with {self.check_interval}s interval"
        )
        
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self.check_all_servers,
            'interval',
            seconds=self.check_interval,
            id='health_check',
            replace_existing=True,
        )
        
        self.scheduler.start()
        self.is_running = True
    
    def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        if self.scheduler and self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            self.logger.info("Monitoring stopped")
    
    def get_server_metrics(
        self,
        server_name: str,
        hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """
        Get metrics for a specific server from history.
        
        Args:
            server_name: Name of the server
            hours: Number of hours to look back
        
        Returns:
            List of metrics dictionaries
        """
        cutoff_time = datetime.now().timestamp() - (hours * 3600)
        
        metrics = [
            m.to_dict()
            for m in self.metrics_history
            if m.server_name == server_name
            and m.timestamp.timestamp() >= cutoff_time
        ]
        
        return metrics
    
    def get_alerts(self) -> List[Dict[str, Any]]:
        """
        Get current alerts based on health thresholds.
        
        Returns:
            List of alert dictionaries
        """
        alerts = []
        
        for metrics in self.metrics_history[-len(self.config_manager.servers):]:
            # CPU usage alert (> 90%)
            if metrics.cpu_usage > 90:
                alerts.append({
                    'server': metrics.server_name,
                    'type': 'high_cpu',
                    'value': metrics.cpu_usage,
                    'threshold': 90,
                    'timestamp': metrics.timestamp.isoformat(),
                })
            
            # Memory usage alert (> 85%)
            if metrics.memory_usage > 85:
                alerts.append({
                    'server': metrics.server_name,
                    'type': 'high_memory',
                    'value': metrics.memory_usage,
                    'threshold': 85,
                    'timestamp': metrics.timestamp.isoformat(),
                })
            
            # Disk usage alert (> 80%)
            if metrics.disk_usage > 80:
                alerts.append({
                    'server': metrics.server_name,
                    'type': 'high_disk',
                    'value': metrics.disk_usage,
                    'threshold': 80,
                    'timestamp': metrics.timestamp.isoformat(),
                })
            
            # Health status alert
            if metrics.health_status != "healthy":
                alerts.append({
                    'server': metrics.server_name,
                    'type': 'health_check_failed',
                    'value': metrics.health_status,
                    'threshold': 'healthy',
                    'timestamp': metrics.timestamp.isoformat(),
                })
        
        return alerts
    
    def _save_metrics(self, metrics: ServerMetrics) -> None:
        """
        Save metrics to file.
        
        Args:
            metrics: ServerMetrics object
        """
        try:
            metrics_file = self.metrics_dir / f"{metrics.server_name}_metrics.jsonl"
            
            with open(metrics_file, 'a') as f:
                f.write(json.dumps(metrics.to_dict()) + '\n')
                
        except Exception as e:
            self.logger.error(f"Failed to save metrics: {e}")
    
    def generate_report(self) -> Dict[str, Any]:
        """
        Generate a summary report of current server statuses.
        
        Returns:
            Report dictionary
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'servers': [],
            'summary': {
                'total_servers': len(self.config_manager.servers),
                'healthy_servers': 0,
                'warning_servers': 0,
                'critical_servers': 0,
            },
        }
        
        for metrics in self.metrics_history[-len(self.config_manager.servers):]:
            server_report = metrics.to_dict()
            
            # Determine status
            if metrics.health_status == "healthy":
                if metrics.cpu_usage < 70 and metrics.memory_usage < 75 and metrics.disk_usage < 70:
                    status = "healthy"
                    report['summary']['healthy_servers'] += 1
                elif metrics.cpu_usage < 90 and metrics.memory_usage < 85 and metrics.disk_usage < 80:
                    status = "warning"
                    report['summary']['warning_servers'] += 1
                else:
                    status = "critical"
                    report['summary']['critical_servers'] += 1
            else:
                status = "critical"
                report['summary']['critical_servers'] += 1
            
            server_report['status'] = status
            report['servers'].append(server_report)
        
        return report
    
    def __del__(self):
        """Clean up resources."""
        self.stop_monitoring()
        if hasattr(self, 'ssh_pool'):
            self.ssh_pool.close_all()


class LocalSystemMonitor:
    """Monitors the local system where DeployMate is running."""
    
    @staticmethod
    def get_cpu_usage() -> float:
        """Get local CPU usage percentage."""
        return psutil.cpu_percent(interval=1)
    
    @staticmethod
    def get_memory_usage() -> Dict[str, float]:
        """Get local memory usage."""
        memory = psutil.virtual_memory()
        return {
            'total': memory.total / (1024 ** 3),  # GB
            'available': memory.available / (1024 ** 3),  # GB
            'used': memory.used / (1024 ** 3),  # GB
            'percent': memory.percent,
        }
    
    @staticmethod
    def get_disk_usage() -> Dict[str, float]:
        """Get local disk usage."""
        disk = psutil.disk_usage('/')
        return {
            'total': disk.total / (1024 ** 3),  # GB
            'used': disk.used / (1024 ** 3),  # GB
            'free': disk.free / (1024 ** 3),  # GB
            'percent': disk.percent,
        }
    
    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Get comprehensive system information."""
        return {
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(),
            'memory': LocalSystemMonitor.get_memory_usage(),
            'disk': LocalSystemMonitor.get_disk_usage(),
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            'processes': len(psutil.pids()),
        }