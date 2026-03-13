# Official Azure Functions Python 3.11 runtime
# Same base image used by Azure Cloud — guarantees local/cloud parity.
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

# Set the working directory inside the container
WORKDIR /home/site/wwwroot

# Install curl for Docker health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (maximises Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared business-logic package
COPY src/ ./src/

# Copy the Azure Functions entrypoint and runtime config
COPY function_app.py .
COPY host.json .

# The Azure Functions runtime (mcr image) listens on port 80 inside Docker.
EXPOSE 80
