"""Command-line interface for DeployMate."""

import json
import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich import print as rprint

from deploymate.config import ConfigManager
from deploymate.deployer import Deployer
from deploymate.monitor import Monitor
from deploymate.alerter import AlertManager
from deploymate.rollback import RollbackManager
from deploymate.utils.logger import setup_logger

# Initialize console for rich output
console = Console()

# Global context
class Context:
    """Global context for CLI commands."""
    
    def __init__(self):
        self.config_manager: Optional[ConfigManager] = None
        self.deployer: Optional[Deployer] = None
        self.monitor: Optional[Monitor] = None
        self.alert_manager: Optional[AlertManager] = None
        self.rollback_manager: Optional[RollbackManager] = None
        self.logger = None


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    '--config-dir',
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default='./configs',
    help='Configuration directory path',
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
    default='INFO',
    help='Logging level',
)
@click.option(
    '--log-file',
    type=click.Path(dir_okay=False),
    default=None,
    help='Log file path',
)
@click.pass_context
def main(ctx, config_dir, log_level, log_file):
    """DeployMate - DevOps Automation Tool"""
    # Setup logging
    logger = setup_logger(
        log_level=log_level,
        log_file=Path(log_file) if log_file else None,
    )
    
    # Initialize context
    ctx.obj = Context()
    ctx.obj.logger = logger
    
    # Load configuration
    try:
        ctx.obj.config_manager = ConfigManager(config_dir)
        logger.info(f"Loaded configuration from {config_dir}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Initialize managers
    ctx.obj.deployer = Deployer(ctx.obj.config_manager)
    ctx.obj.monitor = Monitor(ctx.obj.config_manager)
    ctx.obj.alert_manager = AlertManager(ctx.obj.config_manager.alerts)
    ctx.obj.rollback_manager = RollbackManager(ctx.obj.config_manager)


@main.group()
def servers():
    """Manage servers."""
    pass


@servers.command(name='list')
@click.pass_context
def list_servers(ctx):
    """List all configured servers."""
    config_manager = ctx.obj.config_manager
    
    table = Table(title="Configured Servers")
    table.add_column("Name", style="cyan")
    table.add_column("Host", style="green")
    table.add_column("Port", justify="right")
    table.add_column("Username", style="yellow")
    table.add_column("Environment", style="magenta")
    table.add_column("Tags", style="blue")
    
    for server in config_manager.servers:
        table.add_row(
            server.name,
            server.host,
            str(server.port),
            server.username,
            server.environment,
            ", ".join(server.tags) if server.tags else "-",
        )
    
    console.print(table)


@servers.command(name='health-check')
@click.argument('server_name', required=False)
@click.pass_context
def health_check(ctx, server_name):
    """Check health of servers."""
    monitor = ctx.obj.monitor
    config_manager = ctx.obj.config_manager
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        if server_name:
            server = config_manager.get_server(server_name)
            if not server:
                console.print(f"[red]Server '{server_name}' not found[/red]")
                return
            
            task = progress.add_task(f"Checking {server_name}...", total=None)
            metrics = monitor.check_server_health(server)
            progress.update(task, completed=True)
            
            # Display results
            table = Table(title=f"Health Check: {server_name}")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Status", metrics.health_status)
            table.add_row("CPU Usage", f"{metrics.cpu_usage:.1f}%")
            table.add_row("Memory Usage", f"{metrics.memory_usage:.1f}%")
            table.add_row("Disk Usage", f"{metrics.disk_usage:.1f}%")
            table.add_row("Load Average", ", ".join(f"{x:.2f}" for x in metrics.load_average) if metrics.load_average else "N/A")
            table.add_row("Uptime", metrics.uptime)
            table.add_row("Processes", str(metrics.processes))
            
            console.print(table)
        else:
            task = progress.add_task("Checking all servers...", total=None)
            metrics_list = monitor.check_all_servers()
            progress.update(task, completed=True)
            
            # Display results
            table = Table(title="Server Health Status")
            table.add_column("Server", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("CPU", justify="right")
            table.add_column("Memory", justify="right")
            table.add_column("Disk", justify="right")
            
            for metrics in metrics_list:
                status_color = "green" if metrics.health_status == "healthy" else "red"
                table.add_row(
                    metrics.server_name,
                    f"[{status_color}]{metrics.health_status}[/{status_color}]",
                    f"{metrics.cpu_usage:.1f}%",
                    f"{metrics.memory_usage:.1f}%",
                    f"{metrics.disk_usage:.1f}%",
                )
            
            console.print(table)


@main.group()
def deploy():
    """Deploy applications."""
    pass


@deploy.command(name='run')
@click.argument('deployment_name')
@click.option('--servers', '-s', multiple=True, help='Target servers')
@click.option('--version', '-v', help='Version to deploy')
@click.option('--force', is_flag=True, help='Force deployment')
@click.pass_context
def run_deployment(ctx, deployment_name, servers, version, force):
    """Deploy an application."""
    deployer = ctx.obj.deployer
    alert_manager = ctx.obj.alert_manager
    
    console.print(Panel(f"Deploying [bold]{deployment_name}[/bold]", style="blue"))
    
    # Notify deployment start
    alert_manager.notify_deployment_started(
        deployment_name,
        ", ".join(servers) if servers else "all",
        version or "latest",
    )
    
    try:
        results = deployer.deploy(
            deployment_name,
            list(servers) if servers else None,
            version,
            force,
        )
        
        # Display results
        table = Table(title=f"Deployment Results: {deployment_name}")
        table.add_column("Server", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Version", style="yellow")
        table.add_column("Duration", justify="right")
        table.add_column("Health Check", style="magenta")
        
        for result in results:
            status_color = "green" if result.success else "red"
            health_color = "green" if result.health_check_passed else "yellow"
            table.add_row(
                result.server_name,
                f"[{status_color}]{'Success' if result.success else 'Failed'}[/{status_color}]",
                result.current_version or "N/A",
                f"{result.duration:.2f}s",
                f"[{health_color}]{'Passed' if result.health_check_passed else 'N/A'}[/{health_color}]",
            )
        
        console.print(table)
        
        # Send notifications
        for result in results:
            if result.success:
                alert_manager.notify_deployment_success(
                    deployment_name,
                    result.server_name,
                    result.current_version,
                    result.duration,
                )
            else:
                alert_manager.notify_deployment_failure(
                    deployment_name,
                    result.server_name,
                    result.error_message or "Unknown error",
                )
        
    except Exception as e:
        console.print(f"[red]Deployment failed: {e}[/red]")
        alert_manager.notify_deployment_failure(
            deployment_name,
            "all",
            str(e),
        )
        sys.exit(1)


@deploy.command(name='history')
@click.pass_context
def deployment_history(ctx):
    """Show deployment history."""
    deployer = ctx.obj.deployer
    
    history = deployer.get_deployment_history()
    
    if not history:
        console.print("[yellow]No deployment history found[/yellow]")
        return
    
    table = Table(title="Deployment History")
    table.add_column("Deployment", style="cyan")
    table.add_column("Server", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Version", style="magenta")
    table.add_column("Duration", justify="right")
    table.add_column("Started", style="blue")
    
    for entry in history[-20:]:  # Show last 20 entries
        status_color = "green" if entry['success'] else "red"
        table.add_row(
            entry['deployment_name'],
            entry['server_name'],
            f"[{status_color}]{'Success' if entry['success'] else 'Failed'}[/{status_color}]",
            entry.get('current_version', 'N/A'),
            f"{entry.get('duration', 0):.2f}s",
            entry['start_time'][:19],
        )
    
    console.print(table)


@main.group()
def monitor():
    """Monitor servers."""
    pass


@monitor.command(name='start')
@click.option('--interval', type=int, default=60, help='Check interval in seconds')
@click.pass_context
def start_monitoring(ctx, interval):
    """Start continuous monitoring."""
    monitor = ctx.obj.monitor
    monitor.check_interval = interval
    
    console.print(f"[green]Starting monitoring with {interval}s interval...[/green]")
    monitor.start_monitoring()
    
    try:
        while True:
            click.pause()
    except KeyboardInterrupt:
        monitor.stop_monitoring()
        console.print("\n[yellow]Monitoring stopped[/yellow]")


@monitor.command(name='report')
@click.pass_context
def monitoring_report(ctx):
    """Generate monitoring report."""
    monitor = ctx.obj.monitor
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating report...", total=None)
        monitor.check_all_servers()
        report = monitor.generate_report()
        progress.update(task, completed=True)
    
    # Display summary
    summary = report['summary']
    console.print(Panel(
        f"Total Servers: {summary['total_servers']}\n"
        f"Healthy: [green]{summary['healthy_servers']}[/green]\n"
        f"Warning: [yellow]{summary['warning_servers']}[/yellow]\n"
        f"Critical: [red]{summary['critical_servers']}[/red]",
        title="Monitoring Summary",
        border_style="blue"
    ))
    
    # Display detailed report
    table = Table(title="Server Details")
    table.add_column("Server", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("CPU", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("Disk", justify="right")
    
    for server in report['servers']:
        status_color = {
            'healthy': 'green',
            'warning': 'yellow',
            'critical': 'red',
        }.get(server['status'], 'white')
        
        table.add_row(
            server['server_name'],
            f"[{status_color}]{server['status'].upper()}[/{status_color}]",
            f"{server.get('cpu_usage', 0):.1f}%",
            f"{server.get('memory_usage', 0):.1f}%",
            f"{server.get('disk_usage', 0):.1f}%",
        )
    
    console.print(table)


@main.group()
def rollback():
    """Manage rollbacks."""
    pass


@rollback.command(name='run')
@click.argument('deployment_name')
@click.option('--server', '-s', required=True, help='Server name')
@click.option('--version', '-v', help='Target version')
@click.option('--backup-id', '-b', help='Backup ID')
@click.pass_context
def run_rollback(ctx, deployment_name, server, version, backup_id):
    """Rollback a deployment."""
    rollback_manager = ctx.obj.rollback_manager
    config_manager = ctx.obj.config_manager
    alert_manager = ctx.obj.alert_manager
    
    server_config = config_manager.get_server(server)
    if not server_config:
        console.print(f"[red]Server '{server}' not found[/red]")
        sys.exit(1)
    
    console.print(f"Rolling back [bold]{deployment_name}[/bold] on [bold]{server}[/bold]")
    
    try:
        success = rollback_manager.rollback(
            deployment_name,
            server_config,
            version,
            backup_id,
        )
        
        if success:
            console.print(f"[green]Rollback successful![/green]")
            alert_manager.notify_rollback(
                deployment_name,
                server,
                "current",
                version or "previous",
            )
        else:
            console.print("[red]Rollback failed[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Rollback failed: {e}[/red]")
        sys.exit(1)


@rollback.command(name='versions')
@click.argument('deployment_name')
@click.option('--server', '-s', required=True, help='Server name')
@click.pass_context
def list_versions(ctx, deployment_name, server):
    """List available versions for rollback."""
    rollback_manager = ctx.obj.rollback_manager
    config_manager = ctx.obj.config_manager
    
    server_config = config_manager.get_server(server)
    if not server_config:
        console.print(f"[red]Server '{server}' not found[/red]")
        return
    
    versions = rollback_manager.list_available_versions(deployment_name, server_config)
    
    if not versions:
        console.print("[yellow]No versions available[/yellow]")
        return
    
    table = Table(title=f"Available Versions: {deployment_name} on {server}")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Version", style="green")
    
    for i, version in enumerate(versions, 1):
        table.add_row(str(i), version)
    
    console.print(table)


@main.command()
@click.option('--host', default='0.0.0.0', help='Host to bind')
@click.option('--port', default=5000, help='Port to bind')
@click.pass_context
def web(ctx, host, port):
    """Start web dashboard."""
    try:
        from deploymate.web.app import create_app
        
        app = create_app(ctx.obj)
        
        console.print(f"[green]Starting web dashboard on http://{host}:{port}[/green]")
        app.run(host=host, port=port, debug=False)
        
    except ImportError as e:
        console.print(f"[red]Failed to start web dashboard: {e}[/red]")
        console.print("[yellow]Make sure Flask is installed: pip install flask[/yellow]")
        sys.exit(1)


@main.command()
@click.pass_context
def info(ctx):
    """Show system information."""
    config_manager = ctx.obj.config_manager
    
    console.print(Panel(
        f"[bold]DeployMate[/bold] v0.1.0\n"
        f"Config Directory: {config_manager.config_dir}\n"
        f"Servers: {len(config_manager.servers)}\n"
        f"Deployments: {len(config_manager.deployments)}\n"
        f"Alerts: Slack {'✓' if config_manager.alerts.slack.get('enabled') else '✗'} | "
        f"Email {'✓' if config_manager.alerts.email.get('enabled') else '✗'}",
        title="System Information",
        border_style="blue"
    ))


if __name__ == '__main__':
    main()