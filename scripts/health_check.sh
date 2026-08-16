#!/bin/bash

# DeployMate Health Check Script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Running DeployMate Health Check..."

# Check Python
if command -v python3 &> /dev/null; then
    echo -e "${GREEN}✓${NC} Python 3 found"
else
    echo -e "${RED}✗${NC} Python 3 not found"
    exit 1
fi

# Check required packages
echo "Checking required packages..."
python3 -c "import paramiko" 2>/dev/null && echo -e "${GREEN}✓${NC} paramiko" || echo -e "${RED}✗${NC} paramiko"
python3 -c "import yaml" 2>/dev/null && echo -e "${GREEN}✓${NC} pyyaml" || echo -e "${RED}✗${NC} pyyaml"
python3 -c "import click" 2>/dev/null && echo -e "${GREEN}✓${NC} click" || echo -e "${RED}✗${NC} click"
python3 -c "import flask" 2>/dev/null && echo -e "${GREEN}✓${NC} flask" || echo -e "${RED}✗${NC} flask"

# Check configuration
echo "Checking configuration..."
if [ -d "configs" ]; then
    echo -e "${GREEN}✓${NC} configs directory exists"
else
    echo -e "${RED}✗${NC} configs directory missing"
fi

if [ -f "configs/servers.yaml" ]; then
    echo -e "${GREEN}✓${NC} servers.yaml found"
else
    echo -e "${YELLOW}!${NC} servers.yaml not found (required)"
fi

if [ -f "configs/deployments.yaml" ]; then
    echo -e "${GREEN}✓${NC} deployments.yaml found"
else
    echo -e "${YELLOW}!${NC} deployments.yaml not found (optional)"
fi

# Check SSH
echo "Checking SSH..."
if command -v ssh &> /dev/null; then
    echo -e "${GREEN}✓${NC} SSH client found"
else
    echo -e "${RED}✗${NC} SSH client not found"
fi

# Check Git
if command -v git &> /dev/null; then
    echo -e "${GREEN}✓${NC} Git found"
else
    echo -e "${RED}✗${NC} Git not found (required for deployments)"
fi

echo ""
echo "Health check completed!"