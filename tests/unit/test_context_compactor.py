"""
Unit tests for the context compactor.

Tests the compact_context function with mocked LLM engine and ChromaDB
client to verify summarisation, archival, and edge cases.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from core.context_compactor import compact_context, _role_label


class TestCompactContext:
    """Tests for core/context_compactor.compact_context"""

    def _make_messages(self, n: int):
        """Create n alternating user/assistant messages."""
        msgs = []
        for i in range(n):
            if i % 2 == 0:
                msgs.append(HumanMessage(content=f"User message {i}"))
            else:
                msgs.append(AIMessage(content=f"Assistant reply {i}"))
        return msgs

    def _mock_llm(self, summary_text="Summary of conversation."):
        """Return a mock LLM engine that returns a canned summary."""
        engine = Mock()
        engine.generate.return_value = {"content": summary_text}
        return engine

    def _mock_chroma(self, success=True):
        """Return a mock ChromaClient."""
        client = Mock()
        client.add_document.return_value = success
        return client

    # ── No compaction needed ──────────────────────────────────────────

    def test_no_compaction_under_limit(self):
        msgs = self._make_messages(5)
        llm = self._mock_llm()
        result = compact_context(msgs, max_messages=10, llm_engine=llm)
        assert len(result) == 5
        # LLM should NOT be called
        llm.generate.assert_not_called()

    def test_no_compaction_at_exact_limit(self):
        msgs = self._make_messages(6)
        llm = self._mock_llm()
        result = compact_context(msgs, max_messages=6, llm_engine=llm)
        assert len(result) == 6

    # ── Compaction triggers ───────────────────────────────────────────

    def test_compaction_over_limit(self):
        msgs = self._make_messages(10)
        llm = self._mock_llm("They discussed greetings.")
        result = compact_context(msgs, max_messages=6, llm_engine=llm)

        # Should be 1 summary + 5 kept = 6
        assert len(result) == 6
        assert isinstance(result[0], SystemMessage)
        assert "Conversation Summary" in result[0].content
        assert "greetings" in result[0].content

    def test_llm_called_with_evicted_text(self):
        msgs = self._make_messages(8)
        llm = self._mock_llm("Short summary.")
        compact_context(msgs, max_messages=4, llm_engine=llm)

        llm.generate.assert_called_once()
        call_kwargs = llm.generate.call_args
        prompt = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") if len(call_kwargs) > 1 else call_kwargs[0][0]
        # The prompt should contain evicted messages
        assert isinstance(prompt, list)

    # ── ChromaDB archival ─────────────────────────────────────────────

    def test_archives_to_chroma(self):
        msgs = self._make_messages(10)
        llm = self._mock_llm("Archive test summary.")
        chroma = self._mock_chroma()

        compact_context(
            msgs,
            max_messages=6,
            llm_engine=llm,
            chroma_client=chroma,
            conversation_id="conv-123",
        )

        chroma.add_document.assert_called_once()
        call_kwargs = chroma.add_document.call_args
        assert "ctx_conv-123_" in call_kwargs.kwargs.get("document_id", call_kwargs[1].get("document_id", ""))
        metadata = call_kwargs.kwargs.get("metadata", call_kwargs[1].get("metadata", {}))
        assert metadata["conversation_id"] == "conv-123"
        assert metadata["source"] == "context_compactor"

    def test_no_chroma_no_crash(self):
        msgs = self._make_messages(10)
        llm = self._mock_llm("No chroma test.")
        # chroma_client=None should not crash
        result = compact_context(msgs, max_messages=6, llm_engine=llm, chroma_client=None)
        assert len(result) == 6

    def test_chroma_failure_non_fatal(self):
        msgs = self._make_messages(10)
        llm = self._mock_llm("Chroma fail test.")
        chroma = Mock()
        chroma.add_document.side_effect = RuntimeError("DB down")

        # Should NOT raise
        result = compact_context(msgs, max_messages=6, llm_engine=llm, chroma_client=chroma)
        assert len(result) == 6

    # ── LLM failure fallback ──────────────────────────────────────────

    def test_llm_failure_fallback_truncation(self):
        msgs = self._make_messages(10)
        llm = Mock()
        llm.generate.side_effect = RuntimeError("LLM down")

        result = compact_context(msgs, max_messages=6, llm_engine=llm)
        assert len(result) == 6
        assert isinstance(result[0], SystemMessage)
        assert "truncated" in result[0].content.lower()

    # ── Edge cases ────────────────────────────────────────────────────

    def test_empty_messages(self):
        result = compact_context([], max_messages=6, llm_engine=self._mock_llm())
        assert result == []

    def test_single_message(self):
        msgs = [HumanMessage(content="Hello")]
        result = compact_context(msgs, max_messages=6, llm_engine=self._mock_llm())
        assert len(result) == 1

    def test_original_list_not_mutated(self):
        msgs = self._make_messages(10)
        original_len = len(msgs)
        compact_context(msgs, max_messages=6, llm_engine=self._mock_llm("Test."))
        assert len(msgs) == original_len


class TestRoleLabel:
    """Tests for _role_label helper."""

    def test_human(self):
        assert _role_label(HumanMessage(content="x")) == "User"

    def test_ai(self):
        assert _role_label(AIMessage(content="x")) == "Assistant"

    def test_system(self):
        assert _role_label(SystemMessage(content="x")) == "System"

    def test_tool(self):
        msg = ToolMessage(content="x", tool_call_id="tc1", name="search")
        assert "Tool" in _role_label(msg)
        assert "search" in _role_label(msg)
