"""Secret lookup and session-level public-demo spending limits."""
import hashlib
import json
import os

DEEPSEEK_SESSION_LIMIT = 8


def read_secret(name):
    value = os.environ.get(name)
    if value:
        return value
    import streamlit as st
    try:
        return st.secrets.get(name)
    except (FileNotFoundError, KeyError):
        return None


def reserve_analysis(state, payload, *, deduplicate=True):
    """Reserve before networking, including failures; never store credentials."""
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    attempts = state.setdefault("public_analysis_attempts", {})
    if not deduplicate:
        key += ":" + str(len(attempts))
    if key in attempts:
        return "This analysis was already requested. Update the discussion before requesting another analysis."
    if len(attempts) >= DEEPSEEK_SESSION_LIMIT:
        return "This demo session has reached its limit of 8 DeepSeek requests. Existing results remain available."
    attempts[key] = True
    return None
