# SUMO AI Web Application Container
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Web Application port
EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

# Start SUMO AI Web Application
CMD ["python", "web_app.py", "--host", "0.0.0.0", "--port", "8000"]
