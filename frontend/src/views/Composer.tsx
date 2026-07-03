import {
  ApertureIcon,
  MicIcon,
  MicOffIcon,
  VideoIcon,
  VideoOffIcon,
  WorkflowIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Attachment,
  AttachmentInfo,
  AttachmentHoverCard,
  AttachmentHoverCardContent,
  AttachmentHoverCardTrigger,
  AttachmentPreview,
  AttachmentRemove,
  Attachments,
} from "@/components/ai-elements/attachments";
import {
  MicSelector,
  MicSelectorContent,
  MicSelectorEmpty,
  MicSelectorInput,
  MicSelectorItem,
  MicSelectorLabel,
  MicSelectorList,
  MicSelectorTrigger,
  MicSelectorValue,
} from "@/components/ai-elements/mic-selector";
import {
  PromptInput,
  PromptInputActionAddAttachments,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  PromptInputButton,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputAttachments,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import {
  Queue,
  QueueItem,
  QueueItemAction,
  QueueItemActions,
  QueueItemContent,
  QueueItemIndicator,
  QueueList,
  QueueSection,
  QueueSectionContent,
  QueueSectionLabel,
  QueueSectionTrigger,
} from "@/components/ai-elements/queue";
import { SpeechInput } from "@/components/ai-elements/speech-input";
import type { LiveAgent } from "@/hooks/use-live-agent";

/** Floating live preview of the streaming device camera. */
const CameraPreview = ({ agent }: { agent: LiveAgent }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (videoRef.current && agent.cameraStream) {
      videoRef.current.srcObject = agent.cameraStream;
    }
  }, [agent.cameraStream]);

  if (!agent.cameraStream) return null;
  return (
    <div className="mx-auto mb-2 w-full max-w-3xl">
      <video
        autoPlay
        className="ml-auto h-28 rounded-md border object-cover"
        muted
        playsInline
        ref={videoRef}
      />
    </div>
  );
};

/** Camera device picker (videoinput analogue of MicSelector). */
const CameraDeviceSelect = ({ agent }: { agent: LiveAgent }) => {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);

  useEffect(() => {
    if (!agent.cameraActive) return;
    navigator.mediaDevices
      .enumerateDevices()
      .then((all) => setDevices(all.filter((d) => d.kind === "videoinput")))
      .catch(() => setDevices([]));
  }, [agent.cameraActive]);

  if (!agent.cameraActive || devices.length < 2) return null;
  return (
    <select
      aria-label="Select camera"
      className="h-8 max-w-40 truncate rounded-md bg-transparent text-muted-foreground text-xs outline-none"
      onChange={(event) => agent.selectCameraDevice(event.target.value)}
      value={agent.cameraDeviceId ?? ""}
    >
      {devices.map((device, index) => (
        <option key={device.deviceId} value={device.deviceId}>
          {device.label || `Camera ${index + 1}`}
        </option>
      ))}
    </select>
  );
};

const ComposerAttachments = () => {
  const attachments = usePromptInputAttachments();
  if (attachments.files.length === 0) return null;
  return (
    <Attachments variant="inline">
      {attachments.files.map((file) => (
        <AttachmentHoverCard key={file.id}>
          <AttachmentHoverCardTrigger asChild>
            <Attachment
              data={file}
              onRemove={() => attachments.remove(file.id)}
            >
              <AttachmentPreview />
              <AttachmentRemove />
            </Attachment>
          </AttachmentHoverCardTrigger>
          <AttachmentHoverCardContent>
            <AttachmentPreview className="size-40" />
            <AttachmentInfo />
          </AttachmentHoverCardContent>
        </AttachmentHoverCard>
      ))}
    </Attachments>
  );
};

const PromptQueue = ({ agent }: { agent: LiveAgent }) => {
  const pending = agent.queue.filter((entry) => entry.status === "pending");
  const completed = agent.queue.filter((entry) => entry.status === "completed");
  if (agent.queue.length === 0) return null;
  return (
    <Queue className="mx-auto mb-2 w-full max-w-3xl">
      <QueueSection defaultOpen>
        <QueueSectionTrigger>
          <QueueSectionLabel count={pending.length} label="Queued prompts" />
        </QueueSectionTrigger>
        <QueueSectionContent>
          <QueueList>
            {pending.map((entry) => (
              <QueueItem key={entry.id}>
                <QueueItemIndicator />
                <QueueItemContent>{entry.text}</QueueItemContent>
                <QueueItemActions>
                  <QueueItemAction
                    aria-label="Remove from queue"
                    onClick={() => agent.cancelQueued(entry.id)}
                  >
                    <XIcon className="size-3" />
                  </QueueItemAction>
                </QueueItemActions>
              </QueueItem>
            ))}
          </QueueList>
        </QueueSectionContent>
      </QueueSection>
      {completed.length > 0 && (
        <QueueSection>
          <QueueSectionTrigger>
            <QueueSectionLabel count={completed.length} label="Sent" />
          </QueueSectionTrigger>
          <QueueSectionContent>
            <QueueList>
              {completed.map((entry) => (
                <QueueItem key={entry.id}>
                  <QueueItemIndicator completed />
                  <QueueItemContent completed>{entry.text}</QueueItemContent>
                </QueueItem>
              ))}
            </QueueList>
          </QueueSectionContent>
        </QueueSection>
      )}
    </Queue>
  );
};

