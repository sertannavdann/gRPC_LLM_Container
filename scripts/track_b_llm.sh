#!/bin/bash
# Track B: LLM/AI Tasks - Self-Consistency, JSON Parsing, Evals
# Skill: llm_ai_engineer.md

set -e
cd "$(dirname "$0")/.."

echo "═══════════════════════════════════════════════════════════"
echo "  Track B: LLM/AI Reliability"
echo "═══════════════════════════════════════════════════════════"

# B1. Self-Consistency Status
echo ""
echo "▶ B1. Self-Consistency Integration Status"
echo "─────────────────────────────────────────────────────────────"
if [ -f "core/self_consistency.py" ]; then
    echo "  ✅ self_consistency.py exists"
    grep -c "def " core/self_consistency.py | xargs -I{} echo "    Functions defined: {}"
else
    echo "  ❌ self_consistency.py NOT FOUND"
fi

# Check if integrated in orchestrator
if grep -q "self_consistency\|SelfConsistency" orchestrator/orchestrator_service.py 2>/dev/null; then
    echo "  ✅ Self-consistency integrated in orchestrator"
else
    echo "  ❌ Self-consistency NOT integrated in orchestrator"
fi

# B2. JSON Parser Status
echo ""
echo "▶ B2. Tool-Calling JSON Parser Status"
echo "─────────────────────────────────────────────────────────────"
if [ -f "shared/utils/json_parser.py" ]; then
    echo "  ✅ json_parser.py exists"
    # Check for key functions
    if grep -q "extract_tool_call\|extract_json" shared/utils/json_parser.py 2>/dev/null; then
        echo "    ✅ extract_tool_call/extract_json function found"
    else
        echo "    ❌ extract_tool_call function NOT found"
    fi
else
    echo "  ❌ json_parser.py NOT FOUND - needs creation"
fi

# Check for inline JSON parsing that should be consolidated
echo ""
echo "  Inline JSON parsing locations (should be consolidated):"
grep -rn "json.loads\|```json" orchestrator/ --include="*.py" 2>/dev/null | head -5 || echo "    No inline parsing found"

# B3. Multi-Step Query Guardrails
echo ""
echo "▶ B3. Multi-Step Query Guardrails Status"
echo "─────────────────────────────────────────────────────────────"
if [ -f "orchestrator/intent_patterns.py" ]; then
    echo "  ✅ intent_patterns.py exists"
    if grep -q "MULTI_TOOL" orchestrator/intent_patterns.py 2>/dev/null; then
        echo "    ✅ MULTI_TOOL_INTENTS defined"
    else
        echo "    ❌ MULTI_TOOL_INTENTS NOT defined"
    fi
else
    echo "  ❌ intent_patterns.py NOT FOUND"
fi

# B4. Eval Framework
echo ""
echo "▶ B4. Eval Framework Status"
echo "─────────────────────────────────────────────────────────────"
if [ -d "tests/evals" ]; then
    echo "  ✅ tests/evals/ directory exists"
    ls -la tests/evals/ 2>/dev/null || echo "    (empty)"
else
    echo "  ❌ tests/evals/ NOT FOUND - needs creation"
fi

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Track B Summary - Actions Required"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  B1. Self-Consistency:"
echo "      - Wire SelfConsistencyChecker into orchestrator loop"
echo "      - Add self_consistency_confidence to response proto"
echo "      - Create eval dataset for consistency testing"
echo ""
echo "  B2. JSON Parser:"
echo "      - Create/update shared/utils/json_parser.py"
echo "      - Implement extract_tool_call() for all formats"
echo "      - Replace inline parsing in orchestrator"
echo ""
echo "  B3. Multi-Step Guardrails:"
echo "      - Add MULTI_TOOL_INTENTS to intent_patterns.py"
echo "      - Implement sequence completion guard"
echo "      - Add destination alias resolution"
echo ""
echo "  B4. Eval Framework:"
echo "      - Create tests/evals/eval_runner.py"
echo "      - Define 20+ tool selection eval cases"
echo "      - Add 'make eval' target to Makefile"
echo ""
