"""
Context compactor — keeps conversation history within a token budget.

When the message list exceeds ``max_messages`` the oldest *user/assistant*
turns are:
    1. Summarised into a single compact paragraph by the LLM.
    2. Archived to ChromaDB with rich metadata (conversation_id, turn range,
       timestamp) so they can be recalled via RAG later.
    3. Replaced in-context by a single SystemMessage with the summary.

This lets long-running conversations stay coherent without blowing up the
context window, and gives the knowledge base a growing memory of past
interactions.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────
_SUMMARY_PREFIX = "[Conversation Summary] "
_ARCHIVE_COLLECTION = "conversation_archive"


def compact_context(
    messages: Sequence[BaseMessage],
    max_messages: int,
    llm_engine,
    chroma_client=None,
    conversation_id: str = "unknown",
) -> List[BaseMessage]:
    """
    Trim a message list down to *max_messages* while preserving meaning.

    Algorithm:
        1. If ``len(messages) <= max_messages`` → return as-is.
        2. Split messages into *evicted* (oldest) and *kept* (newest).
        3. Summarise evicted turns with a short LLM call.
        4. Archive evicted text + summary to ChromaDB (if client available).
        5. Return ``[SystemMessage(summary)] + kept``.

    The function never modifies the original list.

    Args:
        messages: Full conversation history.
        max_messages: Target ceiling (e.g. 12).
        llm_engine: Object with ``.generate(messages, …)`` (LLM wrapper).
        chroma_client: Optional ChromaClient for archival.
        conversation_id: Used as metadata label for the archive entry.

    Returns:
        Trimmed list of BaseMessage objects.
    """
    if len(messages) <= max_messages:
        return list(messages)

    # Keep a safety margin: we want max_messages in the final list
    # (1 summary system message + max_messages-1 recent messages)
    keep_count = max_messages - 1  # reserve 1 slot for the summary
    evicted = list(messages[: len(messages) - keep_count])
    kept = list(messages[len(messages) - keep_count :])

    logger.info(
        f"Compacting context: {len(messages)} msgs → "
        f"evicting {len(evicted)}, keeping {len(kept)}"
    )

    # ── 1. Build a plain-text transcript of evicted messages ──────────
    transcript_lines: List[str] = []
    for msg in evicted:
        role = _role_label(msg)
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        if text.strip():
            transcript_lines.append(f"{role}: {text.strip()}")

    transcript = "\n".join(transcript_lines)
    if not transcript.strip():
        # Nothing meaningful to summarise — just drop silently
        return kept

    # ── 2. Summarise via LLM ─────────────────────────────────────────
    summary = _summarise(transcript, llm_engine)

    # ── 3. Archive to ChromaDB ────────────────────────────────────────
    if chroma_client is not None:
        _archive_to_chroma(
            chroma_client=chroma_client,
            transcript=transcript,
            summary=summary,
            conversation_id=conversation_id,
            turn_count=len(evicted),
        )

    # ── 4. Assemble compacted message list ────────────────────────────
    summary_msg = SystemMessage(content=f"{_SUMMARY_PREFIX}{summary}")
    return [summary_msg] + kept


# ── Internal helpers ──────────────────────────────────────────────────

def _role_label(msg: BaseMessage) -> str:
    """Map message type to a readable role tag."""
    if isinstance(msg, HumanMessage):
        return "User"
    if isinstance(msg, AIMessage):
        return "Assistant"
    if isinstance(msg, SystemMessage):
        return "System"
    if isinstance(msg, ToolMessage):
        return f"Tool({getattr(msg, 'name', '?')})"
    return "Unknown"


def _summarise(transcript: str, llm_engine) -> str:
    """
    Ask the LLM to produce a brief factual summary of *transcript*.

    Falls back to a naïve truncation if the LLM call fails.
    """
    prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are a concise summariser. Given the conversation transcript "
                "below, produce a short factual summary (2-4 sentences) capturing "
                "the key topics, decisions, and any data the user shared. "
                "Do NOT add opinions or hallucinate facts."
            ),
        },
        {"role": "user", "content": transcript[:6000]},  # hard cap input
    ]

    try:
        response = llm_engine.generate(
            messages=prompt_messages,
            tools=[],
            temperature=0.0,
            max_tokens=256,
        )
        content = response.get("content", "").strip()
        if content:
            logger.debug(f"Context summary: {content[:120]}…")
            return content
    except Exception as exc:
        logger.warning(f"LLM summarisation failed, falling back to truncation: {exc}")

    # Fallback: take the first ~500 chars of transcript
    return transcript[:500] + " …(truncated)"


def _archive_to_chroma(
    chroma_client,
    transcript: str,
    summary: str,
    conversation_id: str,
    turn_count: int,
) -> None:
    """
    Store evicted turns + summary in ChromaDB.

    Each archive entry gets a unique ID so it can be retrieved by the
    knowledge_search tool later ("recall what we discussed earlier").
    """
    doc_id = f"ctx_{conversation_id}_{uuid.uuid4().hex[:8]}"
    archive_text = f"Summary: {summary}\n\n---\nFull transcript:\n{transcript}"

    metadata = {
        "source": "context_compactor",
        "conversation_id": conversation_id,
        "turn_count": str(turn_count),
        "archived_at": datetime.now(tz=None).isoformat(),
        "type": "conversation_archive",
    }

    try:
        success = chroma_client.add_document(
            document_id=doc_id,
            text=archive_text,
            metadata=metadata,
        )
        if success:
            logger.info(f"Archived {turn_count} turns → ChromaDB doc {doc_id}")
        else:
            logger.warning(f"ChromaDB returned False for doc {doc_id}")
    except Exception as exc:
        # Archival is best-effort — never let it crash the main flow.
        logger.warning(f"ChromaDB archival failed (non-fatal): {exc}")
