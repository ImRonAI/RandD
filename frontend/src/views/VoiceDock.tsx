import {
  AudioLinesIcon,
  BrainCircuitIcon,
  CameraIcon,
  CameraOffIcon,
  PhoneIcon,
  PhoneOffIcon,
  SwitchCameraIcon,
  VideoIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  CameraSelector,
  CameraSelectorContent,
  CameraSelectorEmpty,
  CameraSelectorInput,
  CameraSelectorItem,
  CameraSelectorList,
  CameraSelectorTrigger,
  cameraLabel,
} from "@/components/ai-elements/camera-selector";
import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorDescription,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorInput,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorModelId,
  ModelSelectorName,
  ModelSelectorTrigger,
  ModelSelectorVendor,
} from "@/components/ai-elements/model-selector";
import {
  Transcription,
  TranscriptionSegment,
} from "@/components/ai-elements/transcription";
import {
  VoiceSelector,
  VoiceSelectorAccent,
  VoiceSelectorAge,
  VoiceSelectorAttributes,
  VoiceSelectorBullet,
  VoiceSelectorContent,
  VoiceSelectorDescription,
  VoiceSelectorEmpty,
  VoiceSelectorGender,
  VoiceSelectorGroup,
  VoiceSelectorInput,
  VoiceSelectorItem,
  VoiceSelectorList,
  VoiceSelectorName,
  VoiceSelectorTrigger,
} from "@/components/ai-elements/voice-selector";
import { Button } from "@/components/ui/button";
import type { LiveAgent } from "@/hooks/use-live-agent";
import type { LiveModel } from "@/lib/live-types";
import { cn } from "@/lib/utils";

/**
 * Lightweight CSS status orb. Replaces the AI Elements Rive `Persona`,
 * whose WebGL2/WASM init hard-locks the main thread in this environment
 * (remote .riv blob + webgl2 context), freezing the whole app.
 */
const StatusOrb = ({ state }: { state: string }) => {
  const isAnimating = state === "listening" || state === "speaking" || state === "thinking";
  return (
    <div className="liquid-orb-container" role="img" aria-label={`agent ${state}`}>
      <div className={cn("liquid-orb-ripple", isAnimating && "active")} />
      <div className={cn("liquid-orb-ripple active-delay", isAnimating && "active")} />
      <div className="liquid-orb" data-state={state} />
    </div>
  );
};

/**
 * Camera controls: live preview, on/off, a front(selfie)/rear(non-selfie)
 * toggle, and a full camera picker. Works on any device — laptop/desktop
 * webcams, tablet/phone front & rear lenses, USB and continuity cameras.
 * Rear ("environment") is the default so photos/videos frame the property.
 */
