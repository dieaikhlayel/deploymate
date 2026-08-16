# Multi-stage build for DeployMate
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.11-slim

LABEL maintainer="your.email@example.com"
LABEL description="DeployMate - DevOps Automation Tool"
LABEL version="0.1.0"

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    openssh-client \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -r -s /bin/bash deploymate && \
    mkdir -p /app /configs /logs && \
    chown -R deploymate:deploymate /app /configs /logs

# Copy Python packages from builder
COPY --from=builder /root/.local /usr/local

WORKDIR /app

# Copy application
COPY . .

# Install the application
RUN pip install --no-cache-dir .

# Switch to non-root user
USER deploymate

# Expose web dashboard port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')" || exit 1

# Run the application
CMD ["deploymate", "web", "--host", "0.0.0.0", "--port", "5000"]