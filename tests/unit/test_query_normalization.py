from shared.utils.query_normalization import normalize_user_query


def test_transcript_payload_extracts_last_user_turn():
    payload = (
        "hello\n"
        "User: Can you help me with math?\n"
        "Assistant: Sure.\n"
        "User: Solve 3x+5=14\n"
        "Assistant: x=3\n"
        "User: What about 2x-4=10?"
    )

    normalized = normalize_user_query(payload, max_chars=2000)

    assert normalized == "What about 2x-4=10?"


def test_long_query_is_truncated_to_budget():
    payload = "a" * 2500

    normalized = normalize_user_query(payload, max_chars=2000)

    assert len(normalized) == 2000


def test_plain_query_unchanged():
    payload = "What is 2+2?"

    normalized = normalize_user_query(payload, max_chars=2000)

    assert normalized == payload
