import { useCallback, useEffect, useRef, useState } from "react";
import type { LiveAgent } from "@/hooks/use-live-agent";
import type { LiveToolPart } from "@/lib/live-types";

/**
 * Turnover inspection checklist (the Master QC form) + live agent bridge.
 *
 * The checklist page (public/inspection.html) exposes `window.qcInspection`
 * (addPhoto / setNote / setChecked / getState). This view embeds it and folds
 * the agent's journal + camera tool results into it as they stream:
 *
 *  - journal / record_checklist_result  -> setChecked + setNote (by item slug)
 *  - take_photo / capture_photo         -> addPhoto (workspace file URL)
 */

type QcInspectionApi = {
  addPhoto: (id: string, src: string, tag?: string) => boolean;
  setNote: (id: string, text: string) => boolean;
  setChecked: (id: string, checked: boolean) => boolean;
  listItems: () => string[];
  getState: () => unknown;
};

/** Same slug rule as inspection.html builds its data-ids with. */
const slugify = (label: string) =>
  label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};

const firstString = (...values: unknown[]): string | undefined =>
  values.find((value): value is string => typeof value === "string" && value.length > 0);

/** Pull image paths out of arbitrary tool output (take_photo returns file paths). */
const extractImagePaths = (value: unknown, found: string[] = []): string[] => {
  if (typeof value === "string") {
    const matches = value.match(/[\w\-./]+\.(?:jpe?g|png|webp)/gi);
    if (matches) found.push(...matches);
  } else if (Array.isArray(value)) {
    for (const entry of value) extractImagePaths(entry, found);
  } else if (typeof value === "object" && value !== null) {
    for (const entry of Object.values(value)) extractImagePaths(entry, found);
  }
  return found;
};

const toWorkspaceUrl = (path: string): string => {
  if (path.startsWith("http") || path.startsWith("data:")) return path;
  const relative = path.replace(/^.*?workspace\//, "").replace(/^\.?\//, "");
  return `/workspace/${relative}`;
};

const JOURNAL_TOOLS = new Set(["record_checklist_result", "journal"]);
const PHOTO_TOOLS = new Set(["take_photo", "capture_photo"]);

/** Returns true when the part changed the checklist. */
const applyToolPart = (
  api: QcInspectionApi,
  part: LiveToolPart,
  getLatestFrame?: () => string | null
): boolean => {
  const input = asRecord(part.input);
  const label = firstString(
    input.item,
    input.item_label,
    input.label,
    input.checklist_item,
    input.item_id,
  );
  const slug = label ? slugify(label) : undefined;

  if (JOURNAL_TOOLS.has(part.toolName)) {
    if (!slug) return false;
    let changed = false;
    const result = firstString(input.result, input.status)?.toUpperCase();
    if (result === "PASS") changed = api.setChecked(slug, true) || changed;
    if (result === "FAIL") changed = api.setChecked(slug, false) || changed;
    const note = firstString(input.notes, input.note);
    if (note) changed = api.setNote(slug, note) || changed;
    // Pin the current device-camera frame to this item (any-order routing:
    // whatever the camera sees when the agent records the item).
    if (input.attach_photo === true || input.attach_photo === "true") {
      const frame = getLatestFrame?.();
      if (frame) {
        const tag = firstString(input.photo_tag, input.tag) ?? "evidence";
        changed =
          api.addPhoto(slug, `data:image/jpeg;base64,${frame}`, tag) || changed;
      }
    }
    return changed;
  }

  if (PHOTO_TOOLS.has(part.toolName)) {
    if (!slug) return false;
    const tag = firstString(input.tag, input.photo_type) ?? "evidence";
    let changed = false;
    for (const path of extractImagePaths(part.output)) {
      changed = api.addPhoto(slug, toWorkspaceUrl(path), tag) || changed;
    }
    return changed;
  }

  return false;
};

export const InspectionView = ({
  agent,
  open,
  onAgentEdit,
}: {
  agent: LiveAgent;
  open: boolean;
  onAgentEdit?: () => void;
}) => {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const [ready, setReady] = useState(false);
  const onAgentEditRef = useRef(onAgentEdit);
  onAgentEditRef.current = onAgentEdit;

  const handleLoad = useCallback(() => setReady(true), []);

  useEffect(() => {
    if (!ready) return;
    const frame = frameRef.current;
    const api = (frame?.contentWindow as (Window & { qcInspection?: QcInspectionApi }) | null)
      ?.qcInspection;
    if (!api) return;

    let edited = false;
    for (const message of agent.messages) {
      for (const part of message.parts) {
        if (!("toolCallId" in part)) continue;
        // Journal edits apply as soon as the call's input is known; photo edits
        // need the tool output (the captured file paths).
        const journalReady =
          JOURNAL_TOOLS.has(part.toolName) &&
          (part.state === "input-available" || part.state === "output-available");
        const photoReady = PHOTO_TOOLS.has(part.toolName) && part.state === "output-available";
        if (!journalReady && !photoReady) continue;
        const key = `${part.toolCallId}:${part.toolName}:${photoReady ? "out" : "in"}`;
        if (appliedRef.current.has(key)) continue;
        appliedRef.current.add(key);
        try {
          if (applyToolPart(api, part, agent.getLatestFrame)) edited = true;
        } catch {
          // never let a malformed tool payload break the checklist
        }
      }
    }
    // Surface the checklist whenever the agent touched it.
    if (edited) onAgentEditRef.current?.();
  }, [agent.messages, agent.getLatestFrame, ready]);

  return (
    <iframe
      className={open ? "min-h-0 flex-1 border-0" : "hidden"}
      onLoad={handleLoad}
      ref={frameRef}
      src="/inspection.html"
      title="Turnover inspection checklist"
    />
  );
};
