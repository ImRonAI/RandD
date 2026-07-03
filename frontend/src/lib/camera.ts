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

  async start(deviceId?: string): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "environment" }),
        height: { ideal: 1080 },
        width: { ideal: 1920 },
      },
    });
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
