import type { ReactNode } from "react";
import { AlertTriangle, Check, CloudOff, LoaderCircle, RefreshCw } from "lucide-react";
import type { ApiError, SaveState } from "./types";
import { cn } from "@/lib/utils";

export function SaveIndicator({ state = "saved" }: { state?: SaveState }) {
  const map: Record<SaveState, [ReactNode, string]> = { local: [<CloudOff size={14}/>, "Local"], saving: [<LoaderCircle className="animate-spin" size={14}/>, "Saving"], saved: [<Check size={14}/>, "Saved"], queued: [<CloudOff size={14}/>, "Queued"], failed: [<AlertTriangle size={14}/>, "Save failed"], conflict: [<AlertTriangle size={14}/>, "Needs review"], offline: [<CloudOff size={14}/>, "Offline"] };
  return <span role="status" aria-live="polite" className={cn("v-save", state === "failed" || state === "conflict" ? "v-save--error" : "")}>{map[state][0]}{map[state][1]}</span>;
}
export function PageState({ kind, title, detail, retry }: { kind: "loading" | "empty" | "error"; title: string; detail: string; retry?: () => void }) {
  return <section className="v-state" role={kind === "error" ? "alert" : "status"}>{kind === "loading" ? <LoaderCircle className="animate-spin"/> : kind === "error" ? <AlertTriangle/> : <span className="v-state__mark">V</span>}<h2>{title}</h2><p>{detail}</p>{retry && <button className="v-button v-button--quiet" onClick={retry}><RefreshCw size={17}/>Try again</button>}</section>;
}
export function ErrorNotice({ error, retry }: { error?: ApiError | null; retry?: () => void }) { if (!error) return null; return <div className="v-error" role="alert"><AlertTriangle size={18}/><div><strong>{error.message}</strong><small>{error.retryable ? "Your local work is safe. You can retry." : "Review the highlighted information."}</small></div>{retry && <button onClick={retry}>Retry</button>}</div>; }
export function ScreenHeader({ eyebrow, title, action }: { eyebrow?: string; title: string; action?: ReactNode }) { return <header className="v-screen-header"><div>{eyebrow && <p>{eyebrow}</p>}<h1>{title}</h1></div>{action}</header>; }
