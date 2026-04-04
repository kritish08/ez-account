FROM python:3.11-slim

# Install only what's needed for MongoDB + S3 + AES
RUN pip install --no-cache-dir \
    pymongo[srv] \
    dnspython \
    boto3 \
    cryptography

WORKDIR /app
COPY backup.py .

# Cron: run backup daily at 2:00 AM UTC
RUN apt-get update && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/* \
    && echo "0 2 * * * root python3 /app/backup.py >> /var/log/backup.log 2>&1" > /etc/cron.d/ez-backup \
    && chmod 0644 /etc/cron.d/ez-backup \
    && touch /var/log/backup.log

# Forward cron output to stdout for docker compose logs visibility
CMD ["sh", "-c", "cron && tail -f /var/log/backup.log"]