export const Composer = ({
  agent,
  workflowOpen,
  onToggleWorkflow,
}: {
  agent: LiveAgent;
  workflowOpen: boolean;
  onToggleWorkflow: () => void;
}) => {
  const [text, setText] = useState("");

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      agent.submit({
        text: message.text,
        files: message.files.map((file) => ({
          url: file.url,
          mediaType: file.mediaType ?? "application/octet-stream",
          filename: file.filename,
        })),
      });
      setText("");
    },
    [agent]
  );

  const toggleMic = useCallback(() => {
    if (agent.micActive) {
      agent.stopMic();
    } else {
      agent.startMic();
    }
  }, [agent]);

  const toggleCamera = useCallback(() => {
    if (agent.cameraActive) {
      agent.stopCamera();
    } else {
      agent.startCamera();
    }
  }, [agent]);

  return (
    <div className="border-t bg-background/95 px-4 pt-2 pb-4 backdrop-blur">
      <CameraPreview agent={agent} />
      <PromptQueue agent={agent} />
      <PromptInput
        accept="image/*"
        className="mx-auto w-full max-w-3xl"
        globalDrop
        multiple
        onSubmit={handleSubmit}
      >
        <PromptInputHeader>
          <ComposerAttachments />
        </PromptInputHeader>
        <PromptInputBody>
          <PromptInputTextarea
            onChange={(event) => setText(event.target.value)}
            placeholder={
              agent.status === "connected"
                ? "Message the live agent… (drop images anywhere)"
                : "Connect first, then message the live agent…"
            }
            value={text}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputTools>
            <PromptInputActionMenu>
              <PromptInputActionMenuTrigger />
              <PromptInputActionMenuContent>
                <PromptInputActionAddAttachments label="Attach images" />
              </PromptInputActionMenuContent>
            </PromptInputActionMenu>
            <SpeechInput
              className="shrink-0"
              onTranscriptionChange={setText}
              size="icon-sm"
              variant="ghost"
            />
            <PromptInputButton
              disabled={agent.status !== "connected"}
              onClick={toggleMic}
              variant={agent.micActive ? "default" : "ghost"}
            >
              {agent.micActive ? (
                <MicOffIcon className="size-4" />
              ) : (
                <MicIcon className="size-4" />
              )}
              <span>{agent.micActive ? "Mute" : "Mic"}</span>
            </PromptInputButton>
            <PromptInputButton
              disabled={agent.status !== "connected"}
              onClick={toggleCamera}
              variant={agent.cameraActive ? "default" : "ghost"}
            >
              {agent.cameraActive ? (
                <VideoOffIcon className="size-4" />
              ) : (
                <VideoIcon className="size-4" />
              )}
              <span>{agent.cameraActive ? "Stop cam" : "Camera"}</span>
            </PromptInputButton>
            {agent.cameraActive && (
              <PromptInputButton onClick={() => agent.snapPhoto()} variant="ghost">
                <ApertureIcon className="size-4" />
                <span>Snap</span>
              </PromptInputButton>
            )}
            <CameraDeviceSelect agent={agent} />
            <MicSelector
              onValueChange={(deviceId) =>
                deviceId && agent.selectMicDevice(deviceId)
              }
              value={agent.micDeviceId}
            >
              <MicSelectorTrigger
                className="h-8 max-w-48 border-none text-muted-foreground"
                size="sm"
                variant="ghost"
              >
                <MicSelectorValue className="truncate text-xs" />
              </MicSelectorTrigger>
              <MicSelectorContent>
                <MicSelectorInput placeholder="Search microphones…" />
                <MicSelectorList>
                  {(devices) => (
                    <>
                      <MicSelectorEmpty>No microphones found.</MicSelectorEmpty>
                      {devices.map((device) => (
                        <MicSelectorItem
                          key={device.deviceId}
                          value={device.deviceId}
                        >
                          <MicSelectorLabel device={device} />
                        </MicSelectorItem>
                      ))}
                    </>
                  )}
                </MicSelectorList>
              </MicSelectorContent>
            </MicSelector>
            <PromptInputButton
              onClick={onToggleWorkflow}
              variant={workflowOpen ? "default" : "ghost"}
            >
              <WorkflowIcon className="size-4" />
              <span>Workflow</span>
            </PromptInputButton>
          </PromptInputTools>
          <PromptInputSubmit
            disabled={agent.status !== "connected" && !text.trim()}
            status={agent.chatStatus === "ready" ? undefined : agent.chatStatus}
          />
        </PromptInputFooter>
      </PromptInput>
    </div>
  );
};
