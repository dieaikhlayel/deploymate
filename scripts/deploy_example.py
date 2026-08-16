#!/usr/bin/env python3
"""Example script demonstrating DeployMate usage."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from deploymate.config import ConfigManager
from deploymate.deployer import Deployer
from deploymate.monitor import Monitor
from deploymate.alerter import AlertManager
from deploymate.rollback import RollbackManager
from deploymate.utils.logger import setup_logger


def main():
    """Example deployment workflow."""
    # Setup logging
    logger = setup_logger(log_level="INFO")
    
    # Load configuration
    logger.info("Loading configuration...")
    config = ConfigManager("./configs")
    
    # Initialize managers
    deployer = Deployer(config)
    monitor = Monitor(config)
    alert_manager = AlertManager(config.alerts)
    rollback_manager = RollbackManager(config)
    
    # Check server health before deployment
    logger.info("Checking server health...")
    metrics_list = monitor.check_all_servers()
    
    for metrics in metrics_list:
        logger.info(f"Server: {metrics.server_name}, Status: {metrics.health_status}")
        if metrics.health_status != "healthy":
            logger.warning(f"Server {metrics.server_name} is not healthy!")
            alert_manager.notify_health_check_failure(
                metrics.server_name,
                metrics.to_dict(),
            )
    
    # Deploy application
    deployment_name = "web-app"
    logger.info(f"Starting deployment of {deployment_name}...")
    
    try:
        # Notify deployment start
        alert_manager.notify_deployment_started(
            deployment_name,
            "all",
            "latest",
        )
        
        # Perform deployment
        results = deployer.deploy(deployment_name)
        
        # Check results
        for result in results:
            if result.success:
                logger.info(f"✅ Deployment to {result.server_name} successful!")
                alert_manager.notify_deployment_success(
                    deployment_name,
                    result.server_name,
                    result.current_version,
                    result.duration,
                )
            else:
                logger.error(f"❌ Deployment to {result.server_name} failed: {result.error_message}")
                alert_manager.notify_deployment_failure(
                    deployment_name,
                    result.server_name,
                    result.error_message,
                )
                
                # Attempt rollback on failure
                logger.info(f"Attempting rollback on {result.server_name}...")
                server = config.get_server(result.server_name)
                if server:
                    try:
                        rollback_manager.rollback(
                            deployment_name,
                            server,
                            result.previous_version,
                        )
                        logger.info("Rollback successful!")
                    except Exception as rollback_error:
                        logger.error(f"Rollback failed: {rollback_error}")
        
        # Generate monitoring report
        logger.info("Generating monitoring report...")
        monitor.check_all_servers()
        report = monitor.generate_report()
        
        logger.info(f"Report Summary:")
        logger.info(f"  Total Servers: {report['summary']['total_servers']}")
        logger.info(f"  Healthy: {report['summary']['healthy_servers']}")
        logger.info(f"  Warning: {report['summary']['warning_servers']}")
        logger.info(f"  Critical: {report['summary']['critical_servers']}")
        
    except Exception as e:
        logger.error(f"Deployment workflow failed: {e}")
        alert_manager.notify_deployment_failure(
            deployment_name,
            "all",
            str(e),
        )
        sys.exit(1)
    
    logger.info("Deployment workflow completed!")


if __name__ == "__main__":
    main()