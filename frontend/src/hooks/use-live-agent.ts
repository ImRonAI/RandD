/**
 * useLiveAgent — single source of truth for a live Gemini Live session.
 *
 * Connects to the FastAPI bridge (`/ws`), streams mic PCM up and folds every
 * BidiAgent output event (transcripts, audio, tool use/results, usage,
 * interruptions) into UI state consumed directly by AI Elements components.
 * All data is live agent output — nothing is simulated.
 */

import { nanoid } from "nanoid";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  base64ToBytes,
  MicCapture,
  PcmPlayer,
  pcm16ToWavBlob,
} from "@/lib/audio";
import { CameraCapture } from "@/lib/camera";
import type {
  AgentCard,
  ConnectionStatus,
  LiveMessage,
  LiveModel,
  LiveSegment,
  LiveToolPart,
  LiveThoughtPart,
  LiveSearchPart,
  LiveUsage,
  LiveVoice,
  PersonaState,
  QueueEntry,
  SessionMode,
} from "@/lib/live-types";

const MIC_SAMPLE_RATE = 16000;

type ChatStatus = "ready" | "submitted" | "streaming" | "error";

type ServerEvent = Record<string, unknown> & { type: string };

type SubmitPayload = {
  text: string;
  files: { url: string; mediaType: string; filename?: string }[];
};

