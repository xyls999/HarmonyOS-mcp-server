"""Small testable helpers for per-turn A9 context injection."""

from __future__ import annotations


def build_turn_context(context_engine, user_text, *, messages, body, live_state):
    """Build automatic context once per turn while honoring explicit first-turn state."""
    if context_engine is None:
        return ""
    if "isFirstTurn" in body:
        is_first_turn = bool(body["isFirstTurn"])
    elif "is_first_turn" in body:
        is_first_turn = bool(body["is_first_turn"])
    else:
        user_messages = [item for item in messages if item.get("role") == "user"]
        is_first_turn = len(user_messages) <= 1
    return context_engine.build_prompt_context(
        str(user_text),
        is_first_turn=is_first_turn,
        live_state=live_state,
    )


def merge_context_summaries(memory_context, automatic_context):
    parts = [str(value).strip() for value in (memory_context, automatic_context) if value]
    return "\n\n".join(part for part in parts if part)
