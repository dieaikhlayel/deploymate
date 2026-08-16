"""Validation utilities for DeployMate."""

import ipaddress
import re
from pathlib import Path
from typing import Union
from urllib.parse import urlparse


def validate_host(host: str) -> bool:
    """
    Validate if a string is a valid hostname or IP address.
    
    Args:
        host: Hostname or IP address to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not host:
        return False
    
    # Check if it's an IP address
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    
    # Check if it's a valid hostname
    hostname_pattern = re.compile(
        r'^(?=.{1,253}$)(?!-)[A-Z\d-]{1,63}(?<!-)'
        r'(\.(?!-)[A-Z\d-]{1,63}(?<!-))*\.?$',
        re.IGNORECASE
    )
    
    return bool(hostname_pattern.match(host))


def validate_port(port: Union[int, str]) -> bool:
    """
    Validate if a port number is valid.
    
    Args:
        port: Port number to validate
    
    Returns:
        True if valid (1-65535), False otherwise
    """
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except (ValueError, TypeError):
        return False


def validate_path(path: str) -> bool:
    """
    Validate if a path is a valid absolute Unix path.
    
    Args:
        path: Path to validate
    
    Returns:
        True if valid absolute path, False otherwise
    """
    if not path:
        return False
    
    # Check for absolute path
    if not path.startswith('/'):
        return False
    
    # Check for invalid characters
    invalid_chars = ['\0', '\n', '\r']
    if any(char in path for char in invalid_chars):
        return False
    
    # Check for path traversal
    if '..' in path.split('/'):
        return False
    
    return True


def validate_repository_url(url: str) -> bool:
    """
    Validate if a string is a valid Git repository URL.
    
    Args:
        url: Repository URL to validate
    
    Returns:
        True if valid repository URL, False otherwise
    """
    if not url:
        return False
    
    # Check for SSH format (git@host:repo)
    ssh_pattern = re.compile(
        r'^git@[\w.-]+:[\w./-]+\.git$'
    )
    if ssh_pattern.match(url):
        return True
    
    # Check for HTTPS format
    try:
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            return bool(parsed.netloc and parsed.path)
    except ValueError:
        pass
    
    return False


def validate_environment_variables(env_vars: dict) -> bool:
    """
    Validate environment variables dictionary.
    
    Args:
        env_vars: Dictionary of environment variables
    
    Returns:
        True if all variables are valid, False otherwise
    """
    if not isinstance(env_vars, dict):
        return False
    
    for key, value in env_vars.items():
        # Validate key
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
            return False
        
        # Validate value
        if not isinstance(value, (str, int, float, bool)):
            return False
    
    return True


def validate_health_check_url(url: str) -> bool:
    """
    Validate health check URL.
    
    Args:
        url: URL to validate
    
    Returns:
        True if valid URL, False otherwise
    """
    if not url:
        return True  # Empty URL is valid (no health check)
    
    try:
        parsed = urlparse(url)
        return all([parsed.scheme in ('http', 'https'), parsed.netloc])
    except ValueError:
        return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to be safe for filesystem operations.
    
    Args:
        filename: Original filename
    
    Returns:
        Sanitized filename
    """
    # Remove any directory components
    filename = Path(filename).name
    
    # Replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')
    
    # Ensure non-empty filename
    if not filename:
        filename = 'unnamed'
    
    return filename