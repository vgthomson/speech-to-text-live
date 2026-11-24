(() => {
  const root = document.getElementById("recorder");
  const recordBtn = document.getElementById("record-btn");
  const statusEl = document.getElementById("status");
  const finalEl = document.getElementById("final-text");
  const interimEl = document.getElementById("interim-text");
  const noteEl = document.getElementById("note");
  const hintEl = document.getElementById("hint");
  const languageEl = document.getElementById("language");
  const HINTS = {
    idle: "Click the button to start recording",
    connecting: "Allow microphone access if your browser asks",
    recording: "Speak now. Text appears after each short pause. Click the button again to stop.",
    finishing: "Transcribing the last words and saving…",
  };

  let state = "idle";
  let ws = null;
  let audio = null;

  function setState(next, label) {
    state = next;
    statusEl.textContent = label;
    hintEl.textContent = HINTS[next] || "";
    root.classList.toggle("is-recording", next === "recording");
    recordBtn.disabled = next === "connecting" || next === "finishing";
    languageEl.disabled = next !== "idle";
    recordBtn.setAttribute("aria-label", next === "recording" ? "Stop recording" : "Start recording");
  }

  function note(text, isError = false) {
    noteEl.textContent = text;
    noteEl.classList.toggle("error", isError);
    noteEl.hidden = !text;
  }

  async function startAudio() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const ctx = new AudioContext();
    await ctx.audioWorklet.addModule(root.dataset.workletUrl);
    const source = ctx.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(ctx, "pcm-capture", { processorOptions: { targetRate: 16000, chunkMs: 100 } });
    node.port.onmessage = ({ data }) => {
      if (ws && ws.readyState === WebSocket.OPEN && state === "recording") ws.send(data.pcm);
    };
    source.connect(node);
    node.connect(ctx.destination);
    audio = { ctx, stream, node, source };
  }

  function stopAudio() {
    if (!audio) return;
    audio.stream.getTracks().forEach((t) => t.stop());
    audio.source.disconnect();
    audio.node.disconnect();
    audio.ctx.close();
    audio = null;
  }

  function openSocket() {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${proto}://${location.host}/ws/transcribe/`);
      socket.onopen = () => resolve(socket);
      socket.onerror = () => reject(new Error("Could not connect to the server."));
      socket.onmessage = (e) => handleMessage(JSON.parse(e.data));
      socket.onclose = () => {
        if (ws === socket) ws = null;
        if (state === "recording" || state === "connecting") {
          stopAudio();
          setState("idle", "Disconnected");
        }
      };
    });
  }

  function closeSocket() {
    if (ws) {
      const s = ws;
      ws = null;
      s.close();
    }
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case "ready":
        setState("recording", "Listening…");
        break;
      case "interim":
        interimEl.textContent = msg.text ? ` ${msg.text}` : "";
        break;
      case "final":
        finalEl.textContent = msg.text;
        interimEl.textContent = "";
        break;
      case "limit":
        stopLocal();
        break;
      case "saved":
        finalEl.textContent = msg.text;
        interimEl.textContent = "";
        note("Saved to history.");
        closeSocket();
        setState("idle", "Ready");
        break;
      case "stopped":
        closeSocket();
        setState("idle", "Ready");
        break;
      case "error":
        if (state === "connecting") {
          stopAudio();
          closeSocket();
          setState("idle", "Ready");
        }
        note(msg.message, true);
        break;
    }
  }

  async function start() {
    finalEl.textContent = "";
    interimEl.textContent = "";
    note("");
    setState("connecting", "Connecting…");
    try {
      await startAudio();
      ws = await openSocket();
      ws.send(JSON.stringify({ type: "start", language: languageEl.value }));
    } catch (err) {
      stopAudio();
      closeSocket();
      setState("idle", "Ready");
      note(err.name === "NotAllowedError" ? "Microphone permission was denied." : err.message, true);
    }
  }

  function stopLocal() {
    stopAudio();
    setState("finishing", "Finishing…");
  }

  function stop() {
    stopLocal();
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
  }

  recordBtn.addEventListener("click", () => (state === "recording" ? stop() : start()));
})();
