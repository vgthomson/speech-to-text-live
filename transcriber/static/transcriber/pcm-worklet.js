class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetRate || 16000;
    this.ratio = sampleRate / this.targetRate;
    this.chunkSamples = Math.round((this.targetRate * (opts.chunkMs || 100)) / 1000);
    this.pos = 0;
    this.out = new Int16Array(this.chunkSamples);
    this.outIndex = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input || input.length === 0) return true;

    while (this.pos < input.length) {
      const i = Math.floor(this.pos);
      const frac = this.pos - i;
      const a = input[i];
      const b = i + 1 < input.length ? input[i + 1] : a;
      const s = Math.max(-1, Math.min(1, a + (b - a) * frac));
      this.out[this.outIndex++] = s < 0 ? s * 0x8000 : s * 0x7fff;

      if (this.outIndex === this.chunkSamples) {
        this.port.postMessage({ pcm: this.out.buffer }, [this.out.buffer]);
        this.out = new Int16Array(this.chunkSamples);
        this.outIndex = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= input.length;
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
