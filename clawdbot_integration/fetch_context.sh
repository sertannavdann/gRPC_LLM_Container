#!/bin/bash
# Fetch context from dashboard
# This is a placeholder for the integration script
curl -s http://dashboard:8001/api/context?user_id=${1:-default}
