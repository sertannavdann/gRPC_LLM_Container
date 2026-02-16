"""Utilities for normalizing incoming user query payloads."""

import re
from typing import Optional


def normalize_user_query(query: str, max_chars: int = 2000, logger: Optional[object] = None) -> str:
    """Normalize oversized or transcript-like user payloads before LLM processing."""
    if not query:
        return ""

    normalized = query.strip()

    if (
        normalized.count("User:") >= 2
        or ("User:" in normalized and "Assistant:" in normalized)
    ):
        segments = re.findall(
            r"User:\s*(.+?)(?=(?:\n\s*(?:Assistant|User):)|\Z)",
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )
        extracted = ""
        for segment in reversed(segments):
            candidate = segment.strip()
            if candidate:
                extracted = candidate
                break
        if extracted:
            if logger:
                logger.warning(
                    "Normalized transcript-like payload to last user turn "
                    f"(original={len(normalized)} chars, extracted={len(extracted)} chars)"
                )
            normalized = extracted

    if len(normalized) > max_chars:
        if logger:
            logger.warning(
                "Query too long; truncating to max chars "
                f"(original={len(normalized)}, max={max_chars})"
            )
        normalized = normalized[:max_chars].rstrip()

    return normalized
