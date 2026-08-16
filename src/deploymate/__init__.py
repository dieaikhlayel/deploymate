"""DeployMate - DevOps Automation Tool."""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from deploymate.config import ConfigManager
from deploymate.deployer import Deployer
from deploymate.monitor import Monitor
from deploymate.alerter import AlertManager
from deploymate.rollback import RollbackManager

__all__ = [
    "ConfigManager",
    "Deployer",
    "Monitor",
    "AlertManager",
    "RollbackManager",
    "__version__",
]