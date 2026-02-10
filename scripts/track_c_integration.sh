#!/bin/bash
# Track C: Integration Tasks - OAuth Adapters, MCP Bridge
# Skill: integration_expert.md

set -e
cd "$(dirname "$0")/.."

echo "═══════════════════════════════════════════════════════════"
echo "  Track C: Integration & Adapters"
echo "═══════════════════════════════════════════════════════════"

# C1. Google Calendar OAuth Adapter
echo ""
echo "▶ C1. Google Calendar OAuth Adapter Status"
echo "─────────────────────────────────────────────────────────────"
if [ -f "shared/adapters/calendar/google_calendar.py" ]; then
    echo "  ✅ google_calendar.py adapter exists"
else
    echo "  ❌ google_calendar.py adapter NOT FOUND"
fi

# Check adapter structure
echo "  Adapter directory structure:"
ls -la shared/adapters/calendar/ 2>/dev/null || echo "    Directory not found"

# C2. MCP Bridge Enhancement
echo ""
echo "▶ C2. MCP Bridge Status"
echo "─────────────────────────────────────────────────────────────"
if [ -f "bridge_service/mcp_server.py" ]; then
    echo "  ✅ mcp_server.py exists"
    # Count tools
    grep -c "@tool\|def tool_" bridge_service/mcp_server.py 2>/dev/null | xargs -I{} echo "    Tools defined: {}" || echo "    Could not count tools"
    
    # Check for Pydantic validation
    if grep -q "pydantic\|BaseModel" bridge_service/mcp_server.py 2>/dev/null; then
        echo "    ✅ Pydantic validation present"
    else
        echo "    ❌ Pydantic validation NOT present"
    fi
    
    # Check for rate limiting
    if grep -q "AsyncLimiter\|rate_limit" bridge_service/mcp_server.py 2>/dev/null; then
        echo "    ✅ Rate limiting present"
    else
        echo "    ❌ Rate limiting NOT present"
    fi
else
    echo "  ❌ mcp_server.py NOT FOUND"
fi

# Test MCP endpoint
echo ""
echo "  Testing MCP endpoint (localhost:8100):"
curl -s -o /dev/null -w "    HTTP Status: %{http_code}\n" http://localhost:8100/health 2>/dev/null || echo "    ❌ MCP service not reachable"

# C3. Finance Adapter (Plaid)
echo ""
echo "▶ C3. Finance Adapter (Plaid) Status"
echo "─────────────────────────────────────────────────────────────"
if [ -f "shared/adapters/finance/plaid.py" ]; then
    echo "  ✅ plaid.py adapter exists"
else
    echo "  ❌ plaid.py adapter NOT FOUND"
fi

echo "  Finance adapter directory:"
ls -la shared/adapters/finance/ 2>/dev/null || echo "    Directory not found"

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Track C Summary - Actions Required"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  C1. Google Calendar OAuth:"
echo "      - Create shared/adapters/calendar/google_calendar.py"
echo "      - Implement OAuth 2.0 flow with refresh token"
echo "      - Add OAuth callback route to UI service"
echo "      - Create integration test with mock API"
echo ""
echo "  C2. MCP Bridge Hardening:"
echo "      - Add Pydantic validation to all tool handlers"
echo "      - Implement per-tool rate limits"
echo "      - Add MCP-compliant error codes"
echo ""
echo "  C3. Plaid Finance Adapter:"
echo "      - Create shared/adapters/finance/plaid.py"
echo "      - Implement Plaid Link integration"
echo "      - Add transaction → FinancialTransaction mapping"
echo ""
