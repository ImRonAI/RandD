import {
  CheckCircleIcon,
  CopyIcon,
  FileCodeIcon,
  RefreshCcwIcon,
  TerminalIcon,
  WrenchIcon,
  Brain as BrainIcon,
  Search as SearchIcon,
} from "lucide-react";
import { Fragment, useCallback, useState, useEffect } from "react";
import type { UIMessage } from "ai";
import {
  AudioPlayer,
  AudioPlayerControlBar,
  AudioPlayerDurationDisplay,
  AudioPlayerElement,
  AudioPlayerMuteButton,
  AudioPlayerPlayButton,
  AudioPlayerSeekBackwardButton,
  AudioPlayerSeekForwardButton,
  AudioPlayerTimeDisplay,
  AudioPlayerTimeRange,
  AudioPlayerVolumeRange,
} from "@/components/ai-elements/audio-player";
import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtSearchResult,
  ChainOfThoughtSearchResults,
  ChainOfThoughtStep,
  ChainOfThoughtImage,
} from "@/components/ai-elements/chain-of-thought";
import { CodeBlock, CodeBlockCopyButton } from "@/components/ai-elements/code-block";
import {
  Conversation,
  ConversationContent,
  ConversationDownload,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Image } from "@/components/ai-elements/image";
import {
  JSXPreview,
  JSXPreviewContent,
  JSXPreviewError,
} from "@/components/ai-elements/jsx-preview";
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  Plan,
  PlanContent,
  PlanDescription,
  PlanHeader,
  PlanTitle,
  PlanTrigger,
} from "@/components/ai-elements/plan";
import {
  Sandbox,
  SandboxContent,
  SandboxHeader,
  SandboxTabContent,
  SandboxTabs,
  SandboxTabsBar,
  SandboxTabsList,
  SandboxTabsTrigger,
} from "@/components/ai-elements/sandbox";
import {
  Task,
  TaskContent,
  TaskItem,
  TaskItemFile,
  TaskTrigger,
} from "@/components/ai-elements/task";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import type { LiveAgent } from "@/hooks/use-live-agent";
import type { LiveMessage, LiveToolPart, LiveThoughtPart, LiveSearchPart } from "@/lib/live-types";
import { segmentText } from "@/lib/parse-blocks";

const messageText = (message: LiveMessage): string =>
  message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n");

/** Filenames touched by editor/shell tool input (real tool args). */
const touchedFiles = (part: LiveToolPart): string[] => {
  const input = part.input as Record<string, unknown> | undefined;
  const path = input?.path ?? input?.file_path ?? input?.file_text_path;
  return typeof path === "string" ? [path] : [];
};

const ShellSandbox = ({ part }: { part: LiveToolPart }) => {
  const input = part.input as Record<string, unknown> | undefined;
  const command =
    typeof input?.command === "string"
      ? input.command
      : JSON.stringify(input ?? {}, null, 2);
  return (
    <Sandbox>
      <SandboxHeader state={part.state} title="shell" />
      <SandboxContent>
        <SandboxTabs defaultValue="command">
          <SandboxTabsBar>
            <SandboxTabsList>
              <SandboxTabsTrigger value="command">Command</SandboxTabsTrigger>
              <SandboxTabsTrigger value="output">Output</SandboxTabsTrigger>
            </SandboxTabsList>
          </SandboxTabsBar>
          <SandboxTabContent value="command">
            <CodeBlock code={command} language="bash">
              <CodeBlockCopyButton />
            </CodeBlock>
          </SandboxTabContent>
          <SandboxTabContent value="output">
            <CodeBlock
              code={String(part.output ?? part.errorText ?? "(running…)")}
              language="console"
            >
              <CodeBlockCopyButton />
            </CodeBlock>
          </SandboxTabContent>
        </SandboxTabs>
      </SandboxContent>
    </Sandbox>
  );
};

const ToolPartView = ({ part }: { part: LiveToolPart }) => {
  if (part.toolName === "shell") return <ShellSandbox part={part} />;
  return (
    <Tool>
      <ToolHeader
        state={part.state}
        toolName={part.toolName}
        type="dynamic-tool"
      />
      <ToolContent>
        <ToolInput input={part.input} />
        {(part.output !== undefined || part.errorText) && (
          <ToolOutput
            errorText={part.errorText}
            output={
              typeof part.output === "string" ? (
                <MessageResponse>{part.output}</MessageResponse>
              ) : (
                <CodeBlock
                  code={JSON.stringify(part.output, null, 2)}
                  language="json"
                />
              )
            }
          />
        )}
      </ToolContent>
    </Tool>
  );
};

