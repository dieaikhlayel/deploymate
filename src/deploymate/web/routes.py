"""Additional route handlers for the web dashboard."""

from typing import Any, Dict

from flask import jsonify, render_template, request


def register_dashboard_routes(app, context: Any) -> None:
    """
    Register additional dashboard routes.
    
    Args:
        app: Flask application
        context: Global context object
    """
    
    @app.route('/dashboard')
    def dashboard():
        """Main dashboard page."""
        return render_template('index.html')
    
    @app.route('/servers')
    def servers_page():
        """Servers page."""
        return render_template('servers.html')
    
    @app.route('/deployments')
    def deployments_page():
        """Deployments page."""
        return render_template('deployments.html')
    
    @app.route('/api/summary')
    def api_summary():
        """Get summary information for dashboard."""
        config_manager = context.config_manager
        
        # Get server count
        server_count = len(config_manager.servers)
        
        # Get deployment count
        deployment_count = len(config_manager.deployments)
        
        # Get recent deployments
        recent_deployments = context.deployer.get_deployment_history()[-5:]
        
        # Get monitoring status
        monitoring_active = context.monitor.is_running
        
        # Get alerts
        alerts = context.monitor.get_alerts()
        
        return jsonify({
            'server_count': server_count,
            'deployment_count': deployment_count,
            'recent_deployments': recent_deployments,
            'monitoring_active': monitoring_active,
            'alert_count': len(alerts),
            'alerts': alerts[:5],  # Last 5 alerts
        })