"""Tests for alerting functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from deploymate.alerter import AlertManager
from deploymate.config import AlertConfig


@pytest.fixture
def alert_config():
    """Create alert configuration."""
    return AlertConfig(
        slack={
            'enabled': False,
            'webhook_url': None,
            'channel': '#test',
        },
        email={
            'enabled': False,
        },
        notification_rules={
            'on_deployment_start': ['slack'],
            'on_deployment_success': ['slack'],
            'on_deployment_failure': ['slack', 'email'],
        }
    )


@pytest.fixture
def alert_manager(alert_config):
    """Create AlertManager instance."""
    return AlertManager(alert_config)


def test_send_alert_no_channels(alert_manager):
    """Test sending alert with no channels configured."""
    results = alert_manager.send_alert('Test', 'Test message', 'info', [])
    assert results == {}


def test_get_severity_color(alert_manager):
    """Test severity color mapping."""
    assert alert_manager._get_severity_color('info') == '#36a64f'
    assert alert_manager._get_severity_color('warning') == '#ffcc00'
    assert alert_manager._get_severity_color('error') == '#ff0000'
    assert alert_manager._get_severity_color('critical') == '#8b0000'
    assert alert_manager._get_severity_color('unknown') == '#808080'


@patch('deploymate.alerter.requests.post')
def test_send_slack_alert(mock_post, alert_manager):
    """Test sending Slack alert."""
    # Enable Slack
    alert_manager.alert_config.slack['enabled'] = True
    alert_manager.alert_config.slack['webhook_url'] = 'https://hooks.slack.com/test'
    
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response
    
    result = alert_manager._send_slack_alert('Test', 'Test message', 'info')
    
    assert result == True
    mock_post.assert_called_once()


def test_notify_deployment_started(alert_manager):
    """Test deployment started notification."""
    # This should not raise any errors
    alert_manager.notify_deployment_started('test-app', 'test-server', 'v1.0.0')


def test_notify_deployment_success(alert_manager):
    """Test deployment success notification."""
    # This should not raise any errors
    alert_manager.notify_deployment_success('test-app', 'test-server', 'v1.0.0', 10.5)