const AssistantTextPart = ({
  text,
  streaming,
}: {
  text: string;
  streaming: boolean;
}) => (
  <>
    {segmentText(text, streaming).map((segment, index) => {
      if (segment.kind === "markdown") {
        return segment.content.trim() ? (
          <MessageResponse key={index}>{segment.content}</MessageResponse>
        ) : null;
      }
      if (segment.kind === "jsx") {
        return (
          <JSXPreview
            isStreaming={segment.streaming}
            jsx={segment.content}
            key={index}
          >
            <JSXPreviewContent className="rounded-lg border bg-card p-4" />
            <JSXPreviewError />
          </JSXPreview>
        );
      }
      return (
        <Plan defaultOpen isStreaming={segment.streaming} key={index}>
          <PlanHeader>
            <div>
              <PlanTitle>{segment.plan?.title ?? "Plan"}</PlanTitle>
              {segment.plan?.description && (
                <PlanDescription>{segment.plan.description}</PlanDescription>
              )}
            </div>
            <PlanTrigger />
          </PlanHeader>
          <PlanContent>
            {(segment.plan?.steps ?? []).map((step, stepIndex) => (
              <ChainOfThoughtStep
                key={stepIndex}
                label={step.title}
                status={step.status ?? "pending"}
              />
            ))}
            {!segment.plan && (
              <MessageResponse>{`\`\`\`json\n${segment.raw}\n\`\`\``}</MessageResponse>
            )}
          </PlanContent>
        </Plan>
      );
    })}
  </>
);

