export default function(component) {
  const { parentElement, data, setStateValue } = component;
  let state = parentElement._meetingAudio;
  if (!state) {
    const audio = document.createElement('audio');
    audio.controls = true;
    audio.preload = 'metadata';
    audio.style.width = '100%';
    const label = document.createElement('p');
    label.style.fontSize = '14px';
    parentElement.append(audio, label);
    state = {audio, label, sent: '', publish: null};
    parentElement._meetingAudio = state;
    const report = () => {
      const ranges = [];
      for (let i=0; i<audio.played.length; i++) ranges.push([audio.played.start(i), audio.played.end(i)]);
      const complete = [];
      for (let i=0; i<state.count; i++) {
        const start=i*state.seconds, end=Math.min((i+1)*state.seconds,state.duration);
        if (ranges.some(([a,b]) => a <= start && b >= end)) complete.push(i);
      }
      state.label.textContent = `${audio.currentTime.toFixed(1)} / ${state.duration.toFixed(1)} seconds — ${complete.length} fully played segment(s)`;
      const signature = JSON.stringify(complete);
      if (complete.length && signature !== state.sent) {
        state.sent = signature;
        state.publish('played', {fingerprint:state.fingerprint, ranges});
      }
    };
    audio.addEventListener('timeupdate', report);
    audio.addEventListener('pause', report);
    audio.addEventListener('ended', report);
    audio.addEventListener('seeked', report);
  }
  state.publish = setStateValue;
  state.count = data.count; state.seconds = data.seconds; state.duration = data.duration;
  if (state.fingerprint !== data.fingerprint) {
    state.audio.pause();
    state.fingerprint = data.fingerprint;
    state.sent = '';
    state.audio.src = 'data:audio/wav;base64,' + data.audio;
    state.label.textContent = 'Ready — no audio has been transcribed.';
  }
}
