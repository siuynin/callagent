// Voice spike client: mic -> PCM16 16 kHz -> WebSocket; agent PCM16 (24 kHz) -> gapless playback.
(() => {
  const $ = (id) => document.getElementById(id);
  const CAPTURE_RATE = 16000;
  const FRAME_SAMPLES = 640; // 40 ms

  let ws = null, captureCtx = null, playCtx = null, stream = null, worklet = null;
  let playRate = 24000, nextTime = 0, sources = new Set();
  let turns = 0, interrupts = 0, agentBubble = null, callerBubble = null;

  const workletCode = `
    class Capture extends AudioWorkletProcessor {
      constructor() { super(); this.buf = new Int16Array(${FRAME_SAMPLES}); this.n = 0; }
      process(inputs) {
        const ch = inputs[0][0];
        if (!ch) return true;
        let sum = 0;
        for (let i = 0; i < ch.length; i++) {
          const s = Math.max(-1, Math.min(1, ch[i]));
          sum += s * s;
          this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
          if (this.n === this.buf.length) {
            this.port.postMessage({ pcm: this.buf.buffer.slice(0), rms: Math.sqrt(sum / ch.length) });
            this.n = 0;
          }
        }
        return true;
      }
    }
    registerProcessor('capture', Capture);`;

  function status(text) { $('status').textContent = text; }

  function bubble(role, text, cls = '') {
    const el = document.createElement('div');
    el.className = `bubble ${role} ${cls}`;
    const label = { agent: 'AI', caller: 'Khách', system: '' }[role];
    el.innerHTML = label ? `<small>${label}</small>` : '';
    el.appendChild(document.createTextNode(text));
    $('transcript').appendChild(el);
    $('transcript').scrollTop = $('transcript').scrollHeight;
    return el;
  }

  function appendText(el, text) { el.lastChild.textContent += text; $('transcript').scrollTop = 1e9; }

  function toolLine(text) {
    const el = document.createElement('div');
    el.textContent = text;
    $('tools').prepend(el);
  }

  function clearPlayback() {
    for (const s of sources) { try { s.stop(); } catch (_) {} }
    sources.clear();
    nextTime = playCtx ? playCtx.currentTime : 0;
  }

  function play(buf) {
    if (!playCtx) return;
    const pcm = new Int16Array(buf);
    const audio = playCtx.createBuffer(1, pcm.length, playRate);
    const ch = audio.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 0x8000;
    const src = playCtx.createBufferSource();
    src.buffer = audio;
    src.connect(playCtx.destination);
    nextTime = Math.max(nextTime, playCtx.currentTime + 0.02);
    src.start(nextTime);
    nextTime += audio.duration;
    sources.add(src);
    src.onended = () => sources.delete(src);
  }

  function onEvent(m) {
    switch (m.type) {
      case 'ready': status(`Đang gọi · ${m.provider}${m.phone_sim ? ' · đường điện thoại 8 kHz' : ''}`); break;
      case 'audio_format':
        if (m.rate !== playRate) { playRate = m.rate; }
        break;
      case 'clear': clearPlayback(); break;
      case 'interrupted':
        interrupts++; $('interrupts').textContent = interrupts;
        bubble('system', 'Khách chen ngang · đã dừng phát');
        agentBubble = null;
        break;
      case 'transcript':
        if (m.role === 'agent') {
          callerBubble = null;
          agentBubble = agentBubble || bubble('agent', '');
          appendText(agentBubble, m.text);
        } else {
          agentBubble = null;
          callerBubble = callerBubble || bubble('caller', '');
          appendText(callerBubble, m.text);
        }
        break;
      case 'turn_complete':
        agentBubble = null; callerBubble = null;
        if (m.latency_ms && m.latency_ms.length) {
          turns++; $('turns').textContent = turns;
          $('lastLatency').textContent = `${Math.round(m.latency_ms[0])} ms`;
        }
        break;
      case 'tool_call': toolLine(`→ ${m.name} ${JSON.stringify(m.args)}`); break;
      case 'tool_result': toolLine(`← ${m.name}: ${m.result.status}${m.result.message ? ' · ' + m.result.message : ''}`); break;
      case 'reconnected': bubble('system', `Đã nối lại phiên model (${m.reason})`); break;
      case 'error': bubble('system', `Lỗi: ${m.message}`, 'flag'); status('Lỗi'); break;
      case 'summary':
        $('summary').hidden = false;
        $('summary').textContent = JSON.stringify(m.summary, null, 2);
        if (m.summary.false_confirmations > 0) bubble('system', `Cảnh báo: ${m.summary.false_confirmations} lần AI báo đã hoàn tất trước khi công cụ thành công`, 'flag');
        break;
    }
  }

  async function start() {
    $('start').disabled = true;
    $('summary').hidden = true; $('transcript').innerHTML = ''; $('tools').innerHTML = '';
    turns = 0; interrupts = 0; $('turns').textContent = '0'; $('interrupts').textContent = '0'; $('lastLatency').textContent = '–';
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      status('Không truy cập được micro: ' + e.message); $('start').disabled = false; return;
    }
    captureCtx = new AudioContext({ sampleRate: CAPTURE_RATE });
    playCtx = new AudioContext({ sampleRate: playRate });
    const url = URL.createObjectURL(new Blob([workletCode], { type: 'application/javascript' }));
    await captureCtx.audioWorklet.addModule(url);
    worklet = new AudioWorkletNode(captureCtx, 'capture');
    captureCtx.createMediaStreamSource(stream).connect(worklet);

    const sim = $('phoneSim').checked ? '?phone_sim=alaw' : '';
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/spike${sim}`);
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => { status('Đang mở phiên model…'); $('stop').disabled = false; };
    ws.onmessage = (e) => (typeof e.data === 'string' ? onEvent(JSON.parse(e.data)) : play(e.data));
    ws.onclose = () => { status('Đã kết thúc'); cleanup(); };
    worklet.port.onmessage = ({ data }) => {
      $('level').style.width = `${Math.min(100, data.rms * 400)}%`;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(data.pcm);
    };
  }

  function stop() {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'hangup' }));
    $('stop').disabled = true;
    status('Đang lưu báo cáo…');
  }

  function cleanup() {
    clearPlayback();
    if (worklet) worklet.port.onmessage = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    if (captureCtx) captureCtx.close();
    if (playCtx) playCtx.close();
    captureCtx = playCtx = stream = worklet = ws = null;
    $('start').disabled = false; $('stop').disabled = true; $('level').style.width = '0';
  }

  fetch('/api/info').then((r) => r.json()).then((info) => {
    const el = $('provider');
    el.textContent = info.provider === 'gemini' ? `Gemini Live · ${info.model}` : 'MOCK · không gọi model thật';
    if (info.provider !== 'gemini') el.classList.add('mock');
    if (info.provider === 'gemini' && !info.key_configured) el.textContent += ' · thiếu API key';
  });
  $('start').onclick = start;
  $('stop').onclick = stop;
})();
