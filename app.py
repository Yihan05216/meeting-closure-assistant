
import streamlit as st
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

st.set_page_config(
    page_title="Meeting Closure Assistant",
    layout="wide"
)

logger = logging.getLogger(__name__)

st.title("Meeting Closure Assistant")
st.caption(
    "Check whether the important outcomes are actually resolved before the meeting ends."
)

# -----------------------------
# DeepSeek Client
# -----------------------------

client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)


# -----------------------------
# AI Analysis Function
# -----------------------------

class MeetingAnalysisError(ValueError):
    """An unusable model response with a user-facing explanation."""


def analyze_meeting_with_ai(meeting_type, meeting_goal, agenda, transcript):

    system_prompt = """
You are an AI Meeting Analyst.

Evaluate each agenda item against its intended outcome in the context of
the Meeting Type, Meeting Goal, and Agenda. Use Meeting Type as context;
the specific goal and agenda take precedence over assumptions about that type.
Use the transcript as evidence of what was achieved.

Do not simply check whether a topic was mentioned. An intended outcome may
be sharing information, exploring ideas, reviewing progress, or making a
decision. Do not assume every agenda item requires a decision or commitment.

Judge completion by the action or outcome expressed in each agenda item,
not by whether its underlying subject is fully complete. A review is completed
when the relevant status is sufficiently examined and established, even if
pending work is discovered. Discussing risks can be completed while risks
remain; generating ideas can be completed without selecting one. Confirming
a date, assigning an owner, or making a decision requires that specific
outcome to actually occur.

Capture pending work, risks, blockers, or dependencies discovered during a
completed review in the meeting summary when relevant, and in before_ending
only when they genuinely need attention before ending this meeting. Their
existence alone must not make the review agenda item unresolved.

Classify each agenda item as:

- completed: its intended outcome was achieved
- unresolved: meaningfully discussed, but its intended outcome remains unmet
- missing: not meaningfully addressed

Treat decisions, action items, owners, deadlines, risks, and blockers as
contextual closure signals, not universal requirements. Their absence or
continued existence alone does not prevent completion. Assess whether they
require attention before ending based on this meeting's intended outcomes
and explicit requirements in the transcript. Do not invent requirements or
assume unstated outcomes were achieved.

Set progress to a number from 0 to 100 representing overall progress toward
the meeting's intended outcomes, considering their importance to the Meeting
Goal rather than merely counting topics mentioned.

Set before_ending to only the outstanding items that genuinely need attention
before ending this specific meeting. Do not include future work merely because
it remains unfinished, unless agreeing or resolving it now is necessary to
achieve this meeting's intended outcomes. Use an empty array if none remain.

Also return a meeting_summary based only on information explicitly supported
by the meeting transcript:
- key_decisions: confirmed decisions, as strings
- action_items: agreed actions, each with action, owner, and deadline
- risks: stated risks or unresolved issues, as strings
Do not guess decisions, actions, owners, deadlines, or risks. Use "Not specified"
for missing owners or deadlines. Preserve deadlines as stated in the transcript.
Use empty arrays when no supported entries exist; do not include placeholder items.
Keep wording concise, with short reasons and no unnecessary repetition, while
covering every agenda item and preserving all supported decisions and actions.

Return ONLY valid JSON in this format:

{
  "progress": 0,
  "completed": [
    {
      "item": "",
      "reason": ""
    }
  ],
  "unresolved": [
    {
      "item": "",
      "reason": ""
    }
  ],
  "missing": [
    {
      "item": "",
      "reason": ""
    }
  ],
  "before_ending": [
    ""
  ],
  "meeting_summary": {
    "key_decisions": [],
    "action_items": [
      {
        "action": "",
        "owner": "",
        "deadline": ""
      }
    ],
    "risks": []
  }
}
"""

    user_prompt = f"""
Meeting Type:
{meeting_type}

Meeting Goal:
{meeting_goal}

Agenda:
{agenda}

Meeting Transcript:
{transcript}

Analyze this meeting and return the result as JSON.
"""

    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        reasoning_effort="low",
        max_tokens=16000
    )

    if not response.choices:
        raise MeetingAnalysisError(
            "DeepSeek returned no answer. Please try again."
        )

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise MeetingAnalysisError(
            "DeepSeek reached the output token limit (finish_reason=length), "
            "so the analysis may be incomplete and has not been displayed. "
            "Please try again. If this repeats, the output token limit needs review."
        )

    if choice.finish_reason != "stop":
        raise MeetingAnalysisError(
            "DeepSeek did not finish normally. No analysis has been displayed. "
            "Please try again."
        )

    raw_content = choice.message.content
    if not raw_content or not raw_content.strip():
        raise MeetingAnalysisError(
            "DeepSeek returned an empty answer without reporting an output token "
            "limit. Please try again."
        )

    try:
        result = json.loads(raw_content)
    except json.JSONDecodeError:
        raise MeetingAnalysisError(
            "DeepSeek returned invalid JSON without reporting an output token "
            "limit. The analysis could not be read safely. Please try again."
        ) from None

    if not isinstance(result, dict):
        raise MeetingAnalysisError(
            "DeepSeek returned an unexpected response format. Please try again."
        )

    return result


# -----------------------------
# 1. Meeting Context
# -----------------------------

st.session_state.setdefault("analysis_result", None)
st.session_state.setdefault("analyzed_inputs", None)
st.session_state.setdefault("custom_meeting_type", "")


def save_custom_meeting_type():
    st.session_state["custom_meeting_type"] = st.session_state["_custom_meeting_type"]


st.header("1. Meeting Context")

st.caption("Try a sample product launch meeting, or enter your own meeting details below.")
if st.button("Load Example Meeting"):
    # Fictional sample data for demonstrating the existing analysis workflow.
    st.session_state.update({
        "meeting_type": "Product / Decision Meeting",
        "meeting_goal": "Decide whether to launch the AI assistant beta next Friday, confirm the remaining launch tasks and their owners, and identify any issues that must be clarified before the meeting ends.",
        "agenda": """1. Review beta launch readiness.
2. Confirm the beta launch date and conditions.
3. Assign owners and deadlines for remaining tasks.
4. Discuss beta pricing and longer-term pricing strategy.""",
        "transcript": """Alice: Our goal today is to decide whether we can launch the AI assistant beta next Friday. Let's start with readiness.

Bob: The core features are implemented. I will finish the final regression testing on Thursday afternoon and share the results. If the tests pass, the product should be ready for Friday.

Alice: Great. Are we all comfortable targeting next Friday, provided the final tests pass?

Carol: Yes. I can finish the landing page by Wednesday and prepare the user feedback tracker by Friday.

Alice: Agreed. Let's target next Friday, conditional on successful testing on Thursday.

Carol: What about pricing?

Alice: The invited beta will be free. We don't need to finalize long-term pricing today. I will collect initial feedback and prepare a pricing recommendation for next Monday's meeting.

Bob: One question: if Thursday's tests fail, who will decide whether we postpone the launch?

Alice: We haven't assigned anyone to make that decision yet. We need to clarify this before we wrap up.

Carol: Agreed. Everything else has a clear next step."""
    })
st.caption("This example is fictional and is not a real meeting record.")

meeting_type = st.selectbox(
    "Meeting Type",
    [
        "Product / Decision Meeting",
        "Brainstorming",
        "Weekly Sync",
        "Project Review",
        "Project Retrospective",
        "Client Meeting",
        "Other"
    ],
    key="meeting_type"
)

if meeting_type == "Other":
    st.session_state["_custom_meeting_type"] = st.session_state["custom_meeting_type"]
    custom_type = st.text_input(
        "Describe the meeting type",
        key="_custom_meeting_type",
        on_change=save_custom_meeting_type
    )
    meeting_type = custom_type.strip() or "Other"

meeting_goal = st.text_area(
    "Meeting Goal",
    key="meeting_goal",
    placeholder="Example: Decide whether the product is ready to launch next Monday."
)

agenda = st.text_area(
    "Agenda",
    key="agenda",
    placeholder="""Example:
1. Confirm product readiness
2. Confirm launch date
3. Assign marketing owner
4. Make final launch decision"""
)

st.divider()


# -----------------------------
# 2. Meeting Transcript
# -----------------------------

st.header("2. Meeting Transcript")

transcript = st.text_area(
    "Paste meeting notes or transcript",
    key="transcript",
    height=250,
    placeholder="""Example:

Alice: The engineering team has completed all critical features.

Bob: Marketing materials will be ready by Friday.

Alice: Great. We still need to decide whether we launch on Monday.

Charlie: I can own the final QA check."""
)

st.divider()


