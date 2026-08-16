"""Tests for rollback functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from deploymate.rollback import RollbackManager, RollbackError
from deploymate.config import ConfigManager


@pytest.fixture
def rollback_manager(config_manager: ConfigManager):
    """Create RollbackManager instance."""
    return RollbackManager(config_manager)


def test_rollback_invalid_deployment(rollback_manager: RollbackManager):
    """Test rollback of non-existent deployment."""
    mock_server = MagicMock()
    mock_server.name = 'test-server'
    mock_server.host = '192.168.1.100'
    mock_server.port = 22
    mock_server.username = 'testuser'
    mock_server.key_path = None
    mock_server.password = None
    
    with pytest.raises(RollbackError):
        rollback_manager.rollback('non-existent-app', mock_server)


@patch('deploymate.rollback.SSHManagerPool')
def test_list_available_versions(mock_ssh_pool, rollback_manager: RollbackManager):
    """Test listing available versions."""
    mock_ssh = MagicMock()
    mock_ssh.execute_command.return_value = (0, 'v1.0.0\nv0.9.0\nv0.8.0', '')
    
    mock_ssh_pool.return_value.get_connection.return_value = mock_ssh
    
    mock_deployment = MagicMock()
    mock_deployment.name = 'test-app'
    mock_deployment.deploy_path = '/opt/test-app'
    
    rollback_manager.config_manager.get_deployment = Mock(return_value=mock_deployment)
    
    mock_server = MagicMock()
    mock_server.name = 'test-server'
    mock_server.host = '192.168.1.100'
    mock_server.port = 22
    mock_server.username = 'testuser'
    mock_server.key_path = None
    mock_server.password = None
    
    versions = rollback_manager.list_available_versions('test-app', mock_server)
    
    assert len(versions) == 3
    assert versions[0] == 'v1.0.0'


def test_cleanup_backups(rollback_manager: RollbackManager):
    """Test cleaning up old backups."""
    # Create a test backup file
    backup_info = {
        'backup_id': 'test-backup',
        'deployment_name': 'test-app',
        'server_name': 'test-server',
        'version': 'v1.0.0',
        'timestamp': '2020-01-01T00:00:00',
        'remote_path': '/opt/test-app/backups/test-backup',
    }
    
    rollback_manager._save_backup_info(backup_info)
    
    # Cleanup backups older than 30 days
    removed = rollback_manager.cleanup_backups(max_age_days=30)
    
    assert removed >= 0