"""Configuration management for DeployMate."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator

from deploymate.utils.logger import LoggerMixin
from deploymate.utils.validators import (
    validate_environment_variables,
    validate_health_check_url,
    validate_host,
    validate_port,
    validate_repository_url,
)


class ServerConfig(BaseModel):
    """Server configuration model."""
    
    name: str = Field(..., description="Server name")
    host: str = Field(..., description="Server hostname or IP")
    port: int = Field(22, description="SSH port")
    username: str = Field(..., description="SSH username")
    key_path: Optional[str] = Field(None, description="Path to SSH private key")
    password: Optional[str] = Field(None, description="SSH password")
    tags: List[str] = Field(default_factory=list, description="Server tags")
    environment: str = Field("production", description="Environment (production, staging, etc.)")
    description: str = Field("", description="Server description")
    
    @validator('name')
    def validate_name(cls, v: str) -> str:
        """Validate server name."""
        if not v or not v.strip():
            raise ValueError('Server name cannot be empty')
        if not re.match(r'^[a-zA-Z0-9-_]+$', v):
            raise ValueError('Server name can only contain letters, numbers, hyphens, and underscores')
        return v.strip()
    
    @validator('host')
    def validate_host_field(cls, v: str) -> str:
        """Validate host field."""
        if not validate_host(v):
            raise ValueError(f'Invalid host: {v}')
        return v
    
    @validator('port')
    def validate_port_field(cls, v: int) -> int:
        """Validate port field."""
        if not validate_port(v):
            raise ValueError(f'Invalid port: {v}')
        return v
    
    @validator('key_path')
    def validate_key_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate key path if provided."""
        if v:
            v = os.path.expanduser(v)
            if not Path(v).exists():
                raise ValueError(f'SSH key file not found: {v}')
        return v
    
    @validator('password')
    def validate_password(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        """Validate that either key_path or password is provided."""
        if not v and not values.get('key_path'):
            # Don't raise here if key_path might be set later
            pass
        return v


class DeploymentConfig(BaseModel):
    """Deployment configuration model."""
    
    name: str = Field(..., description="Deployment name")
    repository: str = Field(..., description="Git repository URL")
    branch: str = Field("main", description="Git branch to deploy")
    deploy_path: str = Field(..., description="Deployment path on server")
    pre_deploy_commands: List[str] = Field(default_factory=list)
    post_deploy_commands: List[str] = Field(default_factory=list)
    environment_variables: Dict[str, str] = Field(default_factory=dict)
    health_check_url: Optional[str] = Field(None)
    health_check_timeout: int = Field(30, ge=1, le=300)
    servers: List[str] = Field(default_factory=list)
    
    @validator('name')
    def validate_name(cls, v: str) -> str:
        """Validate deployment name."""
        if not v or not v.strip():
            raise ValueError('Deployment name cannot be empty')
        if not re.match(r'^[a-zA-Z0-9-_]+$', v):
            raise ValueError('Deployment name can only contain letters, numbers, hyphens, and underscores')
        return v.strip()
    
    @validator('repository')
    def validate_repository(cls, v: str) -> str:
        """Validate repository URL."""
        if not validate_repository_url(v):
            raise ValueError(f'Invalid repository URL: {v}')
        return v
    
    @validator('deploy_path')
    def validate_deploy_path(cls, v: str) -> str:
        """Validate deployment path."""
        if not v.startswith('/'):
            raise ValueError('Deploy path must be absolute')
        return v.rstrip('/')
    
    @validator('environment_variables')
    def validate_env_vars(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Validate environment variables."""
        if not validate_environment_variables(v):
            raise ValueError('Invalid environment variables format')
        return v
    
    @validator('health_check_url')
    def validate_health_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate health check URL."""
        if not validate_health_check_url(v):
            raise ValueError(f'Invalid health check URL: {v}')
        return v


class AlertConfig(BaseModel):
    """Alert configuration model."""
    
    slack: Dict[str, Any] = Field(default_factory=dict)
    email: Dict[str, Any] = Field(default_factory=dict)
    notification_rules: Dict[str, List[str]] = Field(default_factory=dict)
    
    @validator('notification_rules')
    def validate_rules(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Validate notification rules."""
        valid_events = {
            'on_deployment_start',
            'on_deployment_success',
            'on_deployment_failure',
            'on_health_check_failure',
            'on_rollback',
        }
        
        valid_channels = {'slack', 'email'}
        
        for event, channels in v.items():
            if event not in valid_events:
                raise ValueError(f'Invalid event: {event}')
            for channel in channels:
                if channel not in valid_channels:
                    raise ValueError(f'Invalid channel: {channel}')
        
        return v


class ConfigManager(LoggerMixin):
    """Manages loading and validation of configuration files."""
    
    def __init__(self, config_dir: Union[str, Path]):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self.servers: List[ServerConfig] = []
        self.deployments: List[DeploymentConfig] = []
        self.alerts: AlertConfig = AlertConfig()
        
        # Load environment variables
        load_dotenv()
        
        # Load configurations
        self.load_configurations()
    
    def load_configurations(self) -> None:
        """Load all configuration files."""
        self.logger.info(f"Loading configurations from {self.config_dir}")
        
        # Load server configurations
        servers_file = self.config_dir / 'servers.yaml'
        if servers_file.exists():
            self.load_servers(servers_file)
        else:
            self.logger.warning(f"Servers config file not found: {servers_file}")
        
        # Load deployment configurations
        deployments_file = self.config_dir / 'deployments.yaml'
        if deployments_file.exists():
            self.load_deployments(deployments_file)
        else:
            self.logger.warning(f"Deployments config file not found: {deployments_file}")
        
        # Load alert configurations
        alerts_file = self.config_dir / 'alerts.yaml'
        if alerts_file.exists():
            self.load_alerts(alerts_file)
        else:
            self.logger.warning(f"Alerts config file not found: {alerts_file}")
    
    def load_servers(self, file_path: Path) -> None:
        """
        Load server configurations from YAML file.
        
        Args:
            file_path: Path to servers YAML file
        """
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            servers_data = data.get('servers', [])
            self.servers = [ServerConfig(**server) for server in servers_data]
            self.logger.info(f"Loaded {len(self.servers)} server configurations")
            
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML file {file_path}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading servers from {file_path}: {e}")
            raise
    
    def load_deployments(self, file_path: Path) -> None:
        """
        Load deployment configurations from YAML file.
        
        Args:
            file_path: Path to deployments YAML file
        """
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            deployments_data = data.get('deployments', [])
            self.deployments = [DeploymentConfig(**deployment) for deployment in deployments_data]
            self.logger.info(f"Loaded {len(self.deployments)} deployment configurations")
            
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML file {file_path}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading deployments from {file_path}: {e}")
            raise
    
    def load_alerts(self, file_path: Path) -> None:
        """
        Load alert configurations from YAML file.
        
        Args:
            file_path: Path to alerts YAML file
        """
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            # Substitute environment variables
            data_str = yaml.dump(data)
            data_str = self._substitute_env_vars(data_str)
            data = yaml.safe_load(data_str)
            
            self.alerts = AlertConfig(**data)
            self.logger.info("Loaded alert configurations")
            
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML file {file_path}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading alerts from {file_path}: {e}")
            raise
    
    def _substitute_env_vars(self, content: str) -> str:
        """
        Substitute environment variables in configuration content.
        
        Args:
            content: Configuration content as string
        
        Returns:
            Content with environment variables substituted
        """
        pattern = r'\$\{([A-Z_][A-Z0-9_]*)\}'
        
        def replace(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))
        
        return re.sub(pattern, replace, content)
    
    def get_server(self, name: str) -> Optional[ServerConfig]:
        """
        Get server configuration by name.
        
        Args:
            name: Server name
        
        Returns:
            ServerConfig if found, None otherwise
        """
        for server in self.servers:
            if server.name == name:
                return server
        return None
    
    def get_deployment(self, name: str) -> Optional[DeploymentConfig]:
        """
        Get deployment configuration by name.
        
        Args:
            name: Deployment name
        
        Returns:
            DeploymentConfig if found, None otherwise
        """
        for deployment in self.deployments:
            if deployment.name == name:
                return deployment
        return None
    
    def get_servers_by_tag(self, tag: str) -> List[ServerConfig]:
        """
        Get servers filtered by tag.
        
        Args:
            tag: Tag to filter by
        
        Returns:
            List of matching ServerConfig objects
        """
        return [server for server in self.servers if tag in server.tags]
    
    def get_servers_by_environment(self, environment: str) -> List[ServerConfig]:
        """
        Get servers filtered by environment.
        
        Args:
            environment: Environment to filter by
        
        Returns:
            List of matching ServerConfig objects
        """
        return [server for server in self.servers if server.environment == environment]
    
    def validate_deployment(self, deployment_name: str) -> List[str]:
        """
        Validate a deployment configuration.
        
        Args:
            deployment_name: Name of the deployment to validate
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        deployment = self.get_deployment(deployment_name)
        
        if not deployment:
            errors.append(f"Deployment '{deployment_name}' not found")
            return errors
        
        # Validate that all referenced servers exist
        for server_name in deployment.servers:
            if not self.get_server(server_name):
                errors.append(f"Server '{server_name}' referenced in deployment not found")
        
        # Validate health check URL
        if deployment.health_check_url:
            if not validate_health_check_url(deployment.health_check_url):
                errors.append(f"Invalid health check URL: {deployment.health_check_url}")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of configuration
        """
        return {
            'servers': [server.dict() for server in self.servers],
            'deployments': [deployment.dict() for deployment in self.deployments],
            'alerts': self.alerts.dict(),
        }