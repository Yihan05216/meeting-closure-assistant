
import streamlit as st
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from meeting_templates import MEETING_TEMPLATES
from closure_workflow import (
    reset_closure, reset_meeting, sync_inputs, collect_blockers,
    save_action, save_exception, unacknowledged_blockers, confirm_end, remaining_risks
)

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
    base_url="https://api.deepseek.com",
    # Avoid incompatible optional Brotli decoders; does not change model behavior.
    default_headers={"Accept-Encoding": "identity"}
)


# -----------------------------
# AI Analysis Function
# -----------------------------

class MeetingAnalysisError(ValueError):
    """An unusable model response with a user-facing explanation."""


def analyze_meeting_with_ai(meeting_type, meeting_goal, agenda, transcript, required_roles=None, checks=None):
    required_roles = required_roles or []
    checks = checks or []

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

Also evaluate every configured required role and check, using their supplied IDs.
Role coverage statuses: covered, not_covered, unable_to_confirm.
Use covered only when the transcript explicitly attributes a substantive
contribution to the role or its user-configured named speaker. A role-to-speaker
mapping is context, not proof that the speaker contributed. Never infer a role
from the topic someone discusses. With ambiguous identity or attribution use
unable_to_confirm; do not claim the person was silent. Use not_covered only
when the transcript explicitly establishes absence or no contribution.
For covered or not_covered include a verbatim supporting transcript excerpt
in evidence; for unable_to_confirm explain the uncertainty in reason.

Check statuses: met, not_met, unable_to_confirm. Evaluate the intended outcome
of each check, not whether all underlying future work is finished. Include a
verbatim transcript excerpt for met; distinguish unmet requirements from
insufficient evidence. Must Have checks are explicit closure requirements:
put unmet requirements or necessary clarifications in before_ending. Should
Have checks are recommendations, not automatic barriers to ending. For
Reference checks capture information and must not block closure merely because
information is absent. Required roles with uncertain or missing contributions
should be identified for clarification, without inventing speaker identities.
Return exactly one role_coverage entry per role ID and one check_results entry
per check ID, with no extra IDs. With no configuration, return empty arrays.

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
  "role_coverage": [{"id": "", "status": "unable_to_confirm", "evidence": "", "reason": ""}],
  "check_results": [{"id": "", "status": "unable_to_confirm", "evidence": "", "reason": ""}],
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

Required Speakers / Roles (user-configured identities):
{json.dumps(required_roles, ensure_ascii=False)}

Checks (with priority):
{json.dumps(checks, ensure_ascii=False)}

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

    # Require complete coverage so omitted checks cannot appear satisfied.
    for field, configured, statuses in (
        ("role_coverage", required_roles, {"covered", "not_covered", "unable_to_confirm"}),
        ("check_results", checks, {"met", "not_met", "unable_to_confirm"})
    ):
        entries = result.get(field, [])
        if not isinstance(entries, list) or any(not isinstance(row, dict) for row in entries):
            raise MeetingAnalysisError("The role or check results could not be validated. Please try again.")
        expected = {row["id"] for row in configured}
        ids = [row.get("id") for row in entries]
        if len(ids) != len(expected) or any(not isinstance(i, str) for i in ids) or set(ids) != expected:
            raise MeetingAnalysisError("The analysis omitted or duplicated configured roles or checks. Please try again.")
        for row in entries:
            if row.get("status") not in statuses or not all(isinstance(row.get(k), str) for k in ("evidence", "reason")):
                raise MeetingAnalysisError("The role or check results could not be validated. Please try again.")
            requires_evidence = row["status"] in {"covered", "not_covered", "met"}
            if requires_evidence and (not row["evidence"].strip() or row["evidence"] not in transcript):
                row.update(status="unable_to_confirm", evidence="", reason="The response did not provide a verifiable transcript excerpt. Please confirm manually.")
        result[field] = entries

    return result


# -----------------------------
# 1. Meeting Context
# -----------------------------

if "closure_revision" not in st.session_state:
    reset_closure(st.session_state)
st.session_state.setdefault("analysis_result", None)
st.session_state.setdefault("analyzed_inputs", None)
st.session_state.setdefault("custom_meeting_type", "")
for config_key in ("required_roles", "must_have_checks", "should_have_checks", "reference_checks"):
    st.session_state.setdefault(config_key, "")


def load_selected_template():
    reset_meeting(st.session_state)
    template = MEETING_TEMPLATES.get(st.session_state["meeting_template"])
    if template:
        st.session_state.update(template)


def configured_requirements():
    roles = []
    for line in st.session_state["required_roles"].splitlines():
        if line.strip():
            role, separator, speaker = line.partition("|")
            roles.append({"id": f"role_{len(roles) + 1}", "role": role.strip(), "speaker": speaker.strip() if separator else ""})
    checks = []
    for key, priority in (("must_have_checks", "Must Have"), ("should_have_checks", "Should Have"), ("reference_checks", "For Reference")):
        for line in st.session_state[key].splitlines():
            if line.strip():
                checks.append({"id": f"check_{len(checks) + 1}", "item": line.strip(), "priority": priority})
    return roles, checks



