#!/bin/sh
# ============================================================
# EZ Account — Automated Daily Backup Script
# Calls the in-app /api/backup/create endpoint to trigger
# an encrypted S3 backup. Runs once a day via cron.
# ============================================================

set -e

# Determine the backend URL (defaults to internal Docker service name)
BACKEND_URL="${BACKUP_TARGET_URL:-http://backend:8001}"
LOG_PREFIX="[EZ-Backup $(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX Starting daily backup..."

# Try to log in and get a token
LOGIN_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${BACKUP_USER_EMAIL}\",\"password\":\"${BACKUP_USER_PASSWORD}\"}")

TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | sed 's/"access_token":"//;s/"//')

if [ -z "$TOKEN" ]; then
  echo "$LOG_PREFIX ERROR: Could not obtain auth token. Check BACKUP_USER_EMAIL and BACKUP_USER_PASSWORD."
  exit 1
fi

# Trigger the backup
BACKUP_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/backup/create" \
  -H "Authorization: Bearer ${TOKEN}")

echo "$LOG_PREFIX Backup response: $BACKUP_RESPONSE"
echo "$LOG_PREFIX Done."
