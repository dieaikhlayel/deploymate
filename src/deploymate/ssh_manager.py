"""SSH connection management for DeployMate."""

import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import paramiko
from paramiko import SSHClient, AutoAddPolicy, SSHException
from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError

from deploymate.utils.logger import LoggerMixin


class SSHConnectionError(Exception):
    """Custom exception for SSH connection errors."""
    pass


class SSHCommandError(Exception):
    """Custom exception for SSH command execution errors."""
    pass


class SSHManager(LoggerMixin):
    """Manages SSH connections to remote servers."""
    
    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """
        Initialize SSH manager for a specific server.
        
        Args:
            host: Server hostname or IP
            username: SSH username
            port: SSH port (default: 22)
            key_path: Path to SSH private key file
            password: SSH password (alternative to key)
            timeout: Connection timeout in seconds
            max_retries: Maximum number of connection retries
            retry_delay: Delay between retries in seconds
        """
        self.host = host
        self.username = username
        self.port = port
        self.key_path = key_path
        self.password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self._client: Optional[SSHClient] = None
        self._connected = False
        
    def connect(self) -> None:
        """
        Establish SSH connection with retry logic.
        
        Raises:
            SSHConnectionError: If connection fails after all retries
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.debug(
                    f"Connecting to {self.host}:{self.port} as {self.username} "
                    f"(attempt {attempt}/{self.max_retries})"
                )
                
                client = SSHClient()
                client.set_missing_host_key_policy(AutoAddPolicy())
                
                connect_kwargs: Dict[str, Any] = {
                    'hostname': self.host,
                    'port': self.port,
                    'username': self.username,
                    'timeout': self.timeout,
                    'banner_timeout': self.timeout,
                    'auth_timeout': self.timeout,
                    'look_for_keys': True,
                    'allow_agent': True,
                }
                
                # Add authentication method
                if self.key_path:
                    key_path = os.path.expanduser(self.key_path)
                    if not Path(key_path).exists():
                        raise SSHConnectionError(f"SSH key file not found: {key_path}")
                    
                    # Try to load the key
                    key = self._load_private_key(key_path)
                    if key:
                        connect_kwargs['pkey'] = key
                    else:
                        connect_kwargs['key_filename'] = key_path
                elif self.password:
                    connect_kwargs['password'] = self.password
                else:
                    # Try SSH agent
                    connect_kwargs['allow_agent'] = True
                
                client.connect(**connect_kwargs)
                
                self._client = client
                self._connected = True
                self.logger.info(f"Successfully connected to {self.host}")
                return
                
            except AuthenticationException as e:
                self.logger.error(f"Authentication failed for {self.host}: {e}")
                raise SSHConnectionError(f"Authentication failed: {e}")
                
            except (SSHException, NoValidConnectionsError, socket.error) as e:
                self.logger.warning(
                    f"Connection attempt {attempt} failed for {self.host}: {e}"
                )
                
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)  # Exponential backoff
                else:
                    raise SSHConnectionError(
                        f"Failed to connect to {self.host} after {self.max_retries} attempts: {e}"
                    )
                    
            except Exception as e:
                self.logger.error(f"Unexpected error connecting to {self.host}: {e}")
                raise SSHConnectionError(f"Unexpected connection error: {e}")
    
    def disconnect(self) -> None:
        """Close SSH connection."""
        if self._client:
            try:
                self._client.close()
                self.logger.info(f"Disconnected from {self.host}")
            except Exception as e:
                self.logger.warning(f"Error closing connection to {self.host}: {e}")
            finally:
                self._client = None
                self._connected = False
    
    def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None,
        sudo: bool = False,
        sudo_password: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """
        Execute a command on the remote server.
        
        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            sudo: Whether to run with sudo
            sudo_password: Password for sudo (if required)
        
        Returns:
            Tuple of (exit_code, stdout, stderr)
        
        Raises:
            SSHCommandError: If command execution fails
        """
        if not self._connected or not self._client:
            raise SSHCommandError("Not connected to server")
        
        try:
            # Prepare command with sudo if needed
            if sudo:
                if sudo_password:
                    command = f"echo '{sudo_password}' | sudo -S {command}"
                else:
                    command = f"sudo {command}"
            
            self.logger.debug(f"Executing command on {self.host}: {command}")
            
            stdin, stdout, stderr = self._client.exec_command(
                command,
                timeout=timeout or self.timeout,
                get_pty=sudo,  # Use PTY for sudo commands
            )
            
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode('utf-8', errors='ignore')
            stderr_text = stderr.read().decode('utf-8', errors='ignore')
            
            if exit_code != 0:
                self.logger.warning(
                    f"Command failed with exit code {exit_code}: {command}\n"
                    f"Error: {stderr_text}"
                )
            else:
                self.logger.debug(f"Command executed successfully: {command}")
            
            return exit_code, stdout_text, stderr_text
            
        except Exception as e:
            raise SSHCommandError(f"Error executing command '{command}': {e}")
    
    def execute_commands(
        self,
        commands: List[str],
        stop_on_error: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple commands sequentially.
        
        Args:
            commands: List of commands to execute
            stop_on_error: Whether to stop on first error
        
        Returns:
            List of command results
        """
        results = []
        
        for command in commands:
            self.logger.info(f"Executing: {command}")
            
            try:
                exit_code, stdout, stderr = self.execute_command(command)
                result = {
                    'command': command,
                    'exit_code': exit_code,
                    'stdout': stdout,
                    'stderr': stderr,
                    'success': exit_code == 0,
                }
                results.append(result)
                
                if not result['success'] and stop_on_error:
                    self.logger.error(f"Stopping execution due to error in command: {command}")
                    break
                    
            except SSHCommandError as e:
                result = {
                    'command': command,
                    'exit_code': -1,
                    'stdout': '',
                    'stderr': str(e),
                    'success': False,
                }
                results.append(result)
                
                if stop_on_error:
                    break
        
        return results
    
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        Upload a file to the remote server via SFTP.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path
        
        Raises:
            SSHCommandError: If file upload fails
        """
        if not self._connected or not self._client:
            raise SSHCommandError("Not connected to server")
        
        try:
            self.logger.info(f"Uploading {local_path} to {self.host}:{remote_path}")
            
            sftp = self._client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            
            self.logger.info(f"File uploaded successfully")
            
        except Exception as e:
            raise SSHCommandError(f"Error uploading file: {e}")
    
    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Download a file from the remote server via SFTP.
        
        Args:
            remote_path: Remote file path
            local_path: Local file path
        
        Raises:
            SSHCommandError: If file download fails
        """
        if not self._connected or not self._client:
            raise SSHCommandError("Not connected to server")
        
        try:
            self.logger.info(f"Downloading {self.host}:{remote_path} to {local_path}")
            
            # Create local directory if it doesn't exist
            local_dir = Path(local_path).parent
            local_dir.mkdir(parents=True, exist_ok=True)
            
            sftp = self._client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
            
            self.logger.info(f"File downloaded successfully")
            
        except Exception as e:
            raise SSHCommandError(f"Error downloading file: {e}")
    
    def check_connection(self) -> bool:
        """
        Check if SSH connection is alive.
        
        Returns:
            True if connected, False otherwise
        """
        if not self._client:
            return False
        
        try:
            transport = self._client.get_transport()
            if transport and transport.is_active():
                return True
        except Exception:
            pass
        
        return False
    
    def get_system_info(self) -> Dict[str, Any]:
        """
        Get basic system information from the remote server.
        
        Returns:
            Dictionary with system information
        """
        info = {}
        
        # Get hostname
        exit_code, stdout, _ = self.execute_command("hostname")
        if exit_code == 0:
            info['hostname'] = stdout.strip()
        
        # Get OS information
        exit_code, stdout, _ = self.execute_command("uname -a")
        if exit_code == 0:
            info['os'] = stdout.strip()
        
        # Get CPU information
        exit_code, stdout, _ = self.execute_command("nproc")
        if exit_code == 0:
            info['cpu_count'] = int(stdout.strip())
        
        # Get memory information
        exit_code, stdout, _ = self.execute_command("free -h | grep Mem | awk '{print $2}'")
        if exit_code == 0:
            info['total_memory'] = stdout.strip()
        
        # Get disk usage
        exit_code, stdout, _ = self.execute_command("df -h / | tail -1 | awk '{print $2}'")
        if exit_code == 0:
            info['total_disk'] = stdout.strip()
        
        return info
    
    def _load_private_key(self, key_path: str) -> Optional[paramiko.PKey]:
        """
        Load a private key for SSH authentication.
        
        Args:
            key_path: Path to private key file
        
        Returns:
            Paramiko PKey object or None if loading fails
        """
        key_types = [
            paramiko.RSAKey,
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
            paramiko.DSSKey,
        ]
        
        for key_type in key_types:
            try:
                key = key_type.from_private_key_file(key_path)
                self.logger.debug(f"Loaded {key_type.__name__} key from {key_path}")
                return key
            except (paramiko.PasswordRequiredException, paramiko.SSHException, IOError):
                continue
        
        self.logger.warning(f"Could not load private key from {key_path}")
        return None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    def __del__(self):
        """Destructor to ensure connection is closed."""
        self.disconnect()


class SSHManagerPool:
    """Manages multiple SSH connections."""
    
    def __init__(self):
        """Initialize SSH manager pool."""
        self._connections: Dict[str, SSHManager] = {}
    
    def get_connection(
        self,
        host: str,
        username: str,
        port: int = 22,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any,
    ) -> SSHManager:
        """
        Get or create an SSH connection.
        
        Args:
            host: Server hostname
            username: SSH username
            port: SSH port
            key_path: SSH key path
            password: SSH password
            **kwargs: Additional arguments
        
        Returns:
            SSHManager instance
        """
        connection_key = f"{username}@{host}:{port}"
        
        if connection_key not in self._connections:
            manager = SSHManager(
                host=host,
                username=username,
                port=port,
                key_path=key_path,
                password=password,
                **kwargs,
            )
            manager.connect()
            self._connections[connection_key] = manager
        
        return self._connections[connection_key]
    
    def close_all(self) -> None:
        """Close all managed connections."""
        for manager in self._connections.values():
            manager.disconnect()
        self._connections.clear()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close_all()