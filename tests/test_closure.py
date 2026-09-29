import copy
import datetime
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from closure_workflow import (
    reset_closure, reset_meeting, sync_inputs, collect_blockers,
    save_action, save_exception, confirm_end, remaining_risks
)
from test_templates import response_for_request


def click(app, label):
    return next(b for b in app.button if b.label == label).click().run()


class ClosureTests(unittest.TestCase):
    def test_actions_never_resolve_and_exceptions_retain_risks(self):
        state = {}
        reset_closure(state)
        result = {"before_ending": ["Decision owner missing"], "meeting_summary": {"risks": ["Launch may slip"]}}
        original = copy.deepcopy(result)
        blockers = collect_blockers(result, {})
        for action, owner, due in (("", "Alice", datetime.date(2026, 10, 1)), ("Follow up", " ", datetime.date(2026, 10, 1)), ("Follow up", "Alice", None)):
            with self.assertRaises(ValueError):
                save_action(state, blockers[0], action, owner, due)
        for _ in range(2):
            save_action(state, blockers[0], "Clarify owner", "Alice", datetime.date(2026, 10, 1))
        self.assertEqual(len(state["gap_actions"]), 1)
        self.assertEqual(state["gap_actions"]["gap_0"]["Due Date"], "2026-10-01")
        self.assertFalse(confirm_end(state, blockers, stale=False, acknowledged=True))
        with self.assertRaises(ValueError):
            save_exception(state, blockers[0], " ")
        save_exception(state, blockers[0], "Host accepts the risk and will clarify tomorrow.")
        self.assertFalse(confirm_end(state, blockers, stale=True, acknowledged=True))
        self.assertFalse(confirm_end(state, blockers, stale=False, acknowledged=False))
        self.assertTrue(confirm_end(state, blockers, stale=False, acknowledged=True))
        self.assertIn("Decision owner missing", remaining_risks(result, blockers))
        self.assertIn("Launch may slip", remaining_risks(result, blockers))
        self.assertEqual(result, original)

    def test_required_checks_cannot_silently_disappear(self):
        result = {"before_ending": [], "check_results": [{"id": "c", "status": "not_met"}], "role_coverage": []}
        analyzed = {"checks": [{"id": "c", "item": "Confirm date", "priority": "Must Have"}, {"id": "optional", "item": "Ideas", "priority": "For Reference"}], "required_roles": [{"id": "r", "role": "Client"}]}
        blockers = collect_blockers(result, analyzed)
        self.assertEqual(len(blockers), 2)
        state = {}
        reset_closure(state)
        self.assertFalse(confirm_end(state, blockers, stale=False, acknowledged=True))

    def test_edit_reset_and_revert_never_restore_host_records(self):
        state = {}
        reset_closure(state)
        sync_inputs(state, {"transcript": "old"})
        save_exception(state, {"id": "gap_0", "text": "risk"}, "accepted")
        state["meeting_closed"] = True
        self.assertTrue(sync_inputs(state, {"transcript": "new"}))
        self.assertFalse(state["meeting_closed"])
        self.assertEqual(state["gap_exceptions"], {})
        sync_inputs(state, {"transcript": "old"})
        self.assertEqual(state["gap_exceptions"], {})
        reset_meeting(state)
        self.assertIsNone(state["analysis_result"])

    def test_ui_closure_forms_reruns_and_template_reset(self):
        client = Mock()
        client.chat.completions.create.side_effect = response_for_request
        with patch("openai.OpenAI", return_value=client):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            for key in ("meeting_goal", "agenda", "transcript"):
                app.text_area(key=key).set_value("Synthetic input")
            click(app, "Prepare to End Meeting")
            self.assertFalse(app.exception)
            self.assertTrue(next(b for b in app.button if b.label == "Confirm End Meeting").disabled)
            click(app, "Convert to Action Item")
            click(app, "Save User-added Action Item")
            self.assertFalse(app.session_state["gap_actions"])
            next(w for w in app.text_input if w.label == "Owner").set_value("Alice")
            app.date_input[0].set_value(datetime.date(2026, 10, 1))
            click(app, "Save User-added Action Item")
            click(app, "Save User-added Action Item")
            self.assertEqual(len(app.session_state["gap_actions"]), 1)
            self.assertEqual(app.session_state["gap_actions"]["gap_0"]["Owner"], "Alice")
            self.assertEqual(app.session_state["gap_actions"]["gap_0"]["Due Date"], "2026-10-01")
            self.assertTrue(next(b for b in app.button if b.label == "Confirm End Meeting").disabled)
            click(app, "Record Exception")
            click(app, "Save User-recorded Exception")
            self.assertFalse(app.session_state["gap_exceptions"])
            next(w for w in app.text_area if w.label == "Exception reason").set_value("Host accepts postponement risk.")
            click(app, "Save User-recorded Exception")
            app.checkbox[0].check().run()
            click(app, "Confirm End Meeting")
            self.assertTrue(app.session_state["meeting_closed"])
            self.assertIn("Clarify the postponement decision owner.", app.session_state["analysis_result"]["before_ending"])
            self.assertEqual(client.chat.completions.create.call_count, 1)
            app.run()
            self.assertTrue(app.session_state["meeting_closed"])
            app.text_area(key="transcript").set_value("Updated discussion").run()
            self.assertFalse(app.session_state["meeting_closed"])
            self.assertFalse(app.session_state["gap_actions"])
            self.assertFalse(app.session_state["gap_exceptions"])
            self.assertTrue(next(b for b in app.button if b.label == "Confirm End Meeting").disabled)
            click(app, "Prepare to End Meeting")
            click(app, "Continue Discussion")
            self.assertTrue(app.session_state["discussion_requested"])
            self.assertEqual(client.chat.completions.create.call_count, 2)
            click(app, "Record Exception")
            next(w for w in app.text_area if w.label == "Exception reason").set_value("Temporary exception")
            click(app, "Save User-recorded Exception")
            client.chat.completions.create.side_effect = RuntimeError("test failure")
            click(app, "Prepare to End Meeting")
            self.assertTrue(app.session_state["gap_exceptions"])
            client.chat.completions.create.side_effect = response_for_request
            click(app, "Prepare to End Meeting")
            self.assertFalse(app.session_state["gap_exceptions"])
            self.assertFalse(app.session_state["discussion_requested"])
            app.selectbox(key="meeting_template").select("Project Retrospective").run()
            self.assertIsNone(app.session_state["analysis_result"])
            self.assertFalse(app.session_state["gap_exceptions"])
            self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
