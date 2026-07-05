/**
 * CameraCapture: getUserMedia video -> canvas JPEG frames (base64).
 *
 * The backend agent runs in a container with no camera, so device cameras are
 * captured here in the browser and streamed to the model as bidi_image_input
 * frames (natively understood by the multimodal realtime models).
 */
export class CameraCapture {
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private timer: number | null = null;

  constructor(
    private readonly onFrame: (jpegBase64: string) => void,
    private readonly intervalMs = 2000,
    private readonly maxDim = 1024,
    private readonly quality = 0.7
  ) {}

  get mediaStream(): MediaStream | null {
    return this.stream;
  }

  async start(deviceId?: string, facing: "environment" | "user" = "environment"): Promise<void> {
    // Constraint fallback chain so a camera is found on every device class:
    // 1. explicit device pick  2. preferred facing (rear by default; flipped
    // on request)  3. the other facing (FaceTime on macOS/iOS, front on
    // Android)  4. any available camera
    const quality = { height: { ideal: 1080 }, width: { ideal: 1920 } };
    const other = facing === "environment" ? "user" : "environment";
    const attempts: MediaTrackConstraints[] = deviceId
      ? [{ deviceId: { exact: deviceId }, ...quality }]
      : [
          { facingMode: facing, ...quality },
          { facingMode: other, ...quality },
          { ...quality },
        ];
    let lastError: unknown;
    for (const video of attempts) {
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ video });
        lastError = undefined;
        break;
      } catch (error) {
        lastError = error;
      }
    }
    if (!this.stream) {
      throw lastError instanceof Error ? lastError : new Error("no camera available");
    }
    this.video = document.createElement("video");
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.srcObject = this.stream;
    await this.video.play();
    this.timer = window.setInterval(() => {
      const frame = this.snap();
      if (frame) this.onFrame(frame);
    }, this.intervalMs);
  }

  /** Capture a single JPEG frame (base64, no data: prefix). */
  snap(): string | null {
    const video = this.video;
    if (!video || video.readyState < 2) return null;
    const scale = Math.min(1, this.maxDim / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", this.quality);
    return dataUrl.slice(dataUrl.indexOf(",") + 1);
  }

  /**
   * Record a full-motion clip WITH microphone audio (MediaRecorder).
   *
   * Prefers the ALREADY-LIVE session mic track (`liveMic`) — during a voice
   * session the mic is held by MicCapture, and opening a second capture
   * returns a silent/dead track on iOS Safari and some Android builds (the
   * root cause of soundless walkthrough clips). A track can feed multiple
   * consumers, so recording taps it without disturbing the agent audio.
   * Falls back to a fresh mic grab (released afterwards) outside sessions,
   * and degrades to video-only when no mic is available at all.
   */
  async record(durationMs: number, liveMic?: MediaStream | null): Promise<Blob> {
    if (!this.stream) throw new Error("camera not started");
    // CLONE the live session track for the recorder — feeding the same track
    // object to a second consumer records silence on iOS Safari and some
    // Chrome builds (measured: clips with a dead -70 dB opus track).
    const cloned = (liveMic?.getAudioTracks() ?? [])
      .filter((track) => track.readyState === "live" && !track.muted)
      .map((track) => track.clone());
    let mic: MediaStream | null = null;
    if (cloned.length === 0) {
      try {
        mic = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
      } catch {
        // no mic permission — record video-only rather than failing
      }
    }
    const combined = new MediaStream([
      ...this.stream.getVideoTracks(),
      ...(cloned.length > 0 ? cloned : mic?.getAudioTracks() ?? []),
    ]);
    const mimeType = [
      "video/webm;codecs=vp9,opus",
      "video/webm;codecs=vp8,opus",
      "video/webm",
      "video/mp4",
    ].find((t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t));
    const recorder = new MediaRecorder(combined, mimeType ? { mimeType } : undefined);
    const chunks: BlobPart[] = [];
    const done = new Promise<Blob>((resolve, reject) => {
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      recorder.onstop = () =>
        resolve(new Blob(chunks, { type: recorder.mimeType || "video/webm" }));
      recorder.onerror = () => reject(new Error("recording failed"));
    });
    recorder.start();
    try {
      await new Promise((r) => setTimeout(r, durationMs));
    } finally {
      if (recorder.state !== "inactive") recorder.stop();
    }
    const blob = await done;
    for (const track of mic?.getTracks() ?? []) track.stop();
    for (const track of cloned) track.stop();
    return blob;
  }

  stop(): void {
    if (this.timer !== null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
    this.video?.pause();
    this.video = null;
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    this.stream = null;
  }
}
