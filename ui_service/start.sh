#!/bin/sh

# Print environment for debugging
echo "================================================"
echo "[Startup Script] Environment variables:"
echo "AGENT_SERVICE_ADDRESS=${AGENT_SERVICE_ADDRESS:-NOT_SET}"
echo "NODE_ENV=${NODE_ENV:-NOT_SET}"
echo "PORT=${PORT:-NOT_SET}"
echo "HOSTNAME=${HOSTNAME:-NOT_SET}"
echo "================================================"
echo ""

# Start Next.js server
exec node server.js
