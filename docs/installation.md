# Installation Guide

## Prerequisites

- Python 3.9 or higher
- Git
- SSH client
- Docker (optional)

## Installation Methods

### Method 1: From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/deploymate.git
cd deploymate

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Verify installation
deploymate --version
```

### Method 2: Using Docker
```bash
# Clone the repository
git clone https://github.com/yourusername/deploymate.git
cd deploymate

# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f
```

### Method 3: Using pip
```bash
# Install from PyPI (once published)
pip install deploymate
```

### Configuration
1. **Create configuration directory:**
```bash
mkdir -p configs
```

2. **Copy example configurations:**
```bash
cp configs/servers.yaml.example configs/servers.yaml
cp configs/deployments.yaml.example configs/deployments.yaml
cp configs/alerts.yaml.example configs/alerts.yaml
```

3. **Create environment file:**
```bash
cp .env.example .env
```

4. **Edit configurations as needed.**
    ## Verification
    ```bash
    # Check system info
deploymate info

# List servers
deploymate servers list

# Check server health
deploymate servers health-check

# Start web dashboard
deploymate web --port 5000
```
Access the web dashboard at http://localhost:5000.
```

### Troubleshooting
## SSH Connection Issues
- Ensure SSH keys are properly configured
- Check network connectivity
- Verify server credentials

## Permission Issues
- Ensure you have proper SSH access to target servers
- Check file permissions on SSH keys

## Docker Issues
- Check Docker daemon is running
- Verify port mappings
- Check container logs with docker-compose logs


### `docs/configuration.md`

```markdown
# Configuration Guide

## Server Configuration

Servers are defined in `configs/servers.yaml`:

```yaml
servers:
  - name: web-server-1
    host: 192.168.1.100
    port: 22
    username: deploy
    key_path: ~/.ssh/id_rsa
    tags:
      - web
      - production
    environment: production
    ```
```

### Fields
- name: Unique server name
- host: IP address or hostname
- port: SSH port (default: 22)
- username: SSH username
- key_path: Path to SSH private key
- password: SSH password (alternative to key)
- tags: List of tags for filtering
- environment: Environment name (production, staging, etc.)

### Deployment Configuration
## Deployments are defined in configs/deployments.yaml:
```bash
deployments:
  - name: web-app
    repository: git@github.com:company/web-app.git
    branch: main
    deploy_path: /var/www/web-app
    pre_deploy_commands:
      - "mkdir -p /var/www/web-app/releases"
    post_deploy_commands:
      - "systemctl restart web-app"
    environment_variables:
      APP_ENV: production
    health_check_url: "https://example.com/health"
    servers:
      - web-server-1
      - web-server-2
```

### Alert Configuration
## Alerts are configured in configs/alerts.yaml:
```bash
slack:
  enabled: true
  webhook_url: ${SLACK_WEBHOOK_URL}
  channel: "#deployments"

email:
  enabled: false
  smtp_host: ${SMTP_HOST}
  smtp_port: 587

notification_rules:
  on_deployment_success:
    - slack
  on_deployment_failure:
    - slack
    - email 
    ```


### Environment Variables
## Create a .env file with:
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-password
```

### Advanced Configuration
## SSH Options
Add to servers.yaml:
```yml
ssh_options:
  timeout: 30
  max_retries: 3
  retry_delay: 2
  ```

  ## Monitoring Thresholds
Configure in alerts.yaml:
```yml
thresholds:
  cpu_warning: 70
  cpu_critical: 90
  memory_warning: 75
  memory_critical: 85
  disk_warning: 70
  disk_critical: 80
  ```

  
### `docs/api.md`

```markdown
# API Reference

## CLI Commands

### Servers
```bash
# List servers
deploymate servers list

# Health check
deploymate servers health-check [SERVER_NAME]
```

## Deployments
```bash
# Deploy application
deploymate deploy run DEPLOYMENT_NAME [OPTIONS]

# Deployment history
deploymate deploy history
```

## Monitoring
```bash
# Start monitoring
deploymate monitor start [--interval SECONDS]

# Generate report
deploymate monitor report
```

## Rollback
```bash
# Rollback deployment
deploymate rollback run DEPLOYMENT_NAME --server SERVER [OPTIONS]

# List versions
deploymate rollback versions DEPLOYMENT_NAME --server SERVER
```

## Web Dashboard
```bash
# Start web dashboard
deploymate web [--host HOST] [--port PORT]
```

### REST API
## Base URL
 **http://localhost:5000**

 ### Endpoints
 ## Get Servers
GET /api/servers

Get Server Details
GET /api/servers/{server_name}

Deploy Application
POST /api/deploy
Content-Type: application/json

{
    "deployment_name": "web-app",
    "servers": ["server1", "server2"],
    "version": "v1.0.0",
    "force": false
}


Start Monitoring
POST /api/monitor/start
Content-Type: application/json

{
    "interval": 60
}

Get Monitoring Report
GET /api/monitor/report

Rollback Deployment
POST /api/rollback
Content-Type: application/json

{
    "deployment_name": "web-app",
    "server": "server1",
    "version": "v0.9.0"
}

Get Deployment History
GET /api/history

Python API
from deploymate.config import ConfigManager
from deploymate.deployer import Deployer

# Load configuration
config = ConfigManager('./configs')

# Create deployer
deployer = Deployer(config)

# Deploy application
results = deployer.deploy('web-app', ['server1', 'server2'])

# Monitor servers
from deploymate.monitor import Monitor
monitor = Monitor(config)
metrics = monitor.check_all_servers()