"""Deployment automation for DeployMate."""

import hashlib
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from deploymate.config import ConfigManager, DeploymentConfig, ServerConfig
from deploymate.ssh_manager import SSHManager, SSHManagerPool, SSHCommandError
from deploymate.utils.logger import LoggerMixin


class DeploymentError(Exception):
    """Custom exception for deployment errors."""
    pass


class DeploymentResult:
    """Represents the result of a deployment."""
    
    def __init__(self, deployment_name: str, server_name: str):
        """
        Initialize deployment result.
        
        Args:
            deployment_name: Name of the deployment
            server_name: Name of the server
        """
        self.deployment_name = deployment_name
        self.server_name = server_name
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.success = False
        self.current_version: Optional[str] = None
        self.previous_version: Optional[str] = None
        self.error_message: Optional[str] = None
        self.commands_executed: List[Dict[str, Any]] = []
        self.health_check_passed = False
    
    @property
    def duration(self) -> float:
        """Get deployment duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'deployment_name': self.deployment_name,
            'server_name': self.server_name,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'success': self.success,
            'current_version': self.current_version,
            'previous_version': self.previous_version,
            'error_message': self.error_message,
            'health_check_passed': self.health_check_passed,
            'commands_executed': self.commands_executed,
        }


class Deployer(LoggerMixin):
    """Handles application deployment to remote servers."""
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize deployer.
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.ssh_pool = SSHManagerPool()
        self.deployment_history: List[DeploymentResult] = []
        self.history_file = Path("deployments/history.json")
    
    def deploy(
        self,
        deployment_name: str,
        server_names: Optional[List[str]] = None,
        version: Optional[str] = None,
        force: bool = False,
    ) -> List[DeploymentResult]:
        """
        Deploy an application to specified servers.
        
        Args:
            deployment_name: Name of the deployment configuration
            server_names: Optional list of server names to deploy to
            version: Optional version to deploy (default: latest from branch)
            force: Force deployment even if health checks fail
        
        Returns:
            List of DeploymentResult objects
        """
        deployment_config = self.config_manager.get_deployment(deployment_name)
        if not deployment_config:
            raise DeploymentError(f"Deployment '{deployment_name}' not found")
        
        # Validate deployment
        errors = self.config_manager.validate_deployment(deployment_name)
        if errors:
            raise DeploymentError(f"Deployment validation failed: {'; '.join(errors)}")
        
        # Determine target servers
        if server_names:
            servers = [self.config_manager.get_server(name) for name in server_names]
            servers = [s for s in servers if s is not None]
        else:
            servers = [
                self.config_manager.get_server(name)
                for name in deployment_config.servers
                if self.config_manager.get_server(name)
            ]
        
        if not servers:
            raise DeploymentError("No valid target servers found")
        
        self.logger.info(
            f"Starting deployment '{deployment_name}' to {len(servers)} server(s)"
        )
        
        results = []
        for server in servers:
            try:
                result = self._deploy_to_server(
                    deployment_config,
                    server,
                    version,
                    force,
                )
                results.append(result)
                
                if result.success:
                    self.logger.info(
                        f"Deployment to {server.name} completed successfully in {result.duration:.2f}s"
                    )
                else:
                    self.logger.error(
                        f"Deployment to {server.name} failed: {result.error_message}"
                    )
                    
            except Exception as e:
                self.logger.error(f"Error deploying to {server.name}: {e}")
                result = DeploymentResult(deployment_name, server.name)
                result.end_time = datetime.now()
                result.error_message = str(e)
                results.append(result)
        
        # Save deployment history
        self.deployment_history.extend(results)
        self._save_history()
        
        return results
    
    def _deploy_to_server(
        self,
        deployment_config: DeploymentConfig,
        server: ServerConfig,
        version: Optional[str],
        force: bool,
    ) -> DeploymentResult:
        """
        Deploy application to a single server.
        
        Args:
            deployment_config: Deployment configuration
            server: Server configuration
            version: Version to deploy
            force: Force deployment
        
        Returns:
            DeploymentResult object
        """
        result = DeploymentResult(deployment_config.name, server.name)
        
        try:
            # Get SSH connection
            ssh = self.ssh_pool.get_connection(
                host=server.host,
                username=server.username,
                port=server.port,
                key_path=server.key_path,
                password=server.password,
            )
            
            # Generate version if not provided
            if not version:
                version = self._generate_version(deployment_config)
            result.current_version = version
            
            # Get previous version if exists
            result.previous_version = self._get_current_version(ssh, deployment_config)
            
            self.logger.info(f"Deploying version {version} to {server.name}")
            
            # Execute pre-deployment commands
            if deployment_config.pre_deploy_commands:
                self.logger.info("Executing pre-deployment commands")
                pre_results = ssh.execute_commands(deployment_config.pre_deploy_commands)
                result.commands_executed.extend(pre_results)
                
                if not all(cmd['success'] for cmd in pre_results):
                    raise DeploymentError("Pre-deployment commands failed")
            
            # Create release directory
            release_path = f"{deployment_config.deploy_path}/releases/{version}"
            current_path = f"{deployment_config.deploy_path}/current"
            
            # Clone repository
            self.logger.info(f"Cloning repository {deployment_config.repository}")
            clone_command = (
                f"git clone --depth 1 --branch {deployment_config.branch} "
                f"{deployment_config.repository} {release_path}"
            )
            exit_code, stdout, stderr = ssh.execute_command(clone_command, timeout=300)
            
            if exit_code != 0:
                raise DeploymentError(f"Failed to clone repository: {stderr}")
            
            result.commands_executed.append({
                'command': clone_command,
                'exit_code': exit_code,
                'stdout': stdout,
                'stderr': stderr,
                'success': exit_code == 0,
            })
            
            # Set up environment variables
            if deployment_config.environment_variables:
                env_file_content = ""
                for key, value in deployment_config.environment_variables.items():
                    env_file_content += f'export {key}="{value}"\n'
                
                env_file_path = f"{release_path}/.env"
                ssh.execute_command(f"echo '{env_file_content}' > {env_file_path}")
            
            # Create symlink to new release
            self.logger.info(f"Updating symlink to version {version}")
            
            symlink_commands = [
                f"ln -sfn {release_path} {current_path}",
                f"echo {version} > {deployment_config.deploy_path}/VERSION",
            ]
            
            symlink_results = ssh.execute_commands(symlink_commands)
            result.commands_executed.extend(symlink_results)
            
            if not all(cmd['success'] for cmd in symlink_results):
                raise DeploymentError("Failed to update symlinks")
            
            # Execute post-deployment commands
            if deployment_config.post_deploy_commands:
                self.logger.info("Executing post-deployment commands")
                post_results = ssh.execute_commands(deployment_config.post_deploy_commands)
                result.commands_executed.extend(post_results)
                
                if not all(cmd['success'] for cmd in post_results):
                    raise DeploymentError("Post-deployment commands failed")
            
            # Perform health check
            if deployment_config.health_check_url:
                self.logger.info("Performing health check")
                health_check_passed = self._perform_health_check(
                    deployment_config.health_check_url,
                    deployment_config.health_check_timeout,
                )
                result.health_check_passed = health_check_passed
                
                if not health_check_passed and not force:
                    # Rollback if health check fails
                    self.logger.error("Health check failed, rolling back")
                    self._rollback(ssh, deployment_config, result.previous_version)
                    raise DeploymentError("Health check failed after deployment")
            
            # Clean up old releases (keep last 5)
            self._cleanup_old_releases(ssh, deployment_config, keep=5)
            
            result.success = True
            
        except Exception as e:
            result.error_message = str(e)
            result.success = False
            
            # Attempt rollback if deployment failed
            if result.previous_version:
                try:
                    ssh = self.ssh_pool.get_connection(
                        host=server.host,
                        username=server.username,
                        port=server.port,
                        key_path=server.key_path,
                        password=server.password,
                    )
                    self._rollback(ssh, deployment_config, result.previous_version)
                    self.logger.info(f"Rolled back to version {result.previous_version}")
                except Exception as rollback_error:
                    self.logger.error(f"Rollback failed: {rollback_error}")
        
        finally:
            result.end_time = datetime.now()
        
        return result
    
    def _generate_version(self, deployment_config: DeploymentConfig) -> str:
        """
        Generate a version string based on timestamp and commit hash.
        
        Args:
            deployment_config: Deployment configuration
        
        Returns:
            Version string
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Try to get commit hash
        try:
            # This would need to query the git repository
            # For now, use a hash of the deployment config
            config_hash = hashlib.md5(
                json.dumps(deployment_config.dict(), sort_keys=True).encode()
            ).hexdigest()[:8]
            return f"{timestamp}-{config_hash}"
        except Exception:
            return timestamp
    
    def _get_current_version(
        self,
        ssh: SSHManager,
        deployment_config: DeploymentConfig,
    ) -> Optional[str]:
        """
        Get current deployed version from server.
        
        Args:
            ssh: SSH manager instance
            deployment_config: Deployment configuration
        
        Returns:
            Current version string or None
        """
        version_file = f"{deployment_config.deploy_path}/VERSION"
        exit_code, stdout, _ = ssh.execute_command(f"cat {version_file} 2>/dev/null")
        
        if exit_code == 0 and stdout.strip():
            return stdout.strip()
        
        return None
    
    def _perform_health_check(self, url: str, timeout: int) -> bool:
        """
        Perform HTTP health check.
        
        Args:
            url: Health check URL
            timeout: Timeout in seconds
        
        Returns:
            True if health check passes, False otherwise
        """
        try:
            response = requests.get(url, timeout=timeout)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def _rollback(
        self,
        ssh: SSHManager,
        deployment_config: DeploymentConfig,
        version: str,
    ) -> None:
        """
        Rollback to a previous version.
        
        Args:
            ssh: SSH manager instance
            deployment_config: Deployment configuration
            version: Version to rollback to
        """
        if not version:
            raise DeploymentError("No version to rollback to")
        
        release_path = f"{deployment_config.deploy_path}/releases/{version}"
        current_path = f"{deployment_config.deploy_path}/current"
        
        # Check if release exists
        exit_code, _, stderr = ssh.execute_command(f"test -d {release_path}")
        if exit_code != 0:
            raise DeploymentError(f"Release directory not found: {release_path}")
        
        # Update symlink
        commands = [
            f"ln -sfn {release_path} {current_path}",
            f"echo {version} > {deployment_config.deploy_path}/VERSION",
        ]
        
        results = ssh.execute_commands(commands)
        
        if not all(cmd['success'] for cmd in results):
            raise DeploymentError("Failed to rollback")
        
        # Restart services
        if deployment_config.post_deploy_commands:
            ssh.execute_commands(deployment_config.post_deploy_commands)
    
    def _cleanup_old_releases(
        self,
        ssh: SSHManager,
        deployment_config: DeploymentConfig,
        keep: int = 5,
    ) -> None:
        """
        Clean up old release directories.
        
        Args:
            ssh: SSH manager instance
            deployment_config: Deployment configuration
            keep: Number of releases to keep
        """
        releases_path = f"{deployment_config.deploy_path}/releases"
        
        cleanup_command = (
            f"cd {releases_path} && ls -t | tail -n +{keep + 1} | xargs -r rm -rf"
        )
        
        ssh.execute_command(cleanup_command)
    
    def _save_history(self) -> None:
        """Save deployment history to file."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            
            history_data = [result.to_dict() for result in self.deployment_history]
            
            with open(self.history_file, 'w') as f:
                json.dump(history_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to save deployment history: {e}")
    
    def get_deployment_history(self) -> List[Dict[str, Any]]:
        """
        Get deployment history.
        
        Returns:
            List of deployment history entries
        """
        return [result.to_dict() for result in self.deployment_history]
    
    def __del__(self):
        """Clean up SSH connections."""
        if hasattr(self, 'ssh_pool'):
            self.ssh_pool.close_all()