const wsUrl = (mode: SessionMode, voice: string, provider: string, token: string) => {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws?mode=${mode}&voice=${encodeURIComponent(voice)}&provider=${encodeURIComponent(provider)}&token=${encodeURIComponent(token)}`;
};

export const useLiveAgent = () => {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [chatStatus, setChatStatus] = useState<ChatStatus>("ready");
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [segments, setSegments] = useState<LiveSegment[]>([]);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [usage, setUsage] = useState<LiveUsage | null>(null);
  const [micActive, setMicActive] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [mode, setMode] = useState<SessionMode>("audio");
  const [voice, setVoiceState] = useState("Puck");
  const [model, setModelState] = useState<LiveModel["id"]>("gemini");
  const [models, setModels] = useState<LiveModel[]>([]);
  const [micDeviceId, setMicDeviceId] = useState<string | undefined>();
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraDeviceId, setCameraDeviceId] = useState<string | undefined>();
  const [cameraFacing, setCameraFacingState] = useState<"environment" | "user">("environment");
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [recording, setRecording] = useState(false);
  const [agentCard, setAgentCard] = useState<AgentCard | null>(null);
  const [voices, setVoices] = useState<LiveVoice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);

  const socketRef = useRef<WebSocket | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const cameraRef = useRef<CameraCapture | null>(null);
  const lastFrameRef = useRef<string | null>(null);
  const cameraControlRef = useRef<{
    start: () => Promise<void>;
    stop: () => void;
    snap: () => boolean;
    flip: () => Promise<void>;
    setFacing: (facing: "environment" | "user") => Promise<void>;
    record: (durationSec: number, section: string) => Promise<boolean>;
  } | null>(null);
  const handledCameraCallsRef = useRef<Set<string>>(new Set());
  const playerRef = useRef<PcmPlayer | null>(null);
  const audioChunksRef = useRef<Uint8Array[]>([]);
  const audioRateRef = useRef(24000);
  const sessionStartRef = useRef(0);
  const chatStatusRef = useRef<ChatStatus>("ready");
  const queueRef = useRef<QueueEntry[]>([]);
  const micActiveRef = useRef(false);

  chatStatusRef.current = chatStatus;
  queueRef.current = queue;
  micActiveRef.current = micActive;

  const refreshAgentCard = useCallback(async () => {
    try {
      const res = await fetch("/api/agent", { credentials: "include" });
      if (res.ok) setAgentCard(await res.json());
    } catch {
      // backend not up yet — the connect flow surfaces errors
    }
  }, []);

  const refreshWorkspace = useCallback(async () => {
    try {
      const res = await fetch("/api/workspace", { credentials: "include" });
      if (res.ok) {
        const data = (await res.json()) as { files: string[] };
        setWorkspaceFiles(data.files);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshAgentCard();
    refreshWorkspace();
    fetch("/api/models", { credentials: "include" })
      .then((res) => (res.ok ? res.json() : { default: "openai", models: [] }))
      .then((data: { default: LiveModel["id"]; models: LiveModel[] }) => {
        setModels(data.models);
        setModelState(data.default);
      })
      .catch(() => setModels([]));
  }, [refreshAgentCard, refreshWorkspace]);

  useEffect(() => {
    fetch(`/api/voices?provider=${model}`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : { voices: [] }))
      .then((data: { voices: LiveVoice[] }) => {
        setVoices(data.voices);
        // Snap the voice to this provider's list if the current one isn't valid for it.
        if (data.voices.length) {
          setVoiceState((prev) =>
            data.voices.some((entry) => entry.id === prev)
              ? prev
              : models.find((entry) => entry.id === model)?.defaultVoice ?? data.voices[0].id
          );
        }
      })
      .catch(() => setVoices([]));
  }, [model, models]);

  const appendText = useCallback((role: "user" | "assistant", text: string) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next.at(-1);
      if (last && last.role === role) {
        const parts = [...last.parts];
        const lastPart = parts.at(-1);
        if (lastPart?.type === "text" && lastPart.state === "streaming") {
          parts[parts.length - 1] = {
            ...lastPart,
            text: lastPart.text + text,
          };
        } else {
          parts.push({ type: "text", text, state: "streaming" });
        }
        next[next.length - 1] = { ...last, parts };
        return next;
      }
      next.push({
        id: nanoid(),
        role,
        parts: [{ type: "text", text, state: "streaming" }],
        createdAt: Date.now(),
      });
      return next;
    });
    const now = (performance.now() - sessionStartRef.current) / 1000;
    setSegments((prev) => [
      ...prev,
      {
        id: nanoid(),
        text,
        role,
        startSecond: now,
        endSecond: now + Math.max(0.3, text.length * 0.05),
      },
    ]);
  }, []);

  const finalizeAssistantTurn = useCallback(() => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next.at(-1);
      if (last?.role !== "assistant") return prev;
      const parts = last.parts.map((part) =>
        part.type === "text" ? { ...part, state: "done" as const } : part
      );
      let audioUrl = last.audioUrl;
      if (audioChunksRef.current.length > 0) {
        const blob = pcm16ToWavBlob(audioChunksRef.current, audioRateRef.current);
        audioUrl = URL.createObjectURL(blob);
        audioChunksRef.current = [];
      }
      next[next.length - 1] = { ...last, parts, audioUrl };
      return next;
    });
  }, []);

  const upsertToolPart = useCallback((part: LiveToolPart) => {
    setMessages((prev) => {
      const next = [...prev];
      let last = next.at(-1);
      if (!last || last.role !== "assistant") {
        last = {
          id: nanoid(),
          role: "assistant",
          parts: [],
          createdAt: Date.now(),
        };
        next.push(last);
      }
      const parts = [...last.parts];
      const index = parts.findIndex(
        (existing) =>
          existing.type.startsWith("tool-") &&
          (existing as LiveToolPart).toolCallId === part.toolCallId
      );
      if (index >= 0) {
        parts[index] = { ...(parts[index] as LiveToolPart), ...part };
      } else {
        parts.push(part);
      }
      next[next.length - 1] = { ...last, parts };
      return next;
    });
  }, []);

  const upsertThoughtPart = useCallback((text: string, state: "streaming" | "done") => {
    setMessages((prev) => {
      const next = [...prev];
      let last = next.at(-1);
      if (!last || last.role !== "assistant") {
        last = {
          id: nanoid(),
          role: "assistant",
          parts: [],
          createdAt: Date.now(),
        };
        next.push(last);
      }
      const parts = [...last.parts];
      const index = parts.findIndex((existing) => existing.type === "thought");
      if (index >= 0) {
        const existingPart = parts[index] as LiveThoughtPart;
        parts[index] = {
          ...existingPart,
          text: state === "streaming" ? existingPart.text + text : existingPart.text,
          state,
        };
      } else {
        parts.push({
          type: "thought",
          text,
          state,
        });
      }
      next[next.length - 1] = { ...last, parts };
      return next;
    });
  }, []);

  const sendRaw = useCallback((payload: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
    }
  }, []);

  const deliver = useCallback(
    (entry: SubmitPayload) => {
      if (entry.text.trim()) {
        appendUserMessage(entry);
        sendRaw({ type: "bidi_text_input", text: entry.text, role: "user" });
      }
      for (const file of entry.files) {
        if (file.mediaType.startsWith("image/")) {
          const base64 = file.url.split(",")[1] ?? "";
          sendRaw({
            type: "bidi_image_input",
            image: base64,
            mime_type: file.mediaType,
          });
        }
      }
      setChatStatus("submitted");
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sendRaw]
  );

  const appendUserMessage = useCallback((entry: SubmitPayload) => {
    setMessages((prev) => [
      ...prev,
      {
        id: nanoid(),
        role: "user",
        parts: [
          ...entry.files.map((file) => ({
            type: "file" as const,
            url: file.url,
            mediaType: file.mediaType,
            filename: file.filename,
          })),
          ...(entry.text.trim()
            ? [{ type: "text" as const, text: entry.text, state: "done" as const }]
            : []),
        ],
        createdAt: Date.now(),
      },
    ]);
  }, []);

  const drainQueue = useCallback(() => {
    const pending = queueRef.current.find((entry) => entry.status === "pending");
    if (!pending) return;
    setQueue((prev) =>
      prev.map((entry) =>
        entry.id === pending.id ? { ...entry, status: "completed" } : entry
      )
    );
    deliver(pending);
  }, [deliver]);

  const handleEvent = useCallback(
    (event: ServerEvent) => {
      switch (event.type) {
        case "bidi_connection_start": {
          setStatus("connected");
          sessionStartRef.current = performance.now();
          break;
        }
        case "bidi_response_start": {
          setChatStatus("streaming");
          break;
        }
        case "bidi_transcript_stream": {
          const role = event.role === "user" ? "user" : "assistant";
          const text = String(event.text ?? "");
          if (text) {
            if (event.thought) {
              upsertThoughtPart(text, "streaming");
            } else {
              appendText(role, text);
            }
          }
          if (role === "assistant") setChatStatus("streaming");
          break;
        }
        case "bidi_grounding_metadata": {
          const queries = (event.queries ?? []) as string[];
          const chunks = (event.chunks ?? []) as {
            type: "web" | "image" | "maps";
            title: string;
            uri: string;
            image_uri?: string;
            domain?: string;
          }[];
          
          setMessages((prev) => {
            const next = [...prev];
            let last = next.at(-1);
            if (!last || last.role !== "assistant") {
              last = {
                id: nanoid(),
                role: "assistant",
                parts: [],
                createdAt: Date.now(),
              };
              next.push(last);
            }
            const parts = [...last.parts];
            const index = parts.findIndex((existing) => existing.type === "search");
            if (index >= 0) {
              parts[index] = {
                type: "search",
                queries,
                chunks,
              };
            } else {
              parts.push({
                type: "search",
                queries,
                chunks,
              });
            }
            next[next.length - 1] = { ...last, parts };
            return next;
          });
          break;
        }
        case "bidi_audio_stream": {
          const audio = String(event.audio ?? "");
          const rate = Number(event.sample_rate ?? 24000);
          audioRateRef.current = rate;
          audioChunksRef.current.push(base64ToBytes(audio));
          playerRef.current?.play(audio, rate);
          break;
        }
        case "bidi_interruption": {
          playerRef.current?.flush();
          audioChunksRef.current = [];
          break;
        }
        case "tool_use_stream": {
          const toolUse = (event.current_tool_use ?? {}) as {
            toolUseId?: string;
            name?: string;
            input?: unknown;
          };
          if (!toolUse.toolUseId || !toolUse.name) break;
          // The agent drives the browser camera through this tool.
          if (toolUse.name === "control_camera") {
            const action = String(
              (toolUse.input as { action?: string } | undefined)?.action ?? ""
            ).toLowerCase();
            const key = `${toolUse.toolUseId}:${action}`;
            if (action && !handledCameraCallsRef.current.has(key)) {
              handledCameraCallsRef.current.add(key);
              const camera = cameraControlRef.current;
              if (action === "start") void camera?.start();
              if (action === "stop") camera?.stop();
              if (action === "snap") camera?.snap();
              if (action === "flip") void camera?.flip();
              if (action === "rear") void camera?.setFacing("environment");
              if (action === "front") void camera?.setFacing("user");
            }
          }
          // take_video: record camera + mic in the browser, upload, let the
          // blocking backend tool pick up the clip (with transcript).
          if (toolUse.name === "take_video") {
            const key = `${toolUse.toolUseId}:record`;
            if (!handledCameraCallsRef.current.has(key)) {
              handledCameraCallsRef.current.add(key);
              const input = (toolUse.input ?? {}) as { duration?: number; section?: string };
              void cameraControlRef.current?.record(
                Number(input.duration ?? 10),
                String(input.section ?? "")
              );
            }
          }
          upsertToolPart({
            type: `tool-${toolUse.name}`,
            toolCallId: toolUse.toolUseId,
            toolName: toolUse.name,
            state: "input-available",
            input: toolUse.input ?? {},
          });
          break;
        }
        case "tool_result": {
          const result = (event.tool_result ?? {}) as {
            toolUseId?: string;
            status?: string;
            content?: { text?: string; json?: unknown }[];
          };
          if (!result.toolUseId) break;
          const output = (result.content ?? [])
            .map((block) =>
              block.text ?? (block.json ? JSON.stringify(block.json, null, 2) : "")
            )
            .join("\n");
          const name = String(event.tool_name ?? "");
          upsertToolPart({
            type: `tool-${name || "unknown"}`,
            toolCallId: result.toolUseId,
            toolName: name || "unknown",
            state: result.status === "error" ? "output-error" : "output-available",
            input: (event.tool_input ?? {}) as unknown,
            output,
            errorText: result.status === "error" ? output : undefined,
          });
          refreshWorkspace();
          if (name === "load_tool") refreshAgentCard();
          break;
        }
        case "bidi_response_complete": {
          // Finalize thoughts
          setMessages((prev) => {
            const next = [...prev];
            const last = next.at(-1);
            if (last && last.role === "assistant") {
              const parts = last.parts.map((part) =>
                part.type === "thought" ? { ...part, state: "done" as const } : part
              );
              next[next.length - 1] = { ...last, parts };
              return next;
            }
            return prev;
          });
          finalizeAssistantTurn();
          setChatStatus("ready");
          drainQueue();
          break;
        }
        case "bidi_usage": {
          setUsage({
            inputTokens: Number(event.input_tokens ?? 0),
            outputTokens: Number(event.output_tokens ?? 0),
            totalTokens: Number(event.total_tokens ?? 0),
          });
          break;
        }
        case "bidi_error": {
          setError(String(event.error ?? "unknown error"));
          setChatStatus("error");
          break;
        }
        case "bidi_connection_close": {
          setStatus("disconnected");
          break;
        }
        default:
          break;
      }
    },
    [
      appendText,
      drainQueue,
      finalizeAssistantTurn,
      refreshAgentCard,
      refreshWorkspace,
      upsertToolPart,
      upsertThoughtPart,
    ]
  );

  const disconnect = useCallback(async () => {
    micRef.current?.stop();
    micRef.current = null;
    setMicActive(false);
    cameraRef.current?.stop();
    cameraRef.current = null;
    setCameraActive(false);
    setCameraStream(null);
    await playerRef.current?.close();
    playerRef.current = null;
    socketRef.current?.close();
    socketRef.current = null;
    setStatus("disconnected");
    setChatStatus("ready");
  }, []);

  const connect = useCallback(async () => {
    await disconnect();
    setError(null);
    setStatus("connecting");
    // Browsers cannot set WS headers, so mint a short-lived token over HTTP
    // (cookie-authenticated) and pass it as a query param.
    let wsToken: string;
    try {
      const res = await fetch("/api/auth/ws-token", {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        setError("Not authorized for a live session — please sign in again.");
        setStatus("disconnected");
        setChatStatus("error");
        return;
      }
      wsToken = ((await res.json()) as { token: string }).token;
    } catch {
      setError("WebSocket connection failed — is the backend running?");
      setStatus("disconnected");
      setChatStatus("error");
      return;
    }
    playerRef.current = new PcmPlayer(setSpeaking);
    const socket = new WebSocket(wsUrl(mode, voice, model, wsToken));
    socketRef.current = socket;
    socket.onmessage = (message) => {
      try {
        handleEvent(JSON.parse(message.data as string) as ServerEvent);
      } catch {
        // malformed frame; ignore
      }
    };
    socket.onclose = () => {
      setStatus("disconnected");
      setMicActive(false);
    };
    socket.onerror = () => {
      setError("WebSocket connection failed — is the backend running?");
      setStatus("disconnected");
      setChatStatus("error");
    };
  }, [disconnect, handleEvent, mode, voice, model]);

  const [pendingReconnect, setPendingReconnect] = useState(false);

  /** Switch vended provider. If a session is live, reconnects seamlessly. */
  const setModel = useCallback(
    (next: LiveModel["id"]) => {
      if (next === model) return;
      setModelState(next);
      const defaultVoice = models.find((entry) => entry.id === next)?.defaultVoice;
      if (defaultVoice) setVoiceState(defaultVoice);
      if (socketRef.current) setPendingReconnect(true);
    },
    [model, models]
  );

  /** Pick a voice for the current provider. If a session is live, reconnects with it. */
  const setVoice = useCallback(
    (next: string) => {
      if (next === voice) return;
      setVoiceState(next);
      if (socketRef.current) setPendingReconnect(true);
    },
    [voice]
  );

  useEffect(() => {
    if (!pendingReconnect) return;
    setPendingReconnect(false);
    void connect();
  }, [pendingReconnect, connect]);

  const startMic = useCallback(
    async (deviceId?: string) => {
      const capture = new MicCapture(MIC_SAMPLE_RATE, (chunk) => {
        sendRaw({
          type: "bidi_audio_input",
          audio: chunk,
          format: "pcm",
          sample_rate: MIC_SAMPLE_RATE,
          channels: 1,
        });
      });
      await capture.start(deviceId ?? micDeviceId);
      micRef.current = capture;
      setMicActive(true);
    },
    [micDeviceId, sendRaw]
  );

  const stopMic = useCallback(async () => {
    await micRef.current?.stop();
    micRef.current = null;
    setMicActive(false);
  }, []);

  /** Start the device camera (browser getUserMedia) and stream frames to the model. */
  // Non-selfie (rear/"environment") is the default so photos/videos frame the
  // property, not the inspector. Kept as a ref for synchronous reads inside
  // startCamera and mirrored to cameraFacing state for the UI.
  const cameraFacingRef = useRef<"environment" | "user">("environment");
  const startCamera = useCallback(
    async (deviceId?: string) => {
      cameraRef.current?.stop();
      const capture = new CameraCapture(
        (jpegBase64) => {
          lastFrameRef.current = jpegBase64;
          sendRaw({
            type: "bidi_image_input",
            image: jpegBase64,
            mime_type: "image/jpeg",
          });
        },
        2000,
        640,
        0.4
      );
      await capture.start(deviceId ?? cameraDeviceId, cameraFacingRef.current);
      cameraRef.current = capture;
      setCameraStream(capture.mediaStream);
      setCameraActive(true);
      // Reflect the facing the stream actually settled on (a picked deviceId
      // may resolve to either camera; read it back off the track when we can).
      const track = capture.mediaStream?.getVideoTracks()[0];
      const settledFacing = track?.getSettings?.().facingMode;
      if (settledFacing === "user" || settledFacing === "environment") {
        cameraFacingRef.current = settledFacing;
        setCameraFacingState(settledFacing);
      }
    },
    [cameraDeviceId, sendRaw]
  );

  const stopCamera = useCallback(() => {
    cameraRef.current?.stop();
    cameraRef.current = null;
    setCameraActive(false);
    setCameraStream(null);
  }, []);

  /** Pick a specific camera by deviceId (any webcam / built-in / USB / phone lens). */
  const selectCameraDevice = useCallback(
    async (deviceId: string) => {
      setCameraDeviceId(deviceId);
      if (cameraRef.current) {
        await startCamera(deviceId);
      }
    },
    [startCamera]
  );

  /** Send one full-quality frame right now (e.g. "take a photo of this"). */
  const snapPhoto = useCallback(() => {
    const frame = cameraRef.current?.snap();
    if (frame) {
      lastFrameRef.current = frame;
      sendRaw({ type: "bidi_image_input", image: frame, mime_type: "image/jpeg" });
      // Show the snap in the conversation thread (rendered by the Image element).
      setMessages((prev) => [
        ...prev,
        {
          id: nanoid(),
          role: "user",
          parts: [
            {
              type: "file",
              url: `data:image/jpeg;base64,${frame}`,
              mediaType: "image/jpeg",
              filename: "camera-snap.jpg",
            },
          ],
          createdAt: Date.now(),
        },
      ]);
    }
    return Boolean(frame);
  }, [sendRaw]);

  /** Switch between front (selfie/"user") and rear ("environment") cameras
   *  (agent "flip" or manual). Clears any explicit deviceId so the facing
   *  constraint drives selection. */
  const flipCamera = useCallback(async () => {
    const next = cameraFacingRef.current === "environment" ? "user" : "environment";
    cameraFacingRef.current = next;
    setCameraFacingState(next);
    setCameraDeviceId(undefined);
    if (cameraRef.current) {
      await startCamera(undefined);
    }
  }, [startCamera]);

  /** Set camera facing explicitly to "environment" (rear, non-selfie — default)
   *  or "user" (front/selfie). Restarts the stream when live. */
  const setCameraFacing = useCallback(
    async (facing: "environment" | "user") => {
      if (facing === cameraFacingRef.current && !cameraDeviceId) return;
      cameraFacingRef.current = facing;
      setCameraFacingState(facing);
      setCameraDeviceId(undefined);
      if (cameraRef.current) {
        await startCamera(undefined);
      }
    },
    [cameraDeviceId, startCamera]
  );

  /** Latest camera frame (base64 JPEG) — used to pin photos onto checklist items. */
  const getLatestFrame = useCallback(() => lastFrameRef.current, []);

  /** Record a walkthrough clip (video + mic audio) and upload it for the take_video tool. */
  const recordClip = useCallback(async (durationSec: number, section: string) => {
    const camera = cameraRef.current;
    if (!camera) return false;
    setRecording(true);
    try {
      const clamped = Math.max(2, Math.min(durationSec || 10, 120));
      // Reuse the live session mic track — a second getUserMedia while
      // MicCapture holds the mic records silence on iOS Safari/some Androids.
      const blob = await camera.record(clamped * 1000, micRef.current?.mediaStream);
      const query = `section=${encodeURIComponent(section)}&duration=${clamped}`;
      await fetch(`/api/inspection/video?${query}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": blob.type || "video/webm" },
        body: blob,
      });
      return true;
    } catch {
      return false;
    } finally {
      setRecording(false);
    }
  }, []);

  // Let the agent's control_camera tool drive the browser camera.
  useEffect(() => {
    cameraControlRef.current = {
      start: startCamera,
      stop: stopCamera,
      snap: snapPhoto,
      flip: flipCamera,
      setFacing: setCameraFacing,
      record: recordClip,
    };
  }, [startCamera, stopCamera, snapPhoto, flipCamera, setCameraFacing, recordClip]);

  const selectMicDevice = useCallback(
    async (deviceId: string) => {
      setMicDeviceId(deviceId);
      if (micActiveRef.current) {
        await startMic(deviceId);
      }
    },
    [startMic]
  );

  const submit = useCallback(
    (payload: SubmitPayload) => {
      if (!payload.text.trim() && payload.files.length === 0) return;
      deliver(payload);
    },
    [deliver]
  );

  const cancelQueued = useCallback((id: string) => {
    setQueue((prev) => prev.filter((entry) => entry.id !== id));
  }, []);

  const retryUserMessage = useCallback(
    (message: LiveMessage) => {
      const text = message.parts
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join("\n");
      if (text) submit({ text, files: [] });
    },
    [submit]
  );

  const personaState: PersonaState = useMemo(() => {
    if (status !== "connected") return "asleep";
    if (speaking) return "speaking";
    if (chatStatus === "submitted" || chatStatus === "streaming") return "thinking";
    if (micActive) return "listening";
    return "idle";
  }, [status, speaking, chatStatus, micActive]);

  useEffect(() => {
    void connect();
  }, [connect]);

  useEffect(() => () => void disconnect(), [disconnect]);

  return {
    // session
    status,
    chatStatus,
    error,
    mode,
    setMode,
    voice,
    setVoice,
    voices,
    model,
    setModel,
    models,
    connect,
    disconnect,
    // conversation
    messages,
    segments,
    usage,
    submit,
    retryUserMessage,
    // queue
    queue,
    cancelQueued,
    // audio
    micActive,
    micDeviceId,
    startMic,
    stopMic,
    selectMicDevice,
    speaking,
    personaState,
    // camera
    cameraActive,
    cameraDeviceId,
    cameraFacing,
    cameraStream,
    recording,
    startCamera,
    stopCamera,
    selectCameraDevice,
    setCameraFacing,
    snapPhoto,
    flipCamera,
    getLatestFrame,
    // agent metadata
    agentCard,
    workspaceFiles,
    refreshWorkspace,
  };
};

export type LiveAgent = ReturnType<typeof useLiveAgent>;
