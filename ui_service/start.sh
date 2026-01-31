#!/bin/sh

# Print environment for debugging
echo "================================================"
echo "[Startup Script] Environment variables:"
echo "AGENT_SERVICE_ADDRESS=${AGENT_SERVICE_ADDRESS:-NOT_SET}"
echo "ENV_FILE_PATH=${ENV_FILE_PATH:-NOT_SET}"
echo "CONVERSATIONS_DIR=${CONVERSATIONS_DIR:-NOT_SET}"
echo "NODE_ENV=${NODE_ENV:-NOT_SET}"
echo "PORT=${PORT:-NOT_SET}"
echo "HOSTNAME=${HOSTNAME:-NOT_SET}"
echo "================================================"

# Check if env file exists
if [ -f "${ENV_FILE_PATH}" ]; then
    echo "[Startup Script] ENV file found at: ${ENV_FILE_PATH}"
else
    echo "[Startup Script] WARNING: ENV file not found at: ${ENV_FILE_PATH}"
    # Create empty env file if it doesn't exist
    mkdir -p $(dirname "${ENV_FILE_PATH}")
    touch "${ENV_FILE_PATH}"
    echo "[Startup Script] Created empty ENV file"
fi
echo ""

# Start Next.js server
exec node server.js
