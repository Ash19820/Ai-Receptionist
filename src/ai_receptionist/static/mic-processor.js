class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions?.targetRate || 16000;
    this.inputRate = sampleRate;
    this.step = this.inputRate / this.targetRate;
    this.position = 0;
    this.pending = [];
    this.previous = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    let position = this.position;
    while (position < channel.length) {
      const left = Math.floor(position);
      const right = Math.min(left + 1, channel.length - 1);
      const fraction = position - left;
      const sample = channel[left] * (1 - fraction) + channel[right] * fraction;
      this.pending.push(Math.max(-1, Math.min(1, sample)));
      position += this.step;
    }
    this.position = position - channel.length;

    while (this.pending.length >= 320) {
      const frame = this.pending.splice(0, 320);
      const pcm = new Int16Array(320);
      for (let i = 0; i < frame.length; i++) {
        pcm[i] = Math.round(frame[i] * (frame[i] < 0 ? 32768 : 32767));
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor);
