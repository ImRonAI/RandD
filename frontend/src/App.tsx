import {
  AudioLinesIcon,
  ClipboardCheckIcon,
  MessageSquareTextIcon,
  PanelRightIcon,
  SlidersHorizontalIcon,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useLiveAgent } from "@/hooks/use-live-agent";
import { AgentPanel } from "@/views/AgentPanel";
import { ChatThread } from "@/views/ChatThread";
import { Composer } from "@/views/Composer";
import { InspectionView } from "@/views/InspectionView";
import { VoiceDock } from "@/views/VoiceDock";

const App = () => {
  const agent = useLiveAgent();
  const [agentPanelOpen, setAgentPanelOpen] = useState(false);
  const [inspectionOpen, setInspectionOpen] = useState(false);
  const [dockOpen, setDockOpen] = useState(false);

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-50 flex h-14 shrink-0 items-center justify-between gap-2 border-b bg-background/80 backdrop-blur-md px-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 font-serif text-xl font-medium tracking-tight">RandD Live</span>
          <span className="hidden truncate text-muted-foreground text-xs sm:inline">
            {agent.models.find((entry) => entry.id === agent.model)?.name ??
              agent.agentCard?.model ??
              "Gemini Live"}{" "}
            ·{" "}
            <span
              className={
                agent.status === "connected"
                  ? "text-primary"
                  : "text-muted-foreground"
              }
            >
              {agent.status}
            </span>
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            onClick={() => agent.setMode("text")}
            size="sm"
            variant={agent.mode === "text" ? "secondary" : "ghost"}
          >
            <MessageSquareTextIcon className="size-4" />
            <span className="hidden sm:inline">Text</span>
          </Button>
          <Button
            onClick={() => agent.setMode("audio")}
            size="sm"
            variant={agent.mode === "audio" ? "secondary" : "ghost"}
          >
            <AudioLinesIcon className="size-4" />
            <span className="hidden sm:inline">Voice</span>
          </Button>
          <Button
            onClick={() => setInspectionOpen((open) => !open)}
            size="sm"
            variant={inspectionOpen ? "secondary" : "ghost"}
          >
            <ClipboardCheckIcon className="size-4" />
            <span className="hidden sm:inline">Inspection</span>
          </Button>
          <Button
            aria-label="Voice and camera controls"
            className="md:hidden"
            onClick={() => setDockOpen((open) => !open)}
            size="sm"
            variant={dockOpen ? "secondary" : "ghost"}
          >
            <SlidersHorizontalIcon className="size-4" />
            <span className="hidden sm:inline">Voice/Camera</span>
          </Button>
          <Button
            onClick={() => setAgentPanelOpen((open) => !open)}
            size="sm"
            variant={agentPanelOpen ? "secondary" : "ghost"}
          >
            <PanelRightIcon className="size-4" />
            <span className="hidden sm:inline">Agent</span>
          </Button>
        </div>
      </header>

      {agent.error && (
        <div className="border-destructive/50 border-b bg-destructive/10 px-4 py-2 text-destructive text-sm">
          {agent.error}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          {/* Always mounted so checklist state persists and agent edits land
              in real time; it auto-surfaces whenever the agent updates it. */}
          <InspectionView
            agent={agent}
            onAgentEdit={() => setInspectionOpen(true)}
            open={inspectionOpen}
          />
          {!inspectionOpen && <ChatThread agent={agent} />}
          <Composer agent={agent} />
        </main>
        <VoiceDock
          agent={agent}
          onClose={() => setDockOpen(false)}
          open={dockOpen}
        />
        {agentPanelOpen && <AgentPanel agent={agent} />}
      </div>
    </div>
  );
};

export default App;
