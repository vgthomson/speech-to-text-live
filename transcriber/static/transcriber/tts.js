(() => {
  const synth = window.speechSynthesis;
  const DEVANAGARI = /[ऀ-ॿ]/;
  let active = null;

  if (!synth) {
    document.querySelectorAll(".js-speak").forEach((el) => (el.hidden = true));
    return;
  }

  function pickVoice(text) {
    const voices = synth.getVoices();
    const find = (re) => voices.find((v) => re.test(v.lang));
    return DEVANAGARI.test(text) ? find(/^hi/i) : find(/^en[-_]IN/i) || find(/^en/i);
  }

  function reset() {
    if (active) {
      active.textContent = "Listen";
      active = null;
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".js-speak");
    if (!button) return;
    const wasActive = active === button;
    synth.cancel();
    reset();
    if (wasActive) return;

    const text = button.dataset.text || "";
    const utterance = new SpeechSynthesisUtterance(text);
    const voice = pickVoice(text);
    if (voice) utterance.voice = voice;
    utterance.lang = voice ? voice.lang : DEVANAGARI.test(text) ? "hi-IN" : "en-IN";
    utterance.onend = utterance.onerror = reset;
    button.textContent = "Stop";
    active = button;
    synth.speak(utterance);
  });
})();
