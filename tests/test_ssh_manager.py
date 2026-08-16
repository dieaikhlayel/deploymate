"""Tests for SSH manager."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from deploymate.ssh_manager import SSHManager, SSHConnectionError, SSHCommandError


@pytest.fixture
def ssh_manager():
    """Create SSH manager instance."""
    return SSHManager(
        host='test-host',
        username='testuser',
        port=22,
        key_path=None,
        password=None,
        timeout=5,
        max_retries=1,
        retry_delay=0,
    )


@patch('deploymate.ssh_manager.paramiko.SSHClient')
def test_connect_success(mock_ssh_client, ssh_manager):
    """Test successful SSH connection."""
    mock_client_instance = MagicMock()
    mock_ssh_client.return_value = mock_client_instance
    
    ssh_manager.connect()
    
    assert ssh_manager._connected == True
    assert ssh_manager._client is not None


@patch('deploymate.ssh_manager.paramiko.SSHClient')
def test_connect_failure(mock_ssh_client, ssh_manager):
    """Test SSH connection failure."""
    from paramiko.ssh_exception import AuthenticationException
    
    mock_client_instance = MagicMock()
    mock_client_instance.connect.side_effect = AuthenticationException('Auth failed')
    mock_ssh_client.return_value = mock_client_instance
    
    with pytest.raises(SSHConnectionError):
        ssh_manager.connect()


@patch('deploymate.ssh_manager.paramiko.SSHClient')
def test_execute_command(mock_ssh_client, ssh_manager):
    """Test command execution."""
    mock_client_instance = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    mock_stdin = MagicMock()
    
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b'command output'
    mock_stderr.read.return_value = b''
    
    mock_client_instance.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
    mock_ssh_client.return_value = mock_client_instance
    
    ssh_manager.connect()
    
    exit_code, stdout, stderr = ssh_manager.execute_command('ls -la')
    
    assert exit_code == 0
    assert stdout == 'command output'
    assert stderr == ''


def test_execute_command_not_connected(ssh_manager):
    """Test command execution when not connected."""
    with pytest.raises(SSHCommandError):
        ssh_manager.execute_command('ls')