def save_custom_meeting_type():
    st.session_state["custom_meeting_type"] = st.session_state["_custom_meeting_type"]


def load_example_meeting():
    reset_meeting(st.session_state)
    st.session_state["meeting_template"] = "Product Launch Decision Meeting"
    st.session_state.update(MEETING_TEMPLATES["Product Launch Decision Meeting"])
    # Explicit fictional identities, not roles inferred from the transcript.
    st.session_state["required_roles"] = "Product lead | Alice\nEngineering lead | Bob\nMarketing lead | Carol"
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


with st.expander("How to Test / Mock & Limitations"):
    st.markdown("""
1. Load a fictional example or select a template and enter your own meeting.
2. Edit the context and paste the transcript, then click **Prepare to End Meeting**.
3. Review AI findings, discuss gaps, add follow-up actions or record exceptions,
   and explicitly confirm whether to end the meeting.

Only the example meeting data is fictional. Analysis uses the real DeepSeek API.
Transcripts must be typed or pasted manually. Data is kept only in this Streamlit
session; persistence is not guaranteed. AI judgments may be wrong and require
host review. Host actions and exceptions do not change the AI's conclusions.
""")

st.header("1. Meeting Context")
st.selectbox(
    "Meeting Template", ["Custom / No template", *MEETING_TEMPLATES],
    key="meeting_template", on_change=load_selected_template
)
st.caption("Selecting a template replaces the goal, agenda, roles, and checks. Your transcript is kept. All fields remain editable.")


st.caption("Try a sample product launch meeting, or enter your own meeting details below.")
st.button("Load Example Meeting", on_click=load_example_meeting)
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
        "Client Progress Meeting",
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

st.text_area(
    "Required Speakers / Roles", key="required_roles",
    help="One role per line. Optionally map a known speaker: Engineering lead | Bob. Without explicit identity evidence, coverage is marked Unable to confirm."
)
st.markdown("#### Meeting Checks")
st.caption("One check per line. Must Have: required for closure. Should Have: recommended. For Reference: record only, not a closure requirement.")
st.text_area("Must Have", key="must_have_checks")
st.text_area("Should Have", key="should_have_checks")
st.text_area("For Reference", key="reference_checks")
required_roles, checks = configured_requirements()

st.divider()


# -----------------------------
# 2. Meeting Transcript
# -----------------------------

st.markdown('<span id="meeting-transcript"></span>', unsafe_allow_html=True)
st.header("2. Meeting Transcript")
if st.session_state["discussion_requested"]:
    st.info("Continue the discussion and edit the transcript below. Then click 'Prepare to End Meeting' manually. No API request has been made.")

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
    "transcript": transcript,
    "required_roles": required_roles,
    "checks": checks
}

