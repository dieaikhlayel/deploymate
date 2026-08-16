"""Test fixtures for DeployMate."""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest
import yaml

from deploymate.config import ConfigManager


@pytest.fixture
def sample_config_dir(tmp_path: Path) -> Path:
    """Create a sample configuration directory."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    
    # Create servers.yaml
    servers_config = {
        'servers': [
            {
                'name': 'test-server-1',
                'host': '192.168.1.100',
                'port': 22,
                'username': 'testuser',
                'key_path': None,
                'tags': ['web', 'test'],
                'environment': 'testing',
            },
            {
                'name': 'test-server-2',
                'host': '192.168.1.101',
                'port': 22,
                'username': 'testuser',
                'key_path': None,
                'tags': ['db', 'test'],
                'environment': 'testing',
            },
        ]
    }
    
    with open(config_dir / 'servers.yaml', 'w') as f:
        yaml.dump(servers_config, f)
    
    # Create deployments.yaml
    deployments_config = {
        'deployments': [
            {
                'name': 'test-app',
                'repository': 'git@github.com:test/test-app.git',
                'branch': 'main',
                'deploy_path': '/opt/test-app',
                'pre_deploy_commands': ['mkdir -p /opt/test-app/releases'],
                'post_deploy_commands': ['systemctl restart test-app'],
                'environment_variables': {'APP_ENV': 'testing'},
                'health_check_url': 'http://localhost:8080/health',
                'health_check_timeout': 10,
                'servers': ['test-server-1'],
            }
        ]
    }
    
    with open(config_dir / 'deployments.yaml', 'w') as f:
        yaml.dump(deployments_config, f)
    
    # Create alerts.yaml
    alerts_config = {
        'slack': {
            'enabled': False,
            'webhook_url': None,
            'channel': '#deployments',
        },
        'email': {
            'enabled': False,
        },
        'notification_rules': {
            'on_deployment_start': ['slack'],
            'on_deployment_success': ['slack'],
            'on_deployment_failure': ['slack', 'email'],
        }
    }
    
    with open(config_dir / 'alerts.yaml', 'w') as f:
        yaml.dump(alerts_config, f)
    
    return config_dir


@pytest.fixture
def config_manager(sample_config_dir: Path) -> ConfigManager:
    """Create a ConfigManager instance with sample config."""
    return ConfigManager(sample_config_dir)


@pytest.fixture
def mock_ssh_response() -> Dict[str, Any]:
    """Create a mock SSH response."""
    return {
        'exit_code': 0,
        'stdout': 'test output',
        'stderr': '',
        'success': True,
    }