const CameraControls = ({ agent }: { agent: LiveAgent }) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.srcObject = agent.cameraStream;
    if (agent.cameraStream) {
      void video.play().catch(() => {
        // autoplay can be rejected until a user gesture; preview resumes on next start
      });
    }
  }, [agent.cameraStream]);

  const facing = agent.cameraFacing;

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-background/50 p-3">
      <div className="flex items-center justify-between">
        <p className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
          Camera
        </p>
        {agent.cameraActive && (
          <span className="text-[10px] text-muted-foreground">
            {facing === "user" ? "Front · selfie" : "Rear · environment"}
            {agent.recording && " · recording"}
          </span>
        )}
      </div>

      {/* Live preview (mirrored only for the selfie/front camera) */}
      <div className="relative aspect-video w-full overflow-hidden rounded-md bg-muted">
        {agent.cameraActive ? (
          <video
            className={cn(
              "h-full w-full object-cover",
              facing === "user" && "-scale-x-100"
            )}
            muted
            playsInline
            ref={videoRef}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <CameraOffIcon className="size-6" />
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        {agent.cameraActive ? (
          <Button
            className="flex-1"
            onClick={() => agent.stopCamera()}
            size="sm"
            variant="secondary"
          >
            <CameraOffIcon className="size-4" />
            Turn off
          </Button>
        ) : (
          <Button
            className="flex-1"
            onClick={() => void agent.startCamera()}
            size="sm"
          >
            <CameraIcon className="size-4" />
            Turn on
          </Button>
        )}
        <Button
          aria-label="Flip camera"
          disabled={!agent.cameraActive}
          onClick={() => void agent.flipCamera()}
          size="sm"
          title="Switch front / rear camera"
          variant="outline"
        >
          <SwitchCameraIcon className="size-4" />
        </Button>
        <Button
          aria-label="Take a photo"
          disabled={!agent.cameraActive}
          onClick={() => agent.snapPhoto()}
          size="sm"
          title="Capture a photo now"
          variant="outline"
        >
          <VideoIcon className="size-4" />
        </Button>
      </div>

      {/* Front / rear (selfie / non-selfie) segmented toggle */}
      <div className="grid grid-cols-2 gap-1 rounded-md bg-muted p-1">
        <Button
          className="h-7"
          onClick={() => void agent.setCameraFacing("environment")}
          size="sm"
          variant={facing === "environment" ? "secondary" : "ghost"}
        >
          Rear
        </Button>
        <Button
          className="h-7"
          onClick={() => void agent.setCameraFacing("user")}
          size="sm"
          variant={facing === "user" ? "secondary" : "ghost"}
        >
          Front (selfie)
        </Button>
      </div>

      {/* Exact camera picker — any lens/webcam on the device */}
      <CameraSelector
        onValueChange={(value) => value && void agent.selectCameraDevice(value)}
        value={agent.cameraDeviceId}
      >
        <CameraSelectorTrigger className="w-full justify-start" size="sm">
          <CameraIcon className="size-4" />
          <span className="truncate">Choose camera…</span>
        </CameraSelectorTrigger>
        <CameraSelectorContent title="Choose a camera">
          <CameraSelectorInput />
          <CameraSelectorList>
            {(devices) => (
              <>
                <CameraSelectorEmpty />
                {devices.map((device, index) => (
                  <CameraSelectorItem key={device.deviceId} value={device.deviceId}>
                    <CameraIcon className="size-4 shrink-0 text-muted-foreground" />
                    <span className="truncate">{cameraLabel(device, index)}</span>
                  </CameraSelectorItem>
                ))}
              </>
            )}
          </CameraSelectorList>
        </CameraSelectorContent>
      </CameraSelector>
    </div>
  );
};

/**
 * Voice + camera dock: live status orb, session controls, voice picker, camera
 * controls, rolling transcript. On desktop it's a fixed right sidebar; on
 * mobile it becomes a slide-in overlay panel toggled from the header so the
 * main content (checklist / chat) keeps the full narrow screen.
 */
