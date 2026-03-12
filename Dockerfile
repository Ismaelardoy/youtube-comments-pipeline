# Official Azure Functions Python 3.11 runtime
# This is the same base image used by Azure Cloud, guaranteeing local/cloud parity.
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

# Set the working directory inside the container
WORKDIR /home/site/wwwroot

# Install curl for Docker health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project files
COPY function_app.py .
COPY host.json .

# The Azure Functions runtime listens on port 7071 by default
EXPOSE 7071
