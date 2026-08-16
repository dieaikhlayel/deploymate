"""Tests for deployment functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from deploymate.deployer import Deployer, DeploymentError, DeploymentResult
from deploymate.config import ConfigManager


@pytest.fixture
def deployer(config_manager: ConfigManager):
    """Create a Deployer instance."""
    return Deployer(config_manager)


def test_deploy_invalid_deployment(deployer: Deployer):
    """Test deploying a non-existent deployment."""
    with pytest.raises(DeploymentError):
        deployer.deploy('non-existent-app')


def test_deploy_no_servers(deployer: Deployer):
    """Test deploying with no valid servers."""
    # Mock config manager to return no servers
    deployer.config_manager.get_deployment = Mock(return_value=Mock(
        name='test-app',
        servers=['non-existent-server'],
    ))
    deployer.config_manager.get_server = Mock(return_value=None)
    
    with pytest.raises(DeploymentError):
        deployer.deploy('test-app')


@patch('deploymate.deployer.SSHManagerPool')
def test_deploy_success(mock_ssh_pool, deployer: Deployer):
    """Test successful deployment."""
    # Mock SSH connection
    mock_ssh = MagicMock()
    mock_ssh.execute_command.return_value = (0, 'output', '')
    mock_ssh.execute_commands.return_value = [
        {'command': 'test', 'exit_code': 0, 'stdout': '', 'stderr': '', 'success': True}
    ]
    
    mock_ssh_pool.return_value.get_connection.return_value = mock_ssh
    
    # Mock config manager
    mock_deployment = MagicMock()
    mock_deployment.name = 'test-app'
    mock_deployment.repository = 'git@github.com:test/test-app.git'
    mock_deployment.branch = 'main'
    mock_deployment.deploy_path = '/opt/test-app'
    mock_deployment.pre_deploy_commands = []
    mock_deployment.post_deploy_commands = []
    mock_deployment.environment_variables = {}
    mock_deployment.health_check_url = None
    mock_deployment.health_check_timeout = 30
    mock_deployment.servers = ['test-server-1']
    
    mock_server = MagicMock()
    mock_server.name = 'test-server-1'
    mock_server.host = '192.168.1.100'
    mock_server.port = 22
    mock_server.username = 'testuser'
    mock_server.key_path = None
    mock_server.password = None
    
    deployer.config_manager.get_deployment = Mock(return_value=mock_deployment)
    deployer.config_manager.get_server = Mock(return_value=mock_server)
    deployer.config_manager.validate_deployment = Mock(return_value=[])
    
    # Deploy
    results = deployer.deploy('test-app')
    
    assert len(results) == 1
    assert results[0].success == True
    assert results[0].server_name == 'test-server-1'


def test_deployment_result():
    """Test DeploymentResult class."""
    result = DeploymentResult('test-app', 'test-server')
    
    assert result.deployment_name == 'test-app'
    assert result.server_name == 'test-server'
    assert result.success == False
    
    result.success = True
    result.end_time = datetime.now()
    
    assert result.duration >= 0
    assert result.to_dict()['success'] == True


@patch('deploymate.deployer.requests.get')
def test_health_check_success(mock_requests_get, deployer: Deployer):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_requests_get.return_value = mock_response
    
    result = deployer._perform_health_check('http://localhost:8080/health', 10)
    
    assert result == True
    mock_requests_get.assert_called_once_with('http://localhost:8080/health', timeout=10)


@patch('deploymate.deployer.requests.get')
def test_health_check_failure(mock_requests_get, deployer: Deployer):
    """Test failed health check."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_requests_get.return_value = mock_response
    
    result = deployer._perform_health_check('http://localhost:8080/health', 10)
    
    assert result == False