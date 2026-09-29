import ast
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from meeting_templates import MEETING_TEMPLATES


def response_for_request(**kwargs):
    prompt = kwargs["messages"][1]["content"]
    roles = json.loads(prompt.split("Required Speakers / Roles (user-configured identities):\n")[1].split("\n\nChecks")[0])
    checks = json.loads(prompt.split("Checks (with priority):\n")[1].split("\n\nMeeting Transcript:")[0])
    result = {
        "progress": 75, "completed": [], "unresolved": [], "missing": [],
        "before_ending": ["Clarify the postponement decision owner."],
        "role_coverage": [{"id": r["id"], "status": "unable_to_confirm", "evidence": "", "reason": "Identity not established."} for r in roles],
        "check_results": [{"id": c["id"], "status": "unable_to_confirm", "evidence": "", "reason": "Needs clarification."} for c in checks],
        "meeting_summary": {"key_decisions": [], "action_items": [], "risks": []}
    }
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(result)))])


class TemplateTests(unittest.TestCase):
    def test_template_editing_sample_and_saved_results(self):
        client = Mock()
        client.chat.completions.create.side_effect = response_for_request
        with patch("openai.OpenAI", return_value=client):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            app.text_area(key="transcript").set_value("Existing notes").run()
            for name, template in MEETING_TEMPLATES.items():
                app.selectbox(key="meeting_template").select(name).run()
                self.assertFalse(app.exception)
                for key, value in template.items():
                    self.assertEqual(app.session_state[key], value)
                self.assertEqual(app.text_area(key="transcript").value, "Existing notes")
                for key in ("meeting_goal", "agenda", "required_roles", "must_have_checks", "should_have_checks", "reference_checks"):
                    app.text_area(key=key).set_value(template[key] + "\nEdited").run()
                    self.assertTrue(app.text_area(key=key).value.endswith("Edited"))
                self.assertEqual(client.chat.completions.create.call_count, 0)
                next(b for b in app.button if b.label == "Prepare to End Meeting").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(client.chat.completions.create.call_count, 1)
                self.assertEqual(len(app.table), 2)
                client.reset_mock()

            next(b for b in app.button if b.label == "Load Example Meeting").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["meeting_template"], "Product Launch Decision Meeting")
            self.assertIn("Product lead | Alice", app.session_state["required_roles"])
            self.assertIn("We haven't assigned anyone", app.session_state["transcript"])
            self.assertEqual(client.chat.completions.create.call_count, 0)
            next(b for b in app.button if b.label == "Prepare to End Meeting").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(client.chat.completions.create.call_count, 1)
            self.assertEqual({c["priority"] for c in app.session_state["analyzed_inputs"]["checks"]}, {"Must Have", "Should Have", "For Reference"})
            before = app.session_state["analysis_result"]
            app.text_area(key="required_roles").set_value("New role").run()
            self.assertTrue(any("previous inputs" in w.value for w in app.warning))
            self.assertEqual(app.session_state["analysis_result"], before)
            self.assertEqual(app.table[0].value.iloc[0]["Role"], "Product lead")
            client.chat.completions.create.side_effect = RuntimeError("test failure")
            next(b for b in app.button if b.label == "Prepare to End Meeting").click().run()
            self.assertEqual(app.session_state["analysis_result"], before)
            self.assertFalse(app.exception)

    def test_evidence_and_missing_results(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in ("MeetingAnalysisError", "analyze_meeting_with_ai")]
        client = Mock()
        ns = {"json": json, "client": client}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), ns)
        roles = [{"id": "role_1", "role": "Engineer", "speaker": ""}]
        result = {"role_coverage": [{"id": "role_1", "status": "covered", "evidence": "Invented quote", "reason": "test"}], "check_results": []}
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(result)))])
        actual = ns["analyze_meeting_with_ai"]("Review", "Review status", "Status", "Anonymous: Ready.", roles, [])
        self.assertEqual(actual["role_coverage"][0]["status"], "unable_to_confirm")
        client.chat.completions.create.return_value.choices[0].message.content = '{"role_coverage": [], "check_results": []}'
        with self.assertRaises(ns["MeetingAnalysisError"]):
            ns["analyze_meeting_with_ai"]("Review", "Goal", "Agenda", "Text", roles, [])


if __name__ == "__main__":
    unittest.main()
