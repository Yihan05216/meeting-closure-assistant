"""Real playback coverage and at-most-once ASR attempts within this session."""
import base64
import hashlib
import io
import math
from pathlib import Path
import wave

SEGMENT_SECONDS = 18


def audio_info(raw):
    with wave.open(io.BytesIO(raw), "rb") as source:
        duration = source.getnframes() / source.getframerate()
    return hashlib.sha256(raw).hexdigest(), duration


def eligible_segments(event, fingerprint, duration):
    if not isinstance(event, dict) or event.get("fingerprint") != fingerprint:
        return []
    ranges = event.get("ranges", [])
    valid = []
    for pair in ranges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        a, b = pair
        if all(isinstance(x, (int, float)) and math.isfinite(x) for x in pair) and 0 <= a <= b <= duration + 0.01:
            valid.append((a, b))
    return [i for i in range(math.ceil(duration / SEGMENT_SECONDS))
            if any(a <= i * SEGMENT_SECONDS and b >= min((i + 1) * SEGMENT_SECONDS, duration)
                   for a, b in valid)]


def wav_segment(raw, index):
    target = io.BytesIO()
    with wave.open(io.BytesIO(raw), "rb") as source:
        source.setpos(index * SEGMENT_SECONDS * source.getframerate())
        frames = source.readframes(SEGMENT_SECONDS * source.getframerate())
        with wave.open(target, "wb") as output:
            output.setparams(source.getparams())
            output.writeframes(frames)
    return target.getvalue()


def transcribe_ready(ledger, raw, eligible, api_key, client_factory=None):
    """Mark attempts before networking. Failed/interrupted requests are never retried."""
    if not api_key:
        return
    if client_factory is None:
        from groq import Groq
        client_factory = Groq
    for index in sorted(set(eligible)):
        if index in ledger:
            continue
        ledger[index] = {"status": "attempted", "text": ""}
        try:
            with client_factory(api_key=api_key, max_retries=0, timeout=45) as client:
                result = client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=("segment.wav", wav_segment(raw, index), "audio/wav"),
                    response_format="json", language="en",
                )
            ledger[index] = {"status": "done", "text": result.text.strip()}
        except Exception as error:
            # Never display raw provider errors, headers, or secrets.
            ledger[index] = {"status": "failed", "text": "",
                             "error": f"{type(error).__name__} (HTTP {getattr(error, 'status_code', 'unavailable')})"}


def append_transcript(state, ledger, duration):
    """Append in time order; wait for skipped segments, retain failed gaps visibly."""
    cursor = state.get("audio_cursor", 0)
    additions = []
    while cursor in ledger:
        row = ledger[cursor]
        if row["status"] not in {"done", "failed"}:
            break
        if row["status"] == "done" and row["text"]:
            additions.append(f"[{cursor * SEGMENT_SECONDS:.0f}–{min((cursor+1)*SEGMENT_SECONDS, duration):.0f}s] {row['text']}")
        cursor += 1
    state["audio_cursor"] = cursor
    if additions:
        old = state.get("transcript", "")
        state["transcript"] = (old.rstrip() + "\n\n" + "\n\n".join(additions)).strip()
        # Preserve host records only for this exact machine-appended change.
        previous = state.get("closure_inputs")
        if previous is not None and previous.get("transcript") == old:
            state["closure_inputs"] = {**previous, "transcript": state["transcript"]}
        state["meeting_closed"] = False
        state["closure_ack_revision"] = state.get("closure_ack_revision", 0) + 1


def render_audio_demo(state):
    import os
    import streamlit as st
    import streamlit.components.v2 as components

    path = Path(__file__).parent / "assets" / "demo_meeting.wav"
    if not path.exists():
        st.error("Demo audio is missing: assets/demo_meeting.wav")
        return
    raw = path.read_bytes()
    fingerprint, duration = audio_info(raw)
    if state.get("audio_fingerprint") != fingerprint:
        state["audio_fingerprint"] = fingerprint
        state["audio_cursor"] = 0
    ledgers = state.setdefault("audio_ledgers", {})
    ledger = ledgers.setdefault(fingerprint, {})
    player = get_player(components)
    event = player(
        key="demo_audio_player", data={"audio": base64.b64encode(raw).decode(),
        "fingerprint": fingerprint, "duration": duration, "seconds": SEGMENT_SECONDS,
        "count": math.ceil(duration / SEGMENT_SECONDS)},
        on_played_change=lambda: None,
    )
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GROQ_API_KEY")
        except (FileNotFoundError, KeyError):
            pass
    if not api_key:
        st.warning("Set GROQ_API_KEY in the environment or Streamlit Secrets to enable transcription.")
    ready = eligible_segments(event.played, fingerprint, duration)
    if any(i not in ledger for i in ready) and api_key:
        with st.spinner("Transcribing fully played audio…"):
            transcribe_ready(ledger, raw, ready, api_key)
    append_transcript(state, ledger, duration)
    st.caption("Segmented near-real-time ASR (18-second segments). Only fully played audio is sent to Groq. DeepSeek reviews about 36 seconds of new ASR automatically; Prepare to End Meeting requests an immediate closure review.")
    st.caption(f"ASR attempts for this audio in this session: {len(ledger)}. Replay uses saved results. A new browser session does not retain this cache.")
    for i, row in sorted(ledger.items()):
        label = f"{i*SEGMENT_SECONDS}–{min((i+1)*SEGMENT_SECONDS,duration):.0f}s"
        if row["status"] == "done":
            st.write(f"{label}: {row['text'] or '(No speech recognized)'}")
        else:
            st.error(f"{label}: {row.get('error', 'Request interrupted or still pending')}. Not retried; billing status may be unknown.")
    if ready and any(i not in ledger for i in range(max(ready))):
        st.info("Play the skipped earlier segments to append the transcript in chronological order.")


_player = None


def get_player(components):
    global _player
    if _player is None:
        _player = components.component("meeting_audio", js=Path(__file__).with_name("audio_player.js").read_text(encoding="utf-8"))
    return _player