const AssistantChainOfThought = ({ message }: { message: LiveMessage }) => {
  const toolParts = message.parts.filter((part): part is LiveToolPart =>
    part.type.startsWith("tool-")
  );
  const thoughtPart = message.parts.find((part): part is LiveThoughtPart =>
    part.type === "thought"
  );
  const searchPart = message.parts.find((part): part is LiveSearchPart =>
    part.type === "search"
  );

  if (toolParts.length === 0 && !thoughtPart && !searchPart) return null;
  const files = toolParts.flatMap(touchedFiles);
  const active = toolParts.some(
    (part) => part.state === "input-streaming" || part.state === "input-available"
  ) || (thoughtPart?.state === "streaming");

  const [isOpen, setIsOpen] = useState(active);
  useEffect(() => {
    if (active) {
      setIsOpen(true);
    }
  }, [active]);

  return (
    <ChainOfThought open={isOpen} onOpenChange={setIsOpen}>
      <ChainOfThoughtHeader>
        {active ? "Working…" : "Chain of thought"}
      </ChainOfThoughtHeader>
      <ChainOfThoughtContent>
        {thoughtPart && (
          <ChainOfThoughtStep
            icon={BrainIcon}
            label="thinking"
            status={thoughtPart.state === "done" ? "complete" : "active"}
          >
            {thoughtPart.text && (
              <div className="max-w-2xl bg-muted/40 p-2.5 rounded-md border border-border/50 text-xs">
                <MessageResponse isAnimating={thoughtPart.state === "streaming"}>
                  {thoughtPart.text}
                </MessageResponse>
              </div>
            )}
          </ChainOfThoughtStep>
        )}

        {searchPart && (searchPart.queries.length > 0 || searchPart.chunks.length > 0) && (
          <ChainOfThoughtStep
            icon={SearchIcon}
            label="google search"
            status="complete"
          >
            {searchPart.queries.length > 0 && (
              <div className="text-xs text-muted-foreground mb-1">
                Searched: {searchPart.queries.join(", ")}
              </div>
            )}
            
            {searchPart.chunks.some(c => c.type === "web") && (
              <ChainOfThoughtSearchResults className="mt-1">
                {searchPart.chunks
                  .filter(c => c.type === "web")
                  .map((chunk) => (
                    <ChainOfThoughtSearchResult key={chunk.uri}>
                      <a
                        href={chunk.uri}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline flex items-center gap-1"
                      >
                        {chunk.domain && <span className="opacity-70">[{chunk.domain}]</span>}
                        {chunk.title}
                      </a>
                    </ChainOfThoughtSearchResult>
                  ))}
              </ChainOfThoughtSearchResults>
            )}

            {searchPart.chunks
              .filter(c => c.type === "image" && c.image_uri)
              .map((chunk) => (
                <ChainOfThoughtImage key={chunk.uri} caption={chunk.title}>
                  <a href={chunk.uri} target="_blank" rel="noopener noreferrer">
                    <img
                      src={chunk.image_uri}
                      alt={chunk.title}
                      className="max-h-72 object-contain rounded-md"
                    />
                  </a>
                </ChainOfThoughtImage>
              ))}
          </ChainOfThoughtStep>
        )}

        {toolParts.map((part) => {
          const isSearchMemory = part.toolName === "search_memory";
          let memoryResults: any[] = [];
          if (isSearchMemory && part.output) {
            if (Array.isArray(part.output)) {
              memoryResults = part.output;
            } else if (typeof part.output === "string") {
              try {
                memoryResults = JSON.parse(part.output);
              } catch {}
            }
          }

          return (
            <ChainOfThoughtStep
              icon={
                isSearchMemory
                  ? SearchIcon
                  : part.toolName === "shell"
                    ? TerminalIcon
                    : part.toolName === "editor"
                      ? FileCodeIcon
                      : WrenchIcon
              }
              key={part.toolCallId}
              label={part.toolName}
              status={
                part.state === "output-available" || part.state === "output-error"
                  ? "complete"
                  : "active"
              }
            >
              {touchedFiles(part).length > 0 && (
                <ChainOfThoughtSearchResults className="mb-2">
                  {touchedFiles(part).map((file) => (
                    <ChainOfThoughtSearchResult key={file}>
                      {file}
                    </ChainOfThoughtSearchResult>
                  ))}
                </ChainOfThoughtSearchResults>
              )}

              {isSearchMemory && !!part.input && (
                <div className="text-xs text-muted-foreground mb-2">
                  Query: {typeof part.input === "string" ? part.input : (part.input as any)?.query ?? JSON.stringify(part.input)}
                </div>
              )}

              {isSearchMemory && memoryResults.length > 0 && (
                <ChainOfThoughtSearchResults className="mt-1 mb-2">
                  {memoryResults.map((res: any, idx: number) => {
                    const title = res.metadata?._document_title || `Result ${idx + 1}`;
                    const uri = res.metadata?._source_uri || res.metadata?._source_location?.s3Location?.uri;
                    return (
                      <ChainOfThoughtSearchResult key={idx}>
                        {uri ? (
                          <a
                            href={uri}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:underline flex items-center gap-1"
                          >
                            <span className="opacity-70">[{res.store_name || "memory"}]</span>
                            {title}
                          </a>
                        ) : (
                          <span>[{res.store_name || "memory"}] {title}</span>
                        )}
                      </ChainOfThoughtSearchResult>
                    );
                  })}
                </ChainOfThoughtSearchResults>
              )}

              {isSearchMemory && memoryResults.length > 0 && (
                <div className="space-y-1.5 mt-2">
                  {memoryResults.map((res: any, idx: number) => (
                    <div key={idx} className="text-xs text-muted-foreground/80 bg-muted/20 p-2.5 rounded border border-border/30">
                      <div className="font-semibold text-[10px] text-muted-foreground/60 uppercase mb-1">
                        Snippet {idx + 1} ({res.metadata?._relevance_score ? `score: ${res.metadata._relevance_score.toFixed(3)}` : "relevance match"})
                      </div>
                      <MessageResponse>
                        {res.content}
                      </MessageResponse>
                    </div>
                  ))}
                </div>
              )}

              {!isSearchMemory && !!part.input && (
                <div className="text-xs text-muted-foreground/80 mt-1 font-mono bg-muted/30 p-2 rounded border border-border/40 max-w-full overflow-x-auto">
                  <span className="text-muted-foreground/60 select-none">$ </span>
                  {typeof part.input === "string"
                    ? part.input
                    : (part.input as any)?.command
                      ? (part.input as any).command
                      : JSON.stringify(part.input, null, 2)}
                </div>
              )}

              {part.errorText && (
                <div className="text-xs text-destructive mt-1 font-mono bg-destructive/10 p-2 rounded border border-destructive/20">
                  {part.errorText}
                </div>
              )}

              {!isSearchMemory && part.output !== undefined && (
                <div className="mt-1 bg-muted/20 p-2 rounded border border-border/30 text-xs">
                  {typeof part.output === "string" ? (
                    <MessageResponse isAnimating={part.state === "input-streaming"}>
                      {part.output}
                    </MessageResponse>
                  ) : (
                    <pre className="text-xs text-muted-foreground/80 font-mono overflow-x-auto">
                      {JSON.stringify(part.output, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </ChainOfThoughtStep>
          );
        })}
        {files.length > 0 && (
          <Task defaultOpen={false}>
            <TaskTrigger
              title={`Touched ${files.length} file${files.length > 1 ? "s" : ""}`}
            />
            <TaskContent>
              {files.map((file) => (
                <TaskItem key={file}>
                  Modified <TaskItemFile>{file}</TaskItemFile>
                </TaskItem>
              ))}
            </TaskContent>
          </Task>
        )}
      </ChainOfThoughtContent>
    </ChainOfThought>
  );
};

const TurnAudio = ({ url }: { url: string }) => (
  <AudioPlayer className="mt-2 w-full max-w-md rounded-lg border bg-card px-2 py-1">
    <AudioPlayerElement src={url} />
    <AudioPlayerControlBar>
      <AudioPlayerPlayButton />
      <AudioPlayerSeekBackwardButton seekOffset={5} />
      <AudioPlayerSeekForwardButton seekOffset={5} />
      <AudioPlayerTimeDisplay />
      <AudioPlayerTimeRange />
      <AudioPlayerDurationDisplay />
      <AudioPlayerMuteButton />
      <AudioPlayerVolumeRange />
    </AudioPlayerControlBar>
  </AudioPlayer>
);

export const ChatThread = ({ agent }: { agent: LiveAgent }) => {
  const copyMessage = useCallback((message: LiveMessage) => {
    navigator.clipboard?.writeText(messageText(message));
  }, []);

  const downloadable = agent.messages.map((message) => ({
    id: message.id,
    role: message.role,
    parts: message.parts
      .filter((part) => part.type === "text")
      .map((part) => ({ type: "text" as const, text: part.text })),
  })) as UIMessage[];

  return (
    <Conversation className="relative flex-1">
      <ConversationContent className="mx-auto w-full max-w-3xl">
        {agent.messages.length === 0 && (
          <ConversationEmptyState
            description={
              agent.status === "connected"
                ? "Say something or type below — the Gemini Live agent is listening."
                : "Connect to start a live text or voice session with the meta-tooling agent."
            }
            icon={<CheckCircleIcon className="size-8" />}
            title="Vantage AI"
          />
        )}
        {agent.messages.map((message) => (
          <Message from={message.role} key={message.id}>
            <MessageContent>
              {message.role === "assistant" && (
                <AssistantChainOfThought message={message} />
              )}
              {message.parts.map((part, index) => {
                if (part.type === "text") {
                  return message.role === "assistant" ? (
                    <AssistantTextPart
                      key={index}
                      streaming={part.state === "streaming"}
                      text={part.text}
                    />
                  ) : (
                    <Fragment key={index}>{part.text}</Fragment>
                  );
                }
                if (part.type === "file") {
                  if (part.mediaType.startsWith("image/")) {
                    const base64 = part.url.split(",")[1] ?? "";
                    return (
                      <Image
                        alt={part.filename ?? "attachment"}
                        base64={base64}
                        className="max-w-xs rounded-lg border"
                        key={index}
                        mediaType={part.mediaType}
                        uint8Array={new Uint8Array()}
                      />
                    );
                  }
                  return (
                    <a href={part.url} key={index} rel="noreferrer" target="_blank">
                      {part.filename ?? part.url}
                    </a>
                  );
                }
                if (part.type.startsWith("tool-")) {
                  const toolPart = part as LiveToolPart;
                  if (toolPart.toolName === "search_memory") {
                    return null;
                  }
                  return <ToolPartView key={index} part={toolPart} />;
                }
                return null;
              })}
              {message.audioUrl && <TurnAudio url={message.audioUrl} />}
              <MessageActions>
                <MessageAction
                  label="Copy"
                  onClick={() => copyMessage(message)}
                  tooltip="Copy message"
                >
                  <CopyIcon className="size-3.5" />
                </MessageAction>
                {message.role === "user" && (
                  <MessageAction
                    label="Retry"
                    onClick={() => agent.retryUserMessage(message)}
                    tooltip="Send again"
                  >
                    <RefreshCcwIcon className="size-3.5" />
                  </MessageAction>
                )}
              </MessageActions>
            </MessageContent>
          </Message>
        ))}
      </ConversationContent>
      <ConversationScrollButton />
      {agent.messages.length > 0 && (
        <ConversationDownload
          filename="randd-live-session.md"
          messages={downloadable}
        />
      )}
    </Conversation>
  );
};
