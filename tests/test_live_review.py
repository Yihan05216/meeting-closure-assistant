import sys
from pathlib import Path
from concurrent.futures import Future
from copy import deepcopy
from unittest import TestCase, main
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_review import advance_review, asr_snapshot, mark_handled, host_status, validate_live
from closure_workflow import reset_meeting


def completed(work):
    future = Future()
    try:
        future.set_result(work())
    except Exception as error:
        future.set_exception(error)
    return future


def row(evidence='Alice: Review readiness.', **changes):
    return dict(id='agenda_0', status='in_progress', discussed='Readiness reviewed',
                unconfirmed_decision='', risk='', next_step='Confirm tests', evidence=evidence,
                contradicts_host=False, contradiction_reason='', **changes)


class LiveReviewTests(TestCase):
    def setUp(self):
        self.inputs = dict(meeting_type='Review', meeting_goal='Review readiness', agenda='Review readiness',
                           required_roles=[], checks=[], transcript='FUTURE SCRIPT MUST NOT BE SENT')
        self.state = {'audio_fingerprint':'audio', 'audio_ledgers':{'audio':{}}, 'transcript':'Keep host notes'}
        reset_meeting(self.state)
        self.ai = Mock(return_value={'live_review':[row()]})

    def add(self, i, text='Alice: Review readiness.'):
        self.state['audio_ledgers']['audio'][i] = {'status':'done','text':text}

    def advance(self, force=False):
        return advance_review(self.state, self.inputs, self.ai, force=force, submit=completed)

    def test_threshold_dedup_and_only_asr_sent(self):
        self.advance(); self.ai.assert_not_called()
        self.add(0); self.advance(); self.ai.assert_not_called()
        self.add(1); self.advance(); self.advance(); self.advance()
        self.assertEqual(self.ai.call_count,1)
        self.assertNotIn('FUTURE SCRIPT', str(self.ai.call_args))
        self.state['audio_ledgers']['audio'][2]={'status':'failed','text':'Future leaked text'}
        self.advance(); self.assertEqual(self.ai.call_count,1)
        self.assertNotIn('Future leaked text',asr_snapshot(self.state)[0])
        self.add(2); self.add(3); self.advance()
        self.assertEqual(self.ai.call_count,2)

    def test_failures_preserve_state_and_never_retry(self):
        self.add(0); self.add(1)
        live=self.advance(); self.advance()
        mark_handled(live,'agenda_0','ignored','Later',asr_snapshot(self.state)[0])
        before=deepcopy(live['handled']); old=live['result']
        self.ai.side_effect=RuntimeError('private provider message')
        self.add(2); self.add(3); self.advance(); live=self.advance(); self.advance()
        self.assertEqual(self.ai.call_count,2)
        self.assertEqual(live['status'],'Analysis failed')
        self.assertEqual(live['result'],old)
        self.assertEqual(live['handled'],before)
        self.assertEqual(self.state['transcript'],'Keep host notes')

    def test_host_suppression_requires_new_contrary_evidence(self):
        self.add(0); self.add(1); live=self.advance(); self.advance()
        mark_handled(live,'agenda_0','resolved','Host confirmed',asr_snapshot(self.state)[0])
        r=row(); r.update(contradicts_host=True,contradiction_reason='Changed')
        self.assertEqual(host_status(live,r,asr_snapshot(self.state)[0]),'Host-marked resolved')
        r['evidence']='Bob: Tests failed.'
        self.assertEqual(host_status(live,r,asr_snapshot(self.state)[0]),'Host-marked resolved')
        self.add(2,r['evidence'])
        self.assertTrue(host_status(live,r,asr_snapshot(self.state)[0]).startswith('Reopened'))
        self.add(3); self.advance()
        self.assertIn('Host confirmed',str(self.ai.call_args.kwargs['live_context']))

    def test_immediate_closure_and_inflight_dedup(self):
        self.add(0)
        future=Future(); submit=Mock(return_value=future)
        live=advance_review(self.state,self.inputs,self.ai,force=True,submit=submit)
        advance_review(self.state,self.inputs,self.ai,submit=submit)
        self.assertEqual(submit.call_count,1)
        self.assertEqual(live['status'],'AI is analyzing')
        reset_meeting(self.state)
        self.assertNotIn('live_review_state',self.state)

    def test_fabricated_evidence_rejected(self):
        with self.assertRaises(ValueError):
            validate_live({'live_review':[row('Invented')]},{'targets':[{'id':'agenda_0'}]},'Actual transcript')


if __name__=='__main__': main()
