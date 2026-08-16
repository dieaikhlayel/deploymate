
### `CONTRIBUTING.md`

```markdown
# Contributing to DeployMate

We love your input! We want to make contributing to DeployMate as easy and transparent as possible.

## Development Process

1. Fork the repo and create your branch from `main`.
2. Make your changes.
3. Test your changes.
4. Submit a pull request.

## Code Style

- Follow PEP 8 guidelines
- Use type hints
- Write docstrings for all public functions
- Keep functions small and focused
- Write tests for new features

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=deploymate

# Run specific test file
pytest tests/test_config.py
```

Pull Request Process
Update the README.md with details of changes if needed

Update the docs with any new features

Ensure all tests pass

Ensure code passes linting (black, ruff, mypy)

The PR will be merged once reviewed and approved

Bug Reports
When filing an issue, please include:

A clear description

Steps to reproduce

Expected behavior

Actual behavior

Environment details (OS, Python version, etc.)

Feature Requests
We welcome feature requests! Please include:

Clear description of the feature

Use case

Potential implementation approach