# -----------------------------
# 3. Prepare to End Meeting
# -----------------------------

st.header("3. Prepare to End Meeting")
st.write(
    "AI reviews the meeting goal, agenda, and transcript to identify what is "
    "complete and what still needs attention before the meeting ends."
)

current_inputs = {
    "meeting_type_selection": st.session_state["meeting_type"],
    "meeting_type": meeting_type,
    "custom_meeting_type": (
        st.session_state["custom_meeting_type"]
        if st.session_state["meeting_type"] == "Other" else ""
    ),
    "meeting_goal": meeting_goal,
    "agenda": agenda,
    "transcript": transcript
}

if st.button("Prepare to End Meeting", type="primary"):

    missing_fields = [
        label for label, value in (
            ("Meeting Goal", meeting_goal),
            ("Agenda", agenda),
            ("Transcript", transcript)
        ) if not value.strip()
    ]

    if missing_fields:

        st.warning(
            "Please complete the following before preparing to end the meeting: "
            + ", ".join(missing_fields) + "."
        )

    else:

        with st.spinner("Checking whether the meeting's important outcomes are resolved..."):

            try:

                result = analyze_meeting_with_ai(
                    meeting_type,
                    meeting_goal,
                    agenda,
                    transcript
                )

                st.session_state["analysis_result"] = result
                st.session_state["analyzed_inputs"] = current_inputs.copy()

            except MeetingAnalysisError as e:
                logger.warning("Meeting analysis response rejected: %s", str(e))
                st.error("The analysis could not be completed. Please try again.")

            except Exception as e:

                # Log the exception category only; API errors can contain sensitive data.
                logger.error("Meeting analysis failed (%s)", type(e).__name__)
                st.error("The analysis is unavailable right now. Please try again shortly.")

if st.session_state["analysis_result"] is not None:
    if current_inputs != st.session_state["analyzed_inputs"]:
        st.warning(
            "These results are based on previous inputs. Click 'Prepare to End Meeting' "
            "to refresh the analysis."
        )

    result = st.session_state["analysis_result"]
    progress = result.get("progress", 0)

    # Progress
    st.divider()
    st.subheader("Overall Meeting Status / Progress")

    st.progress(progress / 100)
    st.metric("Goal Completion", f"{progress}%")

    # Before Ending
    st.divider()

    before_ending = result.get("before_ending", [])

    with st.container(border=True):
        st.subheader("Before Ending This Meeting")
        if before_ending:
            st.warning("Address these items before ending the meeting.")
            for i, item in enumerate(before_ending, 1):
                st.write(f"{i}. {item}")
        else:
            st.success("None identified")

    # Results
    st.subheader("Agenda Review")
    col1, col2, col3 = st.columns(3)

    with col1:

        st.markdown("#### Completed")

        completed = result.get("completed", [])

        if completed:
            for item in completed:
                st.success(item.get("item", ""))
                st.caption(item.get("reason", ""))
        else:
            st.caption("None identified")

    with col2:

        st.markdown("#### Unresolved")

        unresolved = result.get("unresolved", [])

        if unresolved:
            for item in unresolved:
                st.warning(item.get("item", ""))
                st.caption(item.get("reason", ""))
        else:
            st.caption("None identified")

    with col3:

        st.markdown("#### Missing")

        missing = result.get("missing", [])

        if missing:
            for item in missing:
                st.error(item.get("item", ""))
                st.caption(item.get("reason", ""))
        else:
            st.caption("None identified")

    # Meeting Summary
    st.divider()
    st.subheader("Meeting Summary")

    summary = result.get("meeting_summary") or {}

    st.markdown("#### Key Decisions")
    key_decisions = summary.get("key_decisions") or []
    if key_decisions:
        for decision in key_decisions:
            st.write(f"- {decision}")
    else:
        st.caption("None identified")

    st.markdown("#### Action Items")
    action_items = summary.get("action_items") or []
    if action_items:
        st.table([
            {
                "Action": item.get("action", ""),
                "Owner": item.get("owner") or "Not specified",
                "Deadline": item.get("deadline") or "Not specified"
            }
            for item in action_items
        ])
    else:
        st.caption("None identified")

    st.markdown("#### Risks / Unresolved Issues")
    risks = summary.get("risks") or []
    if risks:
        for risk in risks:
            st.write(f"- {risk}")
    else:
        st.caption("None identified")