export const VoiceDock = ({
  agent,
  open = false,
  onClose,
}: {
  agent: LiveAgent;
  open?: boolean;
  onClose?: () => void;
}) => {
  const [transcriptTime, setTranscriptTime] = useState(0);

  const body = (
    <>
      <div className="flex flex-col items-center gap-2">
        <StatusOrb state={agent.personaState} />
        <p className="font-medium text-sm">{agent.agentCard?.name ?? "RandD Live"}</p>
        <p className="text-muted-foreground text-xs capitalize">
          {agent.personaState}
          {agent.status === "connected" && ` · ${agent.voice}`}
        </p>
      </div>

      <div className="flex items-center justify-center gap-2">
        {agent.status === "connected" ? (
          <Button onClick={() => agent.disconnect()} variant="destructive">
            <PhoneOffIcon className="size-4" />
            End session
          </Button>
        ) : (
          <Button
            disabled={agent.status === "connecting"}
            onClick={() => agent.connect()}
          >
            <PhoneIcon className="size-4" />
            {agent.status === "connecting" ? "Connecting…" : "Connect"}
          </Button>
        )}
      </div>

      <ModelSelector
        onValueChange={(value) => value && agent.setModel(value as LiveModel["id"])}
        value={agent.model}
      >
        <ModelSelectorTrigger asChild>
          <Button className="w-full justify-start" variant="outline">
            <BrainCircuitIcon className="size-4" />
            Model:{" "}
            {agent.models.find((entry) => entry.id === agent.model)?.name ??
              agent.model}
          </Button>
        </ModelSelectorTrigger>
        <ModelSelectorContent title="Choose a realtime model">
          <ModelSelectorInput placeholder="Search models…" />
          <ModelSelectorList>
            <ModelSelectorEmpty>No models found.</ModelSelectorEmpty>
            <ModelSelectorGroup heading="Realtime voice models">
              {agent.models.map((entry) => (
                <ModelSelectorItem key={entry.id} value={entry.id}>
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <ModelSelectorName>{entry.name}</ModelSelectorName>
                      <ModelSelectorVendor>{entry.vendor}</ModelSelectorVendor>
                    </div>
                    <ModelSelectorDescription>
                      {entry.description}
                    </ModelSelectorDescription>
                    <ModelSelectorModelId>{entry.modelId}</ModelSelectorModelId>
                  </div>
                </ModelSelectorItem>
              ))}
            </ModelSelectorGroup>
          </ModelSelectorList>
        </ModelSelectorContent>
      </ModelSelector>

      <VoiceSelector onValueChange={(value) => value && agent.setVoice(value)} value={agent.voice}>
        <VoiceSelectorTrigger asChild>
          <Button className="w-full justify-start" variant="outline">
            <AudioLinesIcon className="size-4" />
            Voice: {agent.voice}
          </Button>
        </VoiceSelectorTrigger>
        <VoiceSelectorContent title="Choose a voice">
          <VoiceSelectorInput placeholder="Search voices…" />
          <VoiceSelectorList>
            <VoiceSelectorEmpty>No voices found.</VoiceSelectorEmpty>
            <VoiceSelectorGroup
              heading={`${
                agent.models.find((entry) => entry.id === agent.model)?.name ?? agent.model
              } voices`}
            >
              {agent.voices.map((voice) => (
                <VoiceSelectorItem key={voice.id} value={voice.id}>
                  <div className="flex flex-col gap-1">
                    <VoiceSelectorName>{voice.name}</VoiceSelectorName>
                    <VoiceSelectorDescription>
                      {voice.description}
                    </VoiceSelectorDescription>
                    <VoiceSelectorAttributes>
                      <VoiceSelectorGender value={voice.gender === "neutral" ? undefined : voice.gender} />
                      <VoiceSelectorBullet />
                      <VoiceSelectorAccent value={voice.accent.toLowerCase() as "american"} />
                      <VoiceSelectorBullet />
                      <VoiceSelectorAge>{voice.age}</VoiceSelectorAge>
                    </VoiceSelectorAttributes>
                  </div>
                </VoiceSelectorItem>
              ))}
            </VoiceSelectorGroup>
          </VoiceSelectorList>
        </VoiceSelectorContent>
      </VoiceSelector>
      {agent.status === "connected" && (
        <p className="text-center text-muted-foreground text-xs">
          Changing voice reconnects the live session.
        </p>
      )}

      <CameraControls agent={agent} />

      <div className="min-h-0 flex-1">
        <p className="mb-2 font-medium text-muted-foreground text-xs uppercase tracking-wide">
          Live transcript
        </p>
        {agent.segments.length === 0 ? (
          <p className="text-muted-foreground text-xs">
            Transcript segments appear here as you and the agent speak.
          </p>
        ) : (
          <Transcription
            currentTime={transcriptTime}
            onSeek={setTranscriptTime}
            segments={agent.segments.map((segment) => ({
              text: segment.text,
              startSecond: segment.startSecond,
              endSecond: segment.endSecond,
            }))}
          >
            {(segment, index) => (
              <TranscriptionSegment
                className={
                  agent.segments[index]?.role === "user"
                    ? "font-medium"
                    : undefined
                }
                index={index}
                key={index}
                segment={segment}
              />
            )}
          </Transcription>
        )}
      </div>
    </>
  );

  return (
    <>
      {/* Desktop: fixed right sidebar, always visible at md and up. */}
      <aside className="hidden w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l bg-sidebar p-4 md:flex">
        {body}
      </aside>

      {/* Mobile: slide-in overlay toggled from the header (md:hidden). */}
      {open && (
        <div className="md:hidden">
          <button
            aria-label="Close voice and camera panel"
            className="fixed inset-0 z-40 bg-black/40"
            onClick={onClose}
            type="button"
          />
          <aside className="fixed inset-y-0 right-0 z-50 flex w-[86vw] max-w-sm flex-col gap-4 overflow-y-auto border-l bg-sidebar p-4 shadow-xl">
            <div className="flex items-center justify-between">
              <p className="font-medium text-sm">Voice &amp; Camera</p>
              <Button aria-label="Close" onClick={onClose} size="icon" variant="ghost">
                <XIcon className="size-4" />
              </Button>
            </div>
            {body}
          </aside>
        </div>
      )}
    </>
  );
};
