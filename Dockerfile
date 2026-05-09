# =============================================================================
# Dockerfile — API Health Check Monitor
# =============================================================================
# Build:   docker build -t api-health-monitor .
# Run:     docker run -p 5000:5000 api-health-monitor
# =============================================================================

# Use official slim Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements first (Docker layer caching — only reinstalls if requirements change)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files into the container
COPY . .

# Expose Flask dashboard port
EXPOSE 5000

# Environment variables (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1

# Start the monitor + dashboard
CMD ["python", "main.py"]