inputs_changed = sync_inputs(st.session_state, current_inputs)
if inputs_changed:
    st.info("Inputs changed. Previous host actions, exceptions, and end confirmation were reset. Refresh the analysis before handling gaps.")

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
                    transcript,
                    required_roles,
                    checks
                )

                reset_closure(st.session_state)
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
    stale = current_inputs != st.session_state["analyzed_inputs"]
    if stale:
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
    blockers = collect_blockers(result, st.session_state["analyzed_inputs"] or {})
    revision = st.session_state["closure_revision"]
    locked = stale or st.session_state["meeting_closed"]

    with st.container(border=True):
        st.subheader("Before Ending This Meeting")
        st.caption("AI findings remain unchanged. Host records below are separate. Adding an action or exception does not mean the AI considers a gap resolved.")
        if blockers:
            st.warning("Resolve these gaps through discussion and re-analysis, or record an explicit exception for each remaining blocker before confirming the end.")
        else:
            st.success("None identified")
        for i, blocker in enumerate(blockers, 1):
            gap_id = blocker["id"]
            prefix = f"closure_widget_{revision}_{gap_id}"
            st.write(f"{i}. {blocker['text']}")
            st.caption(blocker["source"])
            discussion_col, action_col, exception_col = st.columns(3)
            with discussion_col:
                if st.button("Continue Discussion", key=prefix + "_discuss", disabled=locked):
                    st.session_state["discussion_requested"] = True
                    st.rerun()
            with action_col:
                if st.button("Convert to Action Item", key=prefix + "_convert", disabled=locked):
                    st.session_state["gap_editors"][gap_id] = "action"
            with exception_col:
                if st.button("Record Exception", key=prefix + "_record", disabled=locked):
                    st.session_state["gap_editors"][gap_id] = "exception"
            mode = st.session_state["gap_editors"].get(gap_id)
            if mode == "action" and not locked:
                with st.form(prefix + "_action_form"):
                    action = st.text_input("Action Item", value=blocker["text"], key=prefix + "_action")
                    owner = st.text_input("Owner", key=prefix + "_owner")
                    due_date = st.date_input("Due Date", value=None, key=prefix + "_due")
                    if st.form_submit_button("Save User-added Action Item"):
                        try:
                            save_action(st.session_state, blocker, action, owner, due_date)
                            st.success("User-added action saved. The original blocker remains unresolved.")
                        except ValueError as e:
                            st.warning(str(e))
            elif mode == "exception" and not locked:
                with st.form(prefix + "_exception_form"):
                    reason = st.text_area("Exception reason", key=prefix + "_reason")
                    if st.form_submit_button("Save User-recorded Exception"):
                        try:
                            save_exception(st.session_state, blocker, reason)
                            st.success("User-recorded exception saved. The original risk remains; AI resolution is not confirmed.")
                        except ValueError as e:
                            st.warning(str(e))
            if gap_id in st.session_state["gap_actions"]:
                saved = st.session_state["gap_actions"][gap_id]
                st.write(f"User-added: {saved['Action Item']} | Owner: {saved['Owner']} | Due Date: {saved['Due Date']}")
            if gap_id in st.session_state["gap_exceptions"]:
                st.write("User-recorded exception: " + st.session_state["gap_exceptions"][gap_id]["Reason"])
                st.caption("Original risk retained. This is a host exception, not an AI-confirmed resolution.")
        if st.session_state["discussion_requested"]:
            st.markdown("[Return to Meeting Transcript](#meeting-transcript) — add the discussion, then manually re-analyze.")

        st.markdown("#### Confirm Meeting End")
        pending = unacknowledged_blockers(st.session_state, blockers)
        if pending:
            st.warning(f"{len(pending)} blocker(s) still need resolution or a recorded exception. Follow-up actions alone do not clear blockers.")
            for blocker in pending:
                st.write(f"- {blocker['text']}")
        if st.session_state["meeting_closed"]:
            st.success("Meeting ended by host confirmation (current session only).")
            if blockers:
                st.warning("Ended with recorded exceptions. The unresolved risks remain listed in the summary.")
        else:
            ack = st.checkbox(
                "I have reviewed the AI findings and accept responsibility for any recorded exceptions and remaining risks.",
                key=f"closure_widget_{revision}_ack_{st.session_state['closure_ack_revision']}",
                disabled=stale or bool(pending)
            )
            if st.button("Confirm End Meeting", disabled=stale or bool(pending) or not ack):
                if confirm_end(st.session_state, blockers, stale=stale, acknowledged=ack):
                    st.rerun()

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

    # Use the analyzed configuration, not edited inputs, to label saved results.
    analyzed = st.session_state["analyzed_inputs"] or {}
    st.subheader("Required Speakers / Roles Coverage")
    role_results = {row["id"]: row for row in result.get("role_coverage", [])}
    role_rows = []
    for role in analyzed.get("required_roles", []):
        row = role_results.get(role["id"], {})
        role_rows.append({
            "Role": role["role"], "Configured speaker": role["speaker"] or "Not specified",
            "Status": {"covered": "Covered", "not_covered": "Not covered"}.get(row.get("status"), "Unable to confirm"),
            "Evidence": row.get("evidence", ""), "Reason": row.get("reason", "No coverage result available.")
        })
    if role_rows:
        st.table(role_rows)
    else:
        st.caption("No required roles configured for this analysis.")

    st.subheader("Meeting Check Results")
    check_results = {row["id"]: row for row in result.get("check_results", [])}
    check_rows = []
    for check in analyzed.get("checks", []):
        row = check_results.get(check["id"], {})
        check_rows.append({
            "Check": check["item"], "Priority": check["priority"],
            "Status": {"met": "Met", "not_met": "Not met"}.get(row.get("status"), "Unable to confirm"),
            "Evidence": row.get("evidence", ""), "Reason": row.get("reason", "No check result available.")
        })
    if check_rows:
        st.table(check_rows)
    else:
        st.caption("No checks configured for this analysis.")

    # Meeting Summary
    st.divider()
    st.subheader("Meeting Summary")

    summary = result.get("meeting_summary") or {}

    st.caption("AI-generated decisions and action items — based on the analyzed transcript.")
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


    st.markdown("#### User-added Action Items")
    if st.session_state["gap_actions"]:
        st.table(list(st.session_state["gap_actions"].values()))
    else:
        st.caption("None recorded")

    st.markdown("#### User-recorded Exceptions")
    if st.session_state["gap_exceptions"]:
        st.table(list(st.session_state["gap_exceptions"].values()))
    else:
        st.caption("None recorded")

    st.markdown("#### Remaining Unresolved Risks")
    st.caption("Original AI risks and closure gaps remain here even when the host records an exception or adds a follow-up action.")
    unresolved_risks = remaining_risks(result, blockers)
    if unresolved_risks:
        for risk in unresolved_risks:
            st.write(f"- {risk}")
    else:
        st.caption("None identified")
