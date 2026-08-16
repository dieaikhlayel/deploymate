"""Flask web application for DeployMate dashboard."""

from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, render_template, request
from flask import send_from_directory

from deploymate.utils.logger import LoggerMixin


class WebDashboard(LoggerMixin):
    """Web dashboard for DeployMate."""
    
    def __init__(self, context: Any):
        """
        Initialize web dashboard.
        
        Args:
            context: Global context object with managers
        """
        self.context = context
        self.app = Flask(
            __name__,
            template_folder='templates',
            static_folder='static',
        )
        
        # Register routes
        self._register_routes()
    
    def _register_routes(self) -> None:
        """Register all routes."""
        
        @self.app.route('/')
        def index():
            """Dashboard home page."""
            return render_template('index.html')
        
        @self.app.route('/health')
        def health():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'version': '0.1.0',
                'timestamp': __import__('datetime').datetime.now().isoformat(),
            })
        
        @self.app.route('/api/servers')
        def api_servers():
            """Get all servers."""
            servers = [
                server.dict()
                for server in self.context.config_manager.servers
            ]
            return jsonify({'servers': servers})
        
        @self.app.route('/api/servers/<server_name>')
        def api_server_detail(server_name: str):
            """Get server details."""
            server = self.context.config_manager.get_server(server_name)
            if not server:
                return jsonify({'error': 'Server not found'}), 404
            
            # Get current metrics
            metrics = self.context.monitor.check_server_health(server)
            return jsonify({
                'server': server.dict(),
                'metrics': metrics.to_dict(),
            })
        
        @self.app.route('/api/deployments')
        def api_deployments():
            """Get all deployments."""
            deployments = [
                deployment.dict()
                for deployment in self.context.config_manager.deployments
            ]
            return jsonify({'deployments': deployments})
        
        @self.app.route('/api/deployments/<deployment_name>')
        def api_deployment_detail(deployment_name: str):
            """Get deployment details."""
            deployment = self.context.config_manager.get_deployment(deployment_name)
            if not deployment:
                return jsonify({'error': 'Deployment not found'}), 404
            
            return jsonify(deployment.dict())
        
        @self.app.route('/api/deploy', methods=['POST'])
        def api_deploy():
            """Deploy an application."""
            data = request.get_json()
            
            if not data or 'deployment_name' not in data:
                return jsonify({'error': 'Missing deployment_name'}), 400
            
            deployment_name = data['deployment_name']
            servers = data.get('servers', [])
            version = data.get('version')
            force = data.get('force', False)
            
            try:
                results = self.context.deployer.deploy(
                    deployment_name,
                    servers,
                    version,
                    force,
                )
                return jsonify({
                    'results': [result.to_dict() for result in results]
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/monitor/start', methods=['POST'])
        def api_start_monitoring():
            """Start monitoring."""
            data = request.get_json() or {}
            interval = data.get('interval', 60)
            
            self.context.monitor.check_interval = interval
            self.context.monitor.start_monitoring()
            
            return jsonify({'status': 'started', 'interval': interval})
        
        @self.app.route('/api/monitor/stop', methods=['POST'])
        def api_stop_monitoring():
            """Stop monitoring."""
            self.context.monitor.stop_monitoring()
            return jsonify({'status': 'stopped'})
        
        @self.app.route('/api/monitor/report')
        def api_monitor_report():
            """Get monitoring report."""
            self.context.monitor.check_all_servers()
            report = self.context.monitor.generate_report()
            return jsonify(report)
        
        @self.app.route('/api/monitor/alerts')
        def api_monitor_alerts():
            """Get current alerts."""
            alerts = self.context.monitor.get_alerts()
            return jsonify({'alerts': alerts})
        
        @self.app.route('/api/rollback', methods=['POST'])
        def api_rollback():
            """Rollback a deployment."""
            data = request.get_json()
            
            if not data or 'deployment_name' not in data or 'server' not in data:
                return jsonify({'error': 'Missing required fields'}), 400
            
            deployment_name = data['deployment_name']
            server_name = data['server']
            version = data.get('version')
            backup_id = data.get('backup_id')
            
            server = self.context.config_manager.get_server(server_name)
            if not server:
                return jsonify({'error': 'Server not found'}), 404
            
            try:
                success = self.context.rollback_manager.rollback(
                    deployment_name,
                    server,
                    version,
                    backup_id,
                )
                return jsonify({'success': success})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/history')
        def api_history():
            """Get deployment history."""
            history = self.context.deployer.get_deployment_history()
            return jsonify({'history': history})
        
        @self.app.route('/api/config')
        def api_config():
            """Get full configuration."""
            config = self.context.config_manager.to_dict()
            return jsonify(config)
    
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
        """
        Run the web dashboard.
        
        Args:
            host: Host to bind
            port: Port to bind
            debug: Enable debug mode
        """
        self.app.run(host=host, port=port, debug=debug)


def create_app(context: Any) -> Flask:
    """
    Create Flask application.
    
    Args:
        context: Global context object
    
    Returns:
        Flask application instance
    """
    dashboard = WebDashboard(context)
    return dashboard.app