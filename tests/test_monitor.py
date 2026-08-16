"""Tests for monitoring functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from deploymate.monitor import Monitor, ServerMetrics
from deploymate.config import ConfigManager


@pytest.fixture
def monitor(config_manager: ConfigManager):
    """Create a Monitor instance."""
    return Monitor(config_manager)


def test_server_metrics():
    """Test ServerMetrics class."""
    metrics = ServerMetrics('test-server')
    
    assert metrics.server_name == 'test-server'
    assert metrics.health_status == 'unknown'
    assert metrics.cpu_usage == 0.0
    assert metrics.memory_usage == 0.0
    
    metrics_dict = metrics.to_dict()
    assert metrics_dict['server_name'] == 'test-server'
    assert 'timestamp' in metrics_dict


@patch('deploymate.monitor.SSHManagerPool')
def test_check_server_health(mock_ssh_pool, monitor: Monitor):
    """Test health check."""
    mock_ssh = MagicMock()
    mock_ssh.check_connection.return_value = True
    mock_ssh.execute_command.return_value = (0, '10.5', '')
    
    mock_ssh_pool.return_value.get_connection.return_value = mock_ssh
    
    # Mock server
    mock_server = MagicMock()
    mock_server.name = 'test-server'
    mock_server.host = '192.168.1.100'
    mock_server.port = 22
    mock_server.username = 'testuser'
    mock_server.key_path = None
    mock_server.password = None
    
    metrics = monitor.check_server_health(mock_server)
    
    assert metrics.server_name == 'test-server'
    assert metrics.health_status == 'healthy'


@patch('deploymate.monitor.SSHManagerPool')
def test_check_server_unreachable(mock_ssh_pool, monitor: Monitor):
    """Test health check for unreachable server."""
    mock_ssh = MagicMock()
    mock_ssh.check_connection.return_value = False
    
    mock_ssh_pool.return_value.get_connection.return_value = mock_ssh
    
    mock_server = MagicMock()
    mock_server.name = 'test-server'
    mock_server.host = '192.168.1.100'
    mock_server.port = 22
    mock_server.username = 'testuser'
    mock_server.key_path = None
    mock_server.password = None
    
    metrics = monitor.check_server_health(mock_server)
    
    assert metrics.health_status == 'unreachable'


def test_get_alerts(monitor: Monitor):
    """Test getting alerts."""
    # Add test metrics to history
    metrics = ServerMetrics('test-server')
    metrics.cpu_usage = 95.0
    metrics.memory_usage = 90.0
    metrics.disk_usage = 85.0
    metrics.health_status = 'unhealthy'
    
    monitor.metrics_history.append(metrics)
    
    alerts = monitor.get_alerts()
    
    assert len(alerts) > 0
    assert any(alert['type'] == 'high_cpu' for alert in alerts)
    assert any(alert['type'] == 'high_memory' for alert in alerts)
    assert any(alert['type'] == 'health_check_failed' for alert in alerts)


def test_generate_report(monitor: Monitor):
    """Test generating report."""
    # Add test metrics
    metrics = ServerMetrics('test-server')
    metrics.health_status = 'healthy'
    metrics.cpu_usage = 10.0
    metrics.memory_usage = 20.0
    metrics.disk_usage = 30.0
    
    monitor.metrics_history.append(metrics)
    
    report = monitor.generate_report()
    
    assert 'timestamp' in report
    assert 'servers' in report
    assert 'summary' in report
    assert report['summary']['total_servers'] > 0