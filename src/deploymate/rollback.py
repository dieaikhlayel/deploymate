"""Rollback management for DeployMate."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from deploymate.config import ConfigManager, DeploymentConfig, ServerConfig
from deploymate.ssh_manager import SSHManager, SSHManagerPool
from deploymate.utils.logger import LoggerMixin


class RollbackError(Exception):
    """Custom exception for rollback errors."""
    pass


class RollbackManager(LoggerMixin):
    """Manages deployment rollbacks."""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        backup_dir: str = "backups",
    ):
        """
        Initialize rollback manager.
        
        Args:
            config_manager: Configuration manager instance
            backup_dir: Directory for storing backups
        """
        self.config_manager = config_manager
        self.backup_dir = Path(backup_dir)
        self.ssh_pool = SSHManagerPool()
        self.rollback_history: List[Dict[str, Any]] = []
        self.history_file = Path("deployments/rollback_history.json")
        
        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Load rollback history
        self._load_history()
    
    def create_backup(
        self,
        deployment_name: str,
        server: ServerConfig,
        version: str,
    ) -> str:
        """
        Create a backup of current deployment.
        
        Args:
            deployment_name: Name of the deployment
            server: Server configuration
            version: Version to backup
        
        Returns:
            Backup identifier
        """
        deployment = self.config_manager.get_deployment(deployment_name)
        if not deployment:
            raise RollbackError(f"Deployment '{deployment_name}' not found")
        
        try:
            # Get SSH connection
            ssh = self.ssh_pool.get_connection(
                host=server.host,
                username=server.username,
                port=server.port,
                key_path=server.key_path,
                password=server.password,
            )
            
            # Create backup
            backup_id = f"{deployment_name}_{server.name}_{version}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            remote_backup_path = f"{deployment.deploy_path}/backups/{backup_id}"
            current_path = f"{deployment.deploy_path}/current"
            
            # Create backup directory
            commands = [
                f"mkdir -p {remote_backup_path}",
                f"cp -r {current_path}/* {remote_backup_path}/ 2>/dev/null || true",
                f"cp {deployment.deploy_path}/VERSION {remote_backup_path}/ 2>/dev/null || true",
            ]
            
            results = ssh.execute_commands(commands)
            
            if not all(cmd['success'] for cmd in results):
                raise RollbackError(f"Failed to create backup on {server.name}")
            
            # Save backup metadata
            backup_info = {
                'backup_id': backup_id,
                'deployment_name': deployment_name,
                'server_name': server.name,
                'version': version,
                'timestamp': datetime.now().isoformat(),
                'remote_path': remote_backup_path,
            }
            
            self._save_backup_info(backup_info)
            
            self.logger.info(f"Created backup {backup_id} for {deployment_name} on {server.name}")
            return backup_id
            
        except Exception as e:
            self.logger.error(f"Failed to create backup: {e}")
            raise RollbackError(f"Backup creation failed: {e}")
    
    def rollback(
        self,
        deployment_name: str,
        server: ServerConfig,
        target_version: Optional[str] = None,
        backup_id: Optional[str] = None,
    ) -> bool:
        """
        Rollback deployment to previous version.
        
        Args:
            deployment_name: Name of the deployment
            server: Server configuration
            target_version: Version to rollback to
            backup_id: Backup ID to restore from
        
        Returns:
            True if rollback successful
        """
        deployment = self.config_manager.get_deployment(deployment_name)
        if not deployment:
            raise RollbackError(f"Deployment '{deployment_name}' not found")
        
        try:
            # Get SSH connection
            ssh = self.ssh_pool.get_connection(
                host=server.host,
                username=server.username,
                port=server.port,
                key_path=server.key_path,
                password=server.password,
            )
            
            # Determine target version
            if backup_id:
                # Rollback from backup
                target_version = self._rollback_from_backup(
                    ssh, deployment, server, backup_id
                )
            elif target_version:
                # Rollback to specific version
                self._rollback_to_version(ssh, deployment, target_version)
            else:
                # Rollback to previous version
                target_version = self._rollback_to_previous(ssh, deployment)
            
            # Update current symlink
            current_path = f"{deployment.deploy_path}/current"
            target_path = f"{deployment.deploy_path}/releases/{target_version}"
            
            # Verify target exists
            exit_code, _, stderr = ssh.execute_command(f"test -d {target_path}")
            if exit_code != 0:
                raise RollbackError(f"Target version directory not found: {target_path}")
            
            # Perform rollback
            commands = [
                f"ln -sfn {target_path} {current_path}",
                f"echo {target_version} > {deployment.deploy_path}/VERSION",
            ]
            
            results = ssh.execute_commands(commands)
            
            if not all(cmd['success'] for cmd in results):
                raise RollbackError("Failed to update symlinks")
            
            # Execute post-rollback commands (restart services)
            if deployment.post_deploy_commands:
                self.logger.info("Restarting services after rollback")
                restart_results = ssh.execute_commands(deployment.post_deploy_commands)
                
                if not all(cmd['success'] for cmd in restart_results):
                    self.logger.warning("Some post-rollback commands failed")
            
            # Record rollback
            rollback_info = {
                'deployment_name': deployment_name,
                'server_name': server.name,
                'target_version': target_version,
                'timestamp': datetime.now().isoformat(),
                'success': True,
            }
            
            self.rollback_history.append(rollback_info)
            self._save_history()
            
            self.logger.info(
                f"Successfully rolled back {deployment_name} to version {target_version} on {server.name}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            
            # Record failed rollback
            rollback_info = {
                'deployment_name': deployment_name,
                'server_name': server.name,
                'target_version': target_version,
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'error': str(e),
            }
            
            self.rollback_history.append(rollback_info)
            self._save_history()
            
            raise RollbackError(f"Rollback failed: {e}")
    
    def _rollback_to_version(
        self,
        ssh: SSHManager,
        deployment: DeploymentConfig,
        version: str,
    ) -> None:
        """
        Rollback to a specific version.
        
        Args:
            ssh: SSH manager instance
            deployment: Deployment configuration
            version: Version to rollback to
        """
        release_path = f"{deployment.deploy_path}/releases/{version}"
        
        # Check if version exists
        exit_code, _, _ = ssh.execute_command(f"test -d {release_path}")
        if exit_code != 0:
            raise RollbackError(f"Version {version} not found")
    
    def _rollback_to_previous(
        self,
        ssh: SSHManager,
        deployment: DeploymentConfig,
    ) -> str:
        """
        Rollback to the previous version.
        
        Args:
            ssh: SSH manager instance
            deployment: Deployment configuration
        
        Returns:
            Previous version string
        """
        releases_path = f"{deployment.deploy_path}/releases"
        
        # Get list of releases (sorted by modification time)
        exit_code, stdout, _ = ssh.execute_command(
            f"ls -lt {releases_path} | grep '^d' | awk '{{print $9}}' | head -n 2 | tail -n 1"
        )
        
        if exit_code != 0 or not stdout.strip():
            raise RollbackError("No previous version found")
        
        previous_version = stdout.strip()
        self.logger.info(f"Rolling back to previous version: {previous_version}")
        
        return previous_version
    
    def _rollback_from_backup(
        self,
        ssh: SSHManager,
        deployment: DeploymentConfig,
        server: ServerConfig,
        backup_id: str,
    ) -> str:
        """
        Rollback from a backup.
        
        Args:
            ssh: SSH manager instance
            deployment: Deployment configuration
            server: Server configuration
            backup_id: Backup identifier
        
        Returns:
            Restored version string
        """
        # Get backup info
        backup_info = self._get_backup_info(backup_id)
        if not backup_info:
            raise RollbackError(f"Backup '{backup_id}' not found")
        
        remote_backup_path = backup_info.get('remote_path')
        if not remote_backup_path:
            raise RollbackError("Backup path not found")
        
        # Check if backup exists on server
        exit_code, _, _ = ssh.execute_command(f"test -d {remote_backup_path}")
        if exit_code != 0:
            raise RollbackError(f"Backup directory not found on server: {remote_backup_path}")
        
        # Create new release from backup
        version = f"rollback-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        release_path = f"{deployment.deploy_path}/releases/{version}"
        
        commands = [
            f"mkdir -p {release_path}",
            f"cp -r {remote_backup_path}/* {release_path}/",
        ]
        
        results = ssh.execute_commands(commands)
        
        if not all(cmd['success'] for cmd in results):
            raise RollbackError("Failed to restore from backup")
        
        return version
    
    def list_available_versions(
        self,
        deployment_name: str,
        server: ServerConfig,
    ) -> List[str]:
        """
        List available versions for rollback.
        
        Args:
            deployment_name: Name of the deployment
            server: Server configuration
        
        Returns:
            List of version strings
        """
        deployment = self.config_manager.get_deployment(deployment_name)
        if not deployment:
            raise RollbackError(f"Deployment '{deployment_name}' not found")
        
        try:
            ssh = self.ssh_pool.get_connection(
                host=server.host,
                username=server.username,
                port=server.port,
                key_path=server.key_path,
                password=server.password,
            )
            
            releases_path = f"{deployment.deploy_path}/releases"
            
            exit_code, stdout, _ = ssh.execute_command(
                f"ls -lt {releases_path} | grep '^d' | awk '{{print $9}}'"
            )
            
            if exit_code != 0:
                return []
            
            return [line.strip() for line in stdout.strip().split('\n') if line.strip()]
            
        except Exception as e:
            self.logger.error(f"Failed to list versions: {e}")
            return []
    
    def cleanup_backups(self, max_age_days: int = 30) -> int:
        """
        Clean up old backups.
        
        Args:
            max_age_days: Maximum age of backups to keep
        
        Returns:
            Number of backups removed
        """
        removed_count = 0
        cutoff_time = datetime.now().timestamp() - (max_age_days * 86400)
        
        for backup_file in self.backup_dir.glob("*.json"):
            try:
                with open(backup_file, 'r') as f:
                    backup_info = json.load(f)
                
                backup_time = datetime.fromisoformat(backup_info['timestamp']).timestamp()
                
                if backup_time < cutoff_time:
                    # Remove backup from server
                    server = self.config_manager.get_server(backup_info['server_name'])
                    if server:
                        ssh = self.ssh_pool.get_connection(
                            host=server.host,
                            username=server.username,
                            port=server.port,
                            key_path=server.key_path,
                            password=server.password,
                        )
                        
                        remote_path = backup_info.get('remote_path')
                        if remote_path:
                            ssh.execute_command(f"rm -rf {remote_path}")
                    
                    # Remove local backup info
                    backup_file.unlink()
                    removed_count += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to process backup {backup_file}: {e}")
        
        return removed_count
    
    def _save_backup_info(self, backup_info: Dict[str, Any]) -> None:
        """Save backup information to file."""
        backup_file = self.backup_dir / f"{backup_info['backup_id']}.json"
        
        with open(backup_file, 'w') as f:
            json.dump(backup_info, f, indent=2)
    
    def _get_backup_info(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Get backup information from file."""
        backup_file = self.backup_dir / f"{backup_id}.json"
        
        if not backup_file.exists():
            return None
        
        with open(backup_file, 'r') as f:
            return json.load(f)
    
    def _save_history(self) -> None:
        """Save rollback history to file."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.history_file, 'w') as f:
                json.dump(self.rollback_history, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to save rollback history: {e}")
    
    def _load_history(self) -> None:
        """Load rollback history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    self.rollback_history = json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load rollback history: {e}")
    
    def __del__(self):
        """Clean up resources."""
        if hasattr(self, 'ssh_pool'):
            self.ssh_pool.close_all()