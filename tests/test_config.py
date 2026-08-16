"""Tests for configuration management."""

import pytest
from pathlib import Path

from deploymate.config import ConfigManager, ServerConfig, DeploymentConfig


def test_load_config(config_manager: ConfigManager):
    """Test loading configuration."""
    assert len(config_manager.servers) == 2
    assert len(config_manager.deployments) == 1
    assert config_manager.servers[0].name == 'test-server-1'


def test_get_server(config_manager: ConfigManager):
    """Test getting server by name."""
    server = config_manager.get_server('test-server-1')
    assert server is not None
    assert server.host == '192.168.1.100'
    
    # Test non-existent server
    assert config_manager.get_server('non-existent') is None


def test_get_deployment(config_manager: ConfigManager):
    """Test getting deployment by name."""
    deployment = config_manager.get_deployment('test-app')
    assert deployment is not None
    assert deployment.repository == 'git@github.com:test/test-app.git'
    
    # Test non-existent deployment
    assert config_manager.get_deployment('non-existent') is None


def test_get_servers_by_tag(config_manager: ConfigManager):
    """Test filtering servers by tag."""
    web_servers = config_manager.get_servers_by_tag('web')
    assert len(web_servers) == 1
    assert web_servers[0].name == 'test-server-1'
    
    db_servers = config_manager.get_servers_by_tag('db')
    assert len(db_servers) == 1
    assert db_servers[0].name == 'test-server-2'


def test_validate_deployment(config_manager: ConfigManager):
    """Test deployment validation."""
    errors = config_manager.validate_deployment('test-app')
    assert len(errors) == 0
    
    # Test non-existent deployment
    errors = config_manager.validate_deployment('non-existent')
    assert len(errors) > 0


def test_server_config_validation():
    """Test server configuration validation."""
    # Valid config
    server = ServerConfig(
        name='test',
        host='192.168.1.1',
        username='user',
    )
    assert server.port == 22
    
    # Invalid host
    with pytest.raises(ValueError):
        ServerConfig(
            name='test',
            host='invalid host',
            username='user',
        )
    
    # Invalid port
    with pytest.raises(ValueError):
        ServerConfig(
            name='test',
            host='192.168.1.1',
            username='user',
            port=99999,
        )