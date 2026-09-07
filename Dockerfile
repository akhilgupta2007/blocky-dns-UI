FROM python:3.11-slim

LABEL maintainer="BlockyDNS Hub"
LABEL description="Lightweight Homelab DNS Manager and Web UI for Blocky"

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    CERTS_DIR=/app/certs \
    HTTP_PORT=3000 \
    HTTPS_PORT=3443

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server/ /app/server/
COPY public/ /app/public/
COPY config/ /app/config/
COPY entrypoint.sh /app/entrypoint.sh

# Create data and cert directories & make entrypoint executable
RUN mkdir -p /app/data /app/certs \
    && chmod +x /app/entrypoint.sh

EXPOSE 3000 3443

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -k -f https://127.0.0.1:3443/api/auth/status || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "server/main.py"]

