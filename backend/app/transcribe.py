"""Best-effort speech transcription for recorded walkthrough clips.

Reality check (verified live against this project's OpenAI key, 2026-07):
- The key exposes NO dedicated transcription models (whisper-1 and the
  *-transcribe family are gone from /v1/models), and the gpt-5.x chat/
  responses endpoints reject ``input_audio`` content on this project.
- What DOES work — proven end-to-end — is ``gpt-realtime-2`` (the same
  model the voice agent runs on) over the realtime WebSocket, with the
  OpenAI-Organization / OpenAI-Project headers the vended Strands model
  also sends. A synthesized narration clip round-tripped verbatim in ~3.6s.
- Browser MediaRecorder produces webm/opus; the realtime API wants raw
  pcm16 @ 24 kHz, so we transcode with the statically-bundled ffmpeg from
  ``imageio-ffmpeg`` (no system ffmpeg needed).

Failures degrade to None; the clip itself is still saved and embedded.
"""

import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

_RATE = 24000
_PROMPT = (
    "You are a transcription service. Output ONLY the verbatim transcript of "
    "the user's audio. If there is no intelligible speech, output exactly: [no speech]"
)


def _ffmpeg() -> Optional[str]:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _to_pcm(path: str | Path) -> Optional[bytes]:
    """Extract the audio track as raw pcm16 mono @ 24 kHz (realtime input format)."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return None
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path),
             "-vn", "-ac", "1", "-ar", str(_RATE), "-f", "s16le", "-"],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0 or len(proc.stdout) < 1000:
            return None
        return proc.stdout
    except Exception:
        return None


def _gemini_transcribe(path: str | Path) -> Optional[str]:
    """Transcribe via Gemini (the project's funded key). Returns None on any failure."""
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    pcm = _to_pcm(path)
    if not pcm:
        return None
    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=key)
        model = os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-flash-latest")
        # Raw pcm16 wrapped as a WAV so the API knows the format.
        header = _wav_header(len(pcm))
        response = client.models.generate_content(
            model=model,
            contents=[
                genai_types.Part.from_bytes(data=header + pcm, mime_type="audio/wav"),
                _PROMPT,
            ],
        )
        text = (response.text or "").strip()
        if not text or text.lower().startswith("[no speech"):
            return None
        return text
    except Exception:
        return None


def _wav_header(data_length: int) -> bytes:
    import struct

    return (
        b"RIFF" + struct.pack("<I", 36 + data_length) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, _RATE, _RATE * 2, 2, 16)
        + b"data" + struct.pack("<I", data_length)
    )


def measure_loudness(path: str | Path) -> Optional[float]:
    """Max audio level of a clip in dBFS (~0 = loud, < -50 = effectively silent)."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return None
    try:
        proc = subprocess.run(
            [ffmpeg, "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        for line in proc.stderr.splitlines():
            if "max_volume:" in line:
                return float(line.split("max_volume:")[1].replace("dB", "").strip())
    except Exception:
        pass
    return None


def compress_clip(path: str | Path) -> Optional[Path]:
    """Re-encode a walkthrough clip to compact web MP4 (640px H.264 + mono AAC).

    Browser MediaRecorder clips run ~3.5 MB per 10 s and get baked into the
    self-contained form export as base64 — the reason exports ballooned to
    ~16 MB. The compact MP4 is ~85% smaller and also plays on iOS Safari,
    which cannot play webm. Returns None (caller keeps the original) on any
    failure or if the result isn't actually smaller.
    """
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return None
    src = Path(path)
    out = src.with_name(src.stem + "-web.mp4")
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
             "-vf", "scale='min(640,iw)':-2",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
             "-c:a", "aac", "-b:a", "64k", "-ac", "1",
             "-movflags", "+faststart", str(out)],
            capture_output=True, timeout=300,
        )
        if proc.returncode != 0 or not out.exists():
            return None
        if out.stat().st_size >= src.stat().st_size:
            out.unlink(missing_ok=True)
            return None
        return out
    except Exception:
        return None


def transcribe_audio(path: str | Path, mime: str = "video/webm") -> Optional[str]:
    """Transcribe the audio track of a media file. Returns None when unavailable."""
    if os.getenv("DISABLE_TRANSCRIPTION", "").lower() in ("1", "true", "yes"):
        return None  # cost kill-switch: clips still save/embed, just no transcript
    # Gemini first: the OpenAI project is quota-limited, which silently produced
    # "no transcript" for every clip (and made the agent report soundless video).
    text = _gemini_transcribe(path)
    if text:
        return text
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    pcm = _to_pcm(path)
    if not pcm:
        return None
    try:
        from websockets.sync.client import connect

        model = os.getenv("OPENAI_TRANSCRIBE_MODEL") or os.getenv("OPENAI_MODEL", "gpt-realtime-2")
        headers = {"Authorization": f"Bearer {key}"}
        if os.getenv("OPENAI_ORGANIZATION"):
            headers["OpenAI-Organization"] = os.environ["OPENAI_ORGANIZATION"]
        if os.getenv("OPENAI_PROJECT"):
            headers["OpenAI-Project"] = os.environ["OPENAI_PROJECT"]

        with connect(
            f"wss://api.openai.com/v1/realtime?model={model}",
            additional_headers=headers,
            max_size=1 << 24,
        ) as ws:
            ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "output_modalities": ["text"],
                    "audio": {"input": {"format": {"type": "audio/pcm", "rate": _RATE},
                                         "turn_detection": None}},
                    "instructions": _PROMPT,
                },
            }))
            step = _RATE * 2 // 5  # ~200ms chunks
            for i in range(0, len(pcm), step):
                ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm[i:i + step]).decode(),
                }))
            ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            ws.send(json.dumps({"type": "response.create"}))
            text = ""
            while True:
                event = json.loads(ws.recv(timeout=120))
                etype = event.get("type", "")
                if "text.delta" in etype:
                    text += event.get("delta", "")
                elif etype == "response.done":
                    break
                elif etype == "error":
                    return None
        text = text.strip()
        if not text or text.lower().startswith("[no speech"):
            return None
        return text
    except Exception:
        return None
