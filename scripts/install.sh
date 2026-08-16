#!/bin/bash

# DeployMate Installation Script

set -e

echo "🚀 Installing DeployMate..."

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
required_version="3.9"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python 3.9 or higher is required (found $python_version)"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -e ".[dev]"

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p configs logs deployments backups

# Copy example configurations
if [ ! -f configs/servers.yaml ]; then
    cp configs/example.env .env.example
    echo "⚠️  Please configure your servers in configs/servers.yaml"
fi

# Set up pre-commit hooks
echo "🔧 Setting up pre-commit hooks..."
pre-commit install

echo "✅ DeployMate installed successfully!"
echo ""
echo "Next steps:"
echo "1. Configure your servers in configs/servers.yaml"
echo "2. Configure deployments in configs/deployments.yaml"
echo "3. Set up alerts in configs/alerts.yaml"
echo "4. Run 'deploymate --help' to see available commands"