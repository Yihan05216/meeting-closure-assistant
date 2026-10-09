import io,sys,unittest,wave
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from streamlit.testing.v1 import AppTest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audio_demo import eligible_segments, transcribe_ready, append_transcript
from closure_workflow import reset_closure, sync_inputs

class AudioTests(unittest.TestCase):
    def test_modes_keep_separate_editable_drafts_without_api(self):
        player = Mock(return_value=SimpleNamespace(played=None))
        with patch('audio_demo.get_player', return_value=player), patch('audio_demo.transcribe_ready') as asr, patch('openai.OpenAI') as ai:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
            app.text_area(key='transcript').set_value('Manual draft').run()
            app.radio(key='input_mode').set_value('Demo Audio Meeting').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.text_area(key='transcript').value, '')
            app.text_area(key='transcript').set_value('Audio host note').run()
            app.radio(key='input_mode').set_value('Manual Transcript').run()
            self.assertEqual(app.text_area(key='transcript').value, 'Manual draft')
            app.radio(key='input_mode').set_value('Demo Audio Meeting').run()
            self.assertEqual(app.text_area(key='transcript').value, 'Audio host note')
            asr.assert_not_called()
            ai.return_value.chat.completions.create.assert_not_called()

    def test_actual_coverage_not_position(self):
        self.assertEqual(eligible_segments(None,'abc',54),[])
        def ready(r): return eligible_segments({'fingerprint':'abc','ranges':r},'abc',54)
        self.assertEqual(ready([[0,17]]),[])
        self.assertEqual(ready([[0,18]]),[0])
        self.assertEqual(ready([[0,10],[36,54]]),[2])
        self.assertEqual(ready([[0,18],[36,54]]),[0,2])
        self.assertEqual(eligible_segments({'fingerprint':'old','ranges':[[0,54]]},'abc',54),[])

    def test_attempts_are_deduplicated_even_on_failure(self):
        data=io.BytesIO()
        with wave.open(data,'wb') as w:
            w.setparams((1,2,16000,0,'NONE','not compressed')); w.writeframes(b'\0\0'*16000*40)
        client=Mock(); client.__enter__=Mock(return_value=client); client.__exit__=Mock(return_value=False)
        client.audio.transcriptions.create.return_value.text='Actual mock ASR'
        factory=Mock(return_value=client); ledger={}
        transcribe_ready(ledger,data.getvalue(),[],'key',factory)
        factory.assert_not_called()
        transcribe_ready(ledger,data.getvalue(),[0],'key',factory)
        transcribe_ready(ledger,data.getvalue(),[0],'key',factory)
        self.assertEqual(client.audio.transcriptions.create.call_count,1)
        factory.assert_called_with(api_key='key',max_retries=0,timeout=45)
        client.audio.transcriptions.create.side_effect=RuntimeError('secret provider text')
        transcribe_ready(ledger,data.getvalue(),[1],'key',factory)
        transcribe_ready(ledger,data.getvalue(),[0,1],'key',factory)
        self.assertEqual(client.audio.transcriptions.create.call_count,2)
        self.assertNotIn('secret',ledger[1]['error'])

    def test_order_and_host_records(self):
        state={'transcript':'Host notes'}; reset_closure(state)
        state['gap_actions']={'gap_0':{'Owner':'Alice'}}
        state['gap_exceptions']={'gap_0':{'Reason':'Follow up'}}
        state['closure_inputs']={'transcript':'Host notes','agenda':'Review'}
        ledger={1:{'status':'done','text':'second'}}
        append_transcript(state,ledger,40)
        self.assertEqual(state['transcript'],'Host notes')
        ledger[0]={'status':'done','text':'first'}
        append_transcript(state,ledger,40)
        self.assertLess(state['transcript'].index('first'),state['transcript'].index('second'))
        prior=state['transcript']; append_transcript(state,ledger,40)
        self.assertEqual(state['transcript'],prior)
        self.assertFalse(sync_inputs(state,{'transcript':prior,'agenda':'Review'}))
        self.assertEqual(state['gap_actions']['gap_0']['Owner'],'Alice')
        self.assertTrue(state['gap_exceptions'])

if __name__=='__main__': unittest.main()
