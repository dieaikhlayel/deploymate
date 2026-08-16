#!/bin/bash

# Initialize Git repository for DeployMate

set -e

echo "🚀 Initializing Git repository for DeployMate..."

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "❌ Git is not installed"
    exit 1
fi

# Initialize git repository if not already initialized
if [ ! -d ".git" ]; then
    git init
    echo "✅ Git repository initialized"
else
    echo "ℹ️  Git repository already exists"
fi

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: DeployMate DevOps Automation Tool

Features:
- SSH connection management
- Automated deployments
- Server monitoring
- Alerting system (Slack/Email)
- Rollback support
- CLI interface
- Web dashboard
- Docker support

This is a professional DevOps automation tool for managing
deployments and monitoring server infrastructure."

echo "✅ Initial commit created"

# Create development branch
git checkout -b develop
echo "✅ Created develop branch"

# Switch back to main
git checkout main

echo ""
echo "Next steps:"
echo "1. Create a GitHub repository"
echo "2. Add remote: git remote add origin https://github.com/yourusername/deploymate.git"
echo "3. Push code: git push -u origin main develop"
echo "4. Set up GitHub Actions CI/CD"
echo "5. Configure branch protection rules"
echo "6. Invite collaborators"