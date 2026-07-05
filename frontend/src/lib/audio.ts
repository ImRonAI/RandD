/**
 * Raw PCM16 audio pipeline for Gemini Live:
 * - MicCapture: getUserMedia -> AudioWorklet -> 16 kHz mono PCM16 base64 chunks
 * - PcmPlayer: schedules streamed 24 kHz PCM16 chunks gaplessly via WebAudio
 * - pcm16ToWavBlob: wraps accumulated model audio into a WAV for AudioPlayer replay
 */

// 512 samples per message (32 ms at 16 kHz) — the same frames_per_buffer the
// strands BidiAudioIO reference uses. Unbatched worklet blocks are 128 samples
// (2.7 ms), which floods the WebSocket with ~375 messages/second.
const CAPTURE_CHUNK = 512;

const WORKLET_SOURCE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(${CAPTURE_CHUNK});
    this.offset = 0;
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) return true;
    let read = 0;
    while (read < channel.length) {
      const take = Math.min(channel.length - read, this.buffer.length - this.offset);
      this.buffer.set(channel.subarray(read, read + take), this.offset);
      this.offset += take;
      read += take;
      if (this.offset === this.buffer.length) {
        this.port.postMessage(this.buffer.slice(0));
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCaptureProcessor);
`;

const floatTo16 = (float32: Float32Array): Int16Array => {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
};

// Fallback resampler for browsers that ignore the AudioContext sampleRate
// hint. Averages each source window (box low-pass) instead of picking single
// samples — bare decimation aliases everything above the Nyquist rate into
// the speech band and the model hears garbage.
const downsample = (
  input: Float32Array,
  fromRate: number,
  toRate: number
): Float32Array => {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const length = Math.floor(input.length / ratio);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.max(start + 1, Math.floor((i + 1) * ratio)), input.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = sum / (end - start);
  }
  return out;
};

export const bytesToBase64 = (bytes: Uint8Array): string => {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
};

export const base64ToBytes = (base64: string): Uint8Array => {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
};

export class MicCapture {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;

  constructor(
    private readonly targetRate: number,
    private readonly onChunk: (base64Pcm16: string) => void
  ) {}

  get active(): boolean {
    return this.stream !== null;
  }

  /** The live mic stream, so recorders can reuse the already-granted track. */
  get mediaStream(): MediaStream | null {
    return this.stream;
  }

  async start(deviceId?: string): Promise<void> {
    await this.stop();
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: deviceId ? { deviceId: { exact: deviceId } } : true,
    });
    // Ask the context for the model's input rate directly — the browser then
    // resamples the mic with a proper filter and no client-side decimation.
    this.context = new AudioContext({ sampleRate: this.targetRate });
    const blob = new Blob([WORKLET_SOURCE], { type: "application/javascript" });
    const url = URL.createObjectURL(blob);
    try {
      await this.context.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    this.source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, "pcm-capture");
    let pending = new Float32Array(0);
    this.node.port.onmessage = (event: MessageEvent<Float32Array>) => {
      const rate = this.context?.sampleRate ?? this.targetRate;
      const resampled = downsample(event.data, rate, this.targetRate);
      // Re-batch after any fallback resample so every message stays CAPTURE_CHUNK.
      const merged = new Float32Array(pending.length + resampled.length);
      merged.set(pending);
      merged.set(resampled, pending.length);
      let offset = 0;
      while (merged.length - offset >= CAPTURE_CHUNK) {
        const pcm = floatTo16(merged.subarray(offset, offset + CAPTURE_CHUNK));
        this.onChunk(bytesToBase64(new Uint8Array(pcm.buffer)));
        offset += CAPTURE_CHUNK;
      }
      pending = merged.slice(offset);
    };
    this.source.connect(this.node);
  }

  async stop(): Promise<void> {
    this.node?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    if (this.context && this.context.state !== "closed") {
      await this.context.close();
    }
    this.node = null;
    this.source = null;
    this.stream = null;
    this.context = null;
  }
}

export class PcmPlayer {
  private context: AudioContext | null = null;
  private nextTime = 0;
  private scheduled = new Set<AudioBufferSourceNode>();

  constructor(private readonly onPlaybackChange?: (playing: boolean) => void) {
    // Create the context NOW, while we're still inside the user's click
    // (connect). Contexts created later inside WebSocket handlers start
    // suspended under Chrome's autoplay policy — audio schedules but never
    // sounds, or cuts out. MDN's autoplay guidance: create/resume on gesture.
    this.context = new AudioContext();
    void this.context.resume();
  }

  play(base64Pcm16: string, sampleRate: number): void {
    if (!this.context || this.context.state === "closed") {
      this.context = new AudioContext();
      this.nextTime = 0;
    }
    if (this.context.state === "suspended") {
      void this.context.resume();
    }
    const bytes = base64ToBytes(base64Pcm16);
    const pcm = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
    const buffer = this.context.createBuffer(1, pcm.length, sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) {
      channel[i] = pcm[i] / 0x8000;
    }
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    const start = Math.max(this.context.currentTime, this.nextTime);
    source.start(start);
    this.nextTime = start + buffer.duration;
    this.scheduled.add(source);
    this.onPlaybackChange?.(true);
    source.onended = () => {
      this.scheduled.delete(source);
      if (this.scheduled.size === 0) {
        this.onPlaybackChange?.(false);
      }
    };
  }

  /** Stop everything immediately (used on bidi_interruption). */
  flush(): void {
    for (const source of this.scheduled) {
      try {
        source.stop();
      } catch {
        // already stopped
      }
    }
    this.scheduled.clear();
    this.nextTime = 0;
    this.onPlaybackChange?.(false);
  }

  async close(): Promise<void> {
    this.flush();
    if (this.context && this.context.state !== "closed") {
      await this.context.close();
    }
    this.context = null;
  }
}

export const pcm16ToWavBlob = (
  chunks: Uint8Array[],
  sampleRate: number
): Blob => {
  const dataLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const writeString = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) {
      view.setUint8(offset + i, text.charCodeAt(i));
    }
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, dataLength, true);
  return new Blob([header, ...(chunks as unknown as BlobPart[])], {
    type: "audio/wav",
  });
};
