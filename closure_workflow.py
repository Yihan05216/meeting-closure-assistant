"""Host-owned session records, separate from immutable AI analysis results."""


def reset_closure(state):
    state["closure_revision"] = state.get("closure_revision", 0) + 1
    state["gap_actions"] = {}
    state["gap_exceptions"] = {}
    state["gap_editors"] = {}
    state["meeting_closed"] = False
    state["closure_ack_revision"] = 0
    state["discussion_requested"] = False
    for key in list(state):
        if key.startswith("closure_widget_"):
            del state[key]


def reset_meeting(state):
    reset_closure(state)
    state["analysis_result"] = None
    state["analyzed_inputs"] = None
    state["closure_inputs"] = None


def sync_inputs(state, inputs):
    """Conservatively discard host records on edits, even if edits are reverted."""
    previous = state.get("closure_inputs")
    changed = previous is not None and previous != inputs
    if changed:
        reset_closure(state)
    state["closure_inputs"] = inputs
    return changed


def collect_blockers(result, analyzed):
    blockers = [
        {"id": f"gap_{i}", "text": text, "source": "AI Before Ending"}
        for i, text in enumerate(result.get("before_ending", [])) if text.strip()
    ]
    # Do not let an omitted before_ending entry silently waive a required check.
    checks = {r["id"]: r for r in result.get("check_results", [])}
    for check in analyzed.get("checks", []):
        if check["priority"] == "Must Have" and checks.get(check["id"], {}).get("status") != "met":
            blockers.append({"id": f"check_{check['id']}", "text": check["item"], "source": "Unmet or unconfirmed Must Have check"})
    roles = {r["id"]: r for r in result.get("role_coverage", [])}
    for role in analyzed.get("required_roles", []):
        if roles.get(role["id"], {}).get("status") != "covered":
            blockers.append({"id": f"role_{role['id']}", "text": f"Confirm contribution from {role['role']}", "source": "Missing or unconfirmed required role"})
    return blockers


def save_action(state, blocker, action, owner, due_date):
    if not action.strip() or not owner.strip() or due_date is None:
        raise ValueError("Please provide an Action Item, Owner, and Due Date.")
    state["gap_actions"][blocker["id"]] = {
        "Source": "User-added", "Original gap": blocker["text"],
        "Action Item": action.strip(), "Owner": owner.strip(),
        "Due Date": due_date.isoformat()
    }
    state["closure_ack_revision"] += 1


def save_exception(state, blocker, reason):
    if not reason.strip():
        raise ValueError("Please provide an exception reason.")
    state["gap_exceptions"][blocker["id"]] = {
        "Source": "User-recorded exception", "Original risk": blocker["text"],
        "Reason": reason.strip()
    }
    state["closure_ack_revision"] += 1


def unacknowledged_blockers(state, blockers):
    # An action item is a follow-up, never proof of resolution or an exception.
    return [b for b in blockers if not state["gap_exceptions"].get(b["id"], {}).get("Reason", "").strip()]


def confirm_end(state, blockers, *, stale, acknowledged):
    if stale or not acknowledged or unacknowledged_blockers(state, blockers):
        return False
    state["meeting_closed"] = True
    return True


def remaining_risks(result, blockers):
    risks = list(result.get("meeting_summary", {}).get("risks", []))
    risks.extend(b["text"] for b in blockers)
    # Exceptions authorize a host choice; they do not remove the original risks.
    return list(dict.fromkeys(risks))
