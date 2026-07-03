# DESIGN.md — Frontend Design System & Interaction Guide

> The single source of truth for how the product **looks, feels, and behaves** on the front end.
> Product scope lives in [AGENTS.md](AGENTS.md); delivery status lives in [TASKS.md](TASKS.md).
> This document is written for the engineers and design agents building the Next.js app. When in doubt, follow the **principles** (§2) over the specifics.

---

## Table of contents

1. [How to use this document](#1-how-to-use-this-document)
2. [Design principles](#2-design-principles)
3. [Brand & art direction](#3-brand--art-direction)
4. [Color system](#4-color-system)
5. [Typography](#5-typography)
6. [Spacing, layout & grid](#6-spacing-layout--grid)
7. [Radius, borders, elevation & texture](#7-radius-borders-elevation--texture)
8. [Iconography & imagery](#8-iconography--imagery)
9. [Motion & animation](#9-motion--animation)
10. [Design tokens (consolidated)](#10-design-tokens-consolidated)
11. [Component system](#11-component-system)
12. [Information architecture & navigation](#12-information-architecture--navigation)
13. [Key screens & flows](#13-key-screens--flows)
14. [Voice & multimodal interaction patterns](#14-voice--multimodal-interaction-patterns)
15. [Status & data-visualization language](#15-status--data-visualization-language)
16. [Content, voice & tone](#16-content-voice--tone)
17. [Accessibility](#17-accessibility)
18. [Responsive & field-use](#18-responsive--field-use)
19. [Frontend architecture & stack](#19-frontend-architecture--stack)
20. [Definition of Done (per screen)](#20-definition-of-done-per-screen)
21. [Governance — do's & don'ts](#21-governance--dos--donts)
22. [Open design decisions](#22-open-design-decisions)

---

## 1. How to use this document

- **Building a screen?** Read §2 (principles), §13 (the screen spec), then pull tokens from §10 and components from §11.
- **Adding a component?** Check §11 first — prefer shadcn/ui primitives and AI Elements before building custom.
- **Unsure about a color, size, or motion?** There is a token for it in §10. Do not hardcode values.
- **Designing anything the agent speaks or shows?** §14 and §16 are mandatory reading.

This is a living contract. Propose changes via PR to this file; don't fork the language in code.

---

## 2. Design principles

Six tenets. They resolve most decisions.

1. **Evidence over assertion.** The product's value is _verifiable_ readiness. Photos, timestamps, and sign-offs are first-class citizens, framed with the care of a gallery — never buried behind IDs. If the UI claims a home is ready, the proof is one glance away.
2. **Calm under pressure.** Users work against arrival deadlines, often outdoors, sometimes with poor signal. The interface is quiet, high-contrast, and decisive. No noise, no anxiety, no ambiguous states.
3. **One clear next action.** Every screen answers "what do I do now?" A single primary action dominates; everything else recedes. The agent and the UI never compete for attention.
4. **Field-first, boardroom-worthy.** Designed thumb-first for a housekeeper in a cold cabin, yet composed enough that an owner reviewing a report feels the operator is meticulous and premium.
5. **The agent is a colleague, not a chatbot.** Voice is the primary interface. Text, transcript, and controls exist to _support_ the conversation and keep the human in control — able to see, interrupt, and override at all times.
6. **Editorial restraint.** Generous whitespace, real typographic hierarchy, hairline rules, one warm accent. When tempted to decorate, remove instead. Confidence reads as calm.

---

## 3. Brand & art direction

### 3.1 The idea

The product is the **operational conscience** of a portfolio of homes — the thing that guarantees a guest crosses the threshold into a home that is genuinely ready. It should feel like a meticulous, warm, unflappable head of housekeeping: precise, trustworthy, and quietly premium.

### 3.2 Working name — _Threshold_ (proposal)

> **Proposal, not a mandate.** No brand exists in the repo yet. `Threshold` carries a deliberate double meaning: the **quality threshold** every home must clear, and the **doorway** a guest crosses into a ready home. It is short, editorial, and trademarkable-sounding. Alternatives worth a look: **Hearth**, **Clearing** ("cleared for guests"), **Keep**, **Vantage**. All tokens below are brand-agnostic and survive a rename — confirm or replace in §22.

- **Tagline:** _Every home, guest-ready._
- **Agent persona (proposal):** a warm, competent field companion. Optionally named **"the Keeper."** Gender-neutral voice, plain-spoken, safety-first. See §16 for voice.

### 3.3 Art direction — _"Editorial Alpine Utility"_

A tension between two moods, held in balance:

- **Editorial** — a refined serif, generous margins, small-caps labels, hairline rules, the feel of a well-made field journal or a premium print magazine.
- **Utility** — dense, legible data; large tap targets; unambiguous status; built to survive sunlight, gloves, and low battery.

The result is neither a sterile SaaS dashboard nor a playful consumer app. It is a **precise instrument that happens to be beautiful**.

**Mood words:** meticulous · warm · quiet · trustworthy · grounded · unhurried.
**Anti-mood:** flashy · neon · gamified · cluttered · corporate-generic · "AI purple gradient."

### 3.4 Logo & mark direction

- A **doorway/aperture** motif — a simple arched or squared threshold that doubles as a "frame" (nodding to the photo-evidence core). Works as a 1-color glyph at 20px in a nav bar and embossed on a report cover.
- Pair the mark with the display serif wordmark. Keep it monochrome (ink on paper / paper on ink); let the **ember** accent appear only in the active state.

### 3.5 Photography treatment

Photos _are_ the product. Treat every captured image with intent:

- Consistent aspect ratios (**4:3** for room/asset capture, **1:1** for detail crops, **16:9** for hero/property covers).
- A hairline `border` + tiny inner radius; never a heavy shadow. Let the image speak.
- Captions in **small-caps mono**, muted: `KITCHEN · SINK · 07:42 · MARIBEL`.
- Status is expressed by a small corner pip or a left border in the semantic color (§15), never by tinting the photo itself.
- Baseline vs. current comparisons use a clean side-by-side or a slider, equal weight, labeled `BASELINE` / `TODAY`.

---

## 4. Color system

**Philosophy — "Paper, Ink & Ember."** A warm paper base and near-black ink give the editorial foundation. A single warm **ember** accent carries brand and primary action. Functional status colors are a disciplined, muted layer kept clearly distinct from the brand accent so "brand green" never gets confused with "PASS green" (there is no brand green — green means _ready_, always).

Values are given in **OKLCH** (what modern shadcn/Tailwind theming uses) with an approximate hex for reference. Implement as CSS variables (§10); never hardcode in components.

### 4.1 Light theme (default)

| Token | OKLCH | ~Hex | Use |
| --- | --- | --- | --- |
| `--background` | `0.975 0.008 85` | `#F8F5EE` | App canvas (warm paper) |
| `--surface` | `0.992 0.006 85` | `#FCFBF6` | Cards, sheets |
| `--surface-sunken` | `0.955 0.010 82` | `#EFEBE0` | Wells, inputs, code |
| `--foreground` | `0.235 0.010 60` | `#2B2926` | Primary text (warm ink) |
| `--muted-foreground` | `0.545 0.012 60` | `#7C776E` | Secondary text, captions |
| `--border` | `0.900 0.008 80` | `#E4DFD3` | Hairlines, dividers |
| `--ring` | `0.63 0.14 47` | `#C1663F` | Focus ring (ember) |
| `--primary` | `0.63 0.14 47` | `#C1663F` | Ember — primary actions, brand |
| `--primary-foreground` | `0.99 0.01 85` | `#FDFBF6` | Text on ember |
| `--accent` | `0.94 0.03 55` | `#F3E7DA` | Soft ember tint — hovers, active bg |
| `--accent-foreground` | `0.30 0.06 47` | `#5A3A2A` | Text on accent |

### 4.2 Dark theme (low-light / battery / night crews)

| Token | OKLCH | ~Hex | Use |
| --- | --- | --- | --- |
| `--background` | `0.205 0.010 60` | `#231F1B` | App canvas (warm charcoal) |
| `--surface` | `0.245 0.012 60` | `#2C2823` | Cards, sheets |
| `--surface-sunken` | `0.180 0.010 60` | `#1C1915` | Wells, inputs |
| `--foreground` | `0.940 0.006 85` | `#ECE8DF` | Primary text (warm off-white) |
| `--muted-foreground` | `0.680 0.012 70` | `#A49E92` | Secondary text |
| `--border` | `0.320 0.010 60` | `#463F38` | Hairlines |
| `--primary` | `0.70 0.14 47` | `#D6784E` | Ember (lifted for contrast) |
| `--primary-foreground` | `0.20 0.02 60` | `#221E19` | Text on ember |
| `--accent` | `0.30 0.03 47` | `#3A2E26` | Ember tint bg |

### 4.3 Semantic / status palette (both themes, tuned per mode)

| Meaning | Token | Light ~Hex | Dark ~Hex | Where |
| --- | --- | --- | --- | --- |
| **Ready / PASS** | `--status-ready` | `#4E7C5A` (pine) | `#6FA47E` | Readiness, PASS, DONE |
| **Caution / attention** | `--status-caution` | `#B98729` (ochre) | `#D9A64A` | Due soon, NA-with-note, pending |
| **Fault / FAIL / urgent** | `--status-fault` | `#A83C2E` (brick) | `#D0604F` | FAIL, urgent WO, errors |
| **Info / neutral** | `--status-info` | `#5B6B86` (slate) | `#8497B4` | Informational, syncing |
| **Offline** | `--status-offline` | `#7C776E` (muted) | `#A49E92` | Offline / queued |

Rules:

- **Green is reserved for "ready/pass."** Never use green for brand, links, or generic success chrome.
- Every status must be legible **without** color (pair with an icon and/or label — §15, §17).
- Semantic colors are for state, not decoration. Chrome stays paper/ink/ember.

### 4.4 Contrast

All text meets **WCAG 2.2 AA** (≥ 4.5:1 body, ≥ 3:1 large/UI). Status colors are validated against both `--surface` and `--background` in both themes. Outdoor "high-contrast" mode (§18) bumps foreground/border tokens without changing hue.

---

## 5. Typography

A three-family system: an **editorial serif** for voice and headlines, a **modern grotesque** for UI and data, and a **mono** for codes and machine facts.

| Role | Family | Why |
| --- | --- | --- |
| Display / editorial | **Fraunces** (variable, `opsz`+`wght`) | Characterful high-contrast serif; carries the editorial, premium, human tone. Google Fonts, well supported. |
| UI / body / data | **Geist Sans** (variable) | Clean neo-grotesque; superb for dense data and controls; pairs natively with the Next.js/AI-Elements aesthetic. |
| Mono / codes | **Geist Mono** | Door codes, Wi-Fi, timestamps, IDs, telemetry — anything that is a _fact_, not prose. |

> If a family is unavailable, fall back: Fraunces → Newsreader → Georgia; Geist → Inter → system-ui; Geist Mono → ui-monospace.

### 5.1 Type scale

| Token | Family | Size / line-height | Weight | Use |
| --- | --- | --- | --- | --- |
| `display-xl` | Fraunces | 44 / 46 | 500 | Report covers, hero empty states |
| `display-l` | Fraunces | 34 / 38 | 500 | Screen titles (editorial moments) |
| `title` | Fraunces | 26 / 30 | 500 | Section headers, property names |
| `h1` | Geist | 22 / 28 | 600 | Screen titles (utility screens) |
| `h2` | Geist | 19 / 26 | 600 | Card headers |
| `h3` | Geist | 16 / 22 | 600 | Sub-headers, list group titles |
| `body-l` | Geist | 17 / 26 | 400 | Reading text, transcript |
| `body` | Geist | 15 / 22 | 400 | Default UI text |
| `body-s` | Geist | 13 / 18 | 400 | Secondary, metadata |
| `label` | Geist | 12 / 16 | 600, +6% tracking, UPPERCASE | Small-caps section labels, chips |
| `mono` | Geist Mono | 14 / 20 | 400 | Codes, timestamps, numeric readouts |
| `mono-s` | Geist Mono | 12 / 16 | 400 | Photo captions, fine facts |

### 5.2 Editorial rules

- Use **Fraunces sparingly** — titles, property names, report headings, and the agent's "signature" moments. It is seasoning, not the meal.
- Section labels are **small-caps mono or `label`** with letter-spacing and a hairline rule beneath — the "field-journal" device.
- Generous leading for transcript and reports (readability under motion/outdoors).
- Numbers that matter (temperatures like `103°F`, deadlines, codes) render in **mono** so they read as instrument values.
- Never justify text; never hyphenate UI; avoid all-caps for anything longer than a label.

---

## 6. Spacing, layout & grid

- **Base unit: 4px.** Spacing scale (token → px): `0.5→2, 1→4, 2→8, 3→12, 4→16, 5→20, 6→24, 8→32, 10→40, 12→48, 16→64, 20→80, 24→96`.
- **8pt rhythm** for vertical stacking; 4pt for tight intra-component spacing.
- **Mobile gutters:** 16px (20px on ≥ `sm`). **Touch targets:** ≥ 44×44px (≥ 48px for primary field actions — §18).
- **Breakpoints:** `sm 640 · md 768 · lg 1024 · xl 1280 · 2xl 1536`.
- **Containers:** content max-width **720px** for reading/reports (editorial measure ~66ch), **1200px** for dashboards. Field screens are full-bleed single-column.
- **Layout model:** mobile = single column, thumb zone reserved at the bottom for primary action + nav. Desktop = left sidebar + fluid content, optional right rail for context (property card, activity).

---

## 7. Radius, borders, elevation & texture

- **Radius** (restrained, editorial): `--radius-sm 6` (chips, inputs), `--radius 10` (cards, sheets), `--radius-lg 14` (modals), `--radius-full` (orb, avatars, pills). Do **not** pill-shape everything; corners are soft, not bubbly.
- **Borders:** the hairline is the primary separator. `1px` `--border`; use rules and whitespace before you reach for shadow.
- **Elevation (minimal):**
  - `elev-0` flat, hairline only — default cards.
  - `elev-1` `0 1px 2px rgb(0 0 0 / 0.05)` — hoverable/interactive cards.
  - `elev-2` `0 8px 24px -8px rgb(0 0 0 / 0.18)` — sheets, popovers, the Voice Console.
  - Shadows are warm-neutral and soft; never harsh black.
- **Texture (optional, subtle):** a very low-opacity paper grain on large empty surfaces (≤ 3% opacity) and report covers. Must never reduce text contrast; disabled in high-contrast mode.

---

## 8. Iconography & imagery

- **Icon set:** **Lucide** (ships with shadcn/ui). Stroke `1.75px`, rounded joins. Sizes `16 / 20 / 24`. Icons clarify, they don't decorate.
- One icon per concept, used consistently: camera = capture, check = pass, triangle-alert = fault, wrench = work order, route = directions, home = property, mic = voice.
- **Never** rely on an icon alone for status — pair with color + label (§15, §17).
- **Imagery:** see §3.5. User photos dominate; avoid stock imagery entirely. Illustration, if ever used, is minimal line-work in ink/ember.

---

## 9. Motion & animation

Motion is **functional and calm** — it explains change and gives the voice agent life. Nothing bounces for fun.

- **Durations:** `--motion-fast 120ms` (hover, chips), `--motion 200ms` (most transitions), `--motion-slow 320ms` (sheets, screen transitions).
- **Easing:** standard `cubic-bezier(0.2, 0, 0, 1)` (decisive ease-out); entrances may use a gentle emphasized curve. No spring overshoot in chrome.
- **Voice motion (the exception that gets personality):**
  - **Idle:** the orb "breathes" — a 2.4s ease-in-out scale/opacity loop, ~2% amplitude.
  - **Listening:** a live waveform driven by input amplitude (mic RMS), in `--foreground`/neutral.
  - **Speaking:** waveform in `--primary` (ember), amplitude driven by output audio.
  - **Thinking / tool-running:** a slow indeterminate shimmer along the orb ring.
  - State changes crossfade over `--motion` (240ms); never hard-cut.
- **Reduced motion:** honor `prefers-reduced-motion`. Replace the waveform with a simple opacity pulse; disable breathing, grain animation, and screen slides (crossfade instead). No essential information is conveyed by motion alone.

---

## 10. Design tokens (consolidated)

Implement as CSS variables on `:root` / `.dark`, then map into Tailwind (v4 `@theme`). Components consume Tailwind classes / CSS vars — **never raw values**.

```css
/* globals.css — abbreviated; see §4–§9 for full tables */
:root {
  /* color (light) */
  --background: oklch(0.975 0.008 85);
  --surface: oklch(0.992 0.006 85);
  --surface-sunken: oklch(0.955 0.010 82);
  --foreground: oklch(0.235 0.010 60);
  --muted-foreground: oklch(0.545 0.012 60);
  --border: oklch(0.900 0.008 80);
  --primary: oklch(0.63 0.14 47);
  --primary-foreground: oklch(0.99 0.01 85);
  --accent: oklch(0.94 0.03 55);
  --ring: oklch(0.63 0.14 47);
  /* status */
  --status-ready: oklch(0.58 0.09 150);
  --status-caution: oklch(0.70 0.11 75);
  --status-fault: oklch(0.52 0.16 28);
  --status-info: oklch(0.55 0.06 250);
  --status-offline: oklch(0.55 0.012 60);
  /* radius */
  --radius-sm: 6px; --radius: 10px; --radius-lg: 14px;
  /* motion */
  --motion-fast: 120ms; --motion: 200ms; --motion-slow: 320ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  /* elevation */
  --elev-1: 0 1px 2px rgb(0 0 0 / 0.05);
  --elev-2: 0 8px 24px -8px rgb(0 0 0 / 0.18);
  /* fonts */
  --font-display: "Fraunces", Newsreader, Georgia, serif;
  --font-sans: "Geist", Inter, system-ui, sans-serif;
  --font-mono: "Geist Mono", ui-monospace, monospace;
}
.dark {
  --background: oklch(0.205 0.010 60);
  --surface: oklch(0.245 0.012 60);
  --surface-sunken: oklch(0.180 0.010 60);
  --foreground: oklch(0.940 0.006 85);
  --muted-foreground: oklch(0.680 0.012 70);
  --border: oklch(0.320 0.010 60);
  --primary: oklch(0.70 0.14 47);
  --primary-foreground: oklch(0.20 0.02 60);
  --accent: oklch(0.30 0.03 47);
  /* status (lifted) */
  --status-ready: oklch(0.70 0.09 150);
  --status-caution: oklch(0.78 0.11 75);
  --status-fault: oklch(0.64 0.15 28);
  --status-info: oklch(0.68 0.06 250);
}
```

**Naming convention:** semantic first (`--status-ready`, `--surface`), never literal (`--green`, `--gray-200`). Components reference roles, so a re-theme touches only this file.

> A generated Material-3 style token export also exists at [docs/design-tokens.material.yaml](docs/design-tokens.material.yaml) for reference; **this section is the source of truth.**

---

## 11. Component system

Three layers, in order of preference: **use shadcn/ui → use AI Elements → build custom.**

### 11.1 Foundation — shadcn/ui

The base primitive library (Radix + Tailwind), themed by §10. Use for: Button, Input, Textarea, Select, Dialog, Sheet, Drawer, Tabs, Card, Badge, Avatar, Tooltip, Popover, DropdownMenu, Accordion, Progress, Switch, Skeleton, Sonner (toasts), ScrollArea, Separator. Do not restyle per-instance; extend variants centrally.

**Button variants:** `primary` (ember, one per screen), `secondary` (surface + border), `ghost` (text), `destructive` (fault), `field` (≥48px, high-contrast — outdoor/gloved use).

### 11.2 AI surface — AI Elements

[AI Elements](https://ai-sdk.dev/elements) (Vercel, built on shadcn/ui, for AI SDK v5) power the agent surfaces. Install via `npx ai-elements@latest`. Map:

| Experience | AI Elements component(s) |
| --- | --- |
| Live transcript & turns | `Conversation`, `Message`, `Response` |
| Agent reasoning (when surfaced) | `Reasoning`, `Chain of Thought` |
| Tool activity (capture, log, WO, call) | `Tool`, `Task`, `Loader` |
| Captured photos inline | `Image` |
| Quick replies / guided answers | `Suggestion` |
| Report citations / source links | `Sources`, `Inline Citation` |
| Token/latency/context debugging | `Context` |
| Text entry fallback (no-voice) | `Prompt Input`, `Actions` |
| Rich report artifacts | `Artifact`, `Code Block` |

Keep AI Elements visually consistent with the foundation — they inherit the same tokens; override only spacing/typography to match §5–§6.

### 11.3 Custom components (build these)

Domain components not covered above. Each ships with all states (§11.4), a Storybook/preview, and a11y notes.

- **`VoiceOrb`** — the signature. A circular presence with a state machine (`idle · listening · thinking · speaking · tool · interrupted · offline`) and an audio-reactive waveform (§9, §14). Center of the Voice Console and the nav's primary action.
- **`MicControl`** — push-to-talk / hands-free toggle, mute, end-session; ≥ 56px; unmistakable states.
- **`ReadinessMeter`** — a property's guest-ready score/state: a calm segmented gauge (`ready` / `attention` / `not ready`) with the deciding factors one tap away. Never a naked percentage without cause.
- **`ChecklistRail`** — vertical progress of categories/items during an inspection; shows current item, PASS/FAIL/NA pips, required-photo indicator.
- **`PhotoEvidenceCard`** — the framed photo unit (§3.5): image, small-caps caption, status pip, linkage to space/asset/checklist item, tap-to-zoom, baseline compare.
- **`StagePipeline`** — the 8-stage turnover pipeline (QC→…→REPORT) as a compact, glanceable rail with completed/current/blocked states.
- **`WorkOrderCard`** — status, priority chip, assignee, before/after photos, source checklist item.
- **`RouteList` + `RouteMap`** — grouped daily tasks with map, directions launch, arrival countdowns.
- **`PropertyCredential`** — masked door code / Wi-Fi in mono with press-and-hold reveal + copy; audit-logged reveal.
- **`ReportSheet`** — the self-contained, embedded-photo report view + sign-off + delivery status.
- **`CaptureSheet`** — full-bleed camera capture with framing guides, retake, and offline-queue confirmation.
- **`StatusChip` / `PriorityChip`** — the atomic status vocabulary (§15).
- **`OfflineBanner` / `SyncIndicator`** — connectivity + queue state (§18).

### 11.4 Component states (required for every interactive component)

`default · hover · focus-visible · active/pressed · disabled · loading · empty · error · success`. Plus, where relevant: `offline/queued`, `readonly (role-gated)`. Focus-visible always shows the ember `--ring`. Loading uses `Skeleton`/`Loader`, never a spinner-only blank.

---

## 12. Information architecture & navigation

### 12.1 Primary structure (role-aware)

```text
Threshold
├─ Today            → daily route, deadlines, what's next
├─ Properties       → portfolio → property detail (spaces/assets/credentials/history)
├─ ● Voice          → the live agent console  (center, prominent)
├─ Work             → work orders (facilities) / inspections queue (QC)
└─ More             → reports, portfolio dashboard, settings, sign-out
```

- **Mobile:** fixed **bottom tab bar**, 5 slots, the **center slot is the Voice action** (raised, ember, the app's beating heart). Titles are short; icons + labels.
- **Desktop / tablet:** left **sidebar** with the same destinations; Voice becomes a persistent, dockable panel or a prominent sidebar action; content area gets an optional right context rail.
- **Role-awareness:** navigation adapts — a Housekeeper sees `Today · Voice · Checklist`; Facilities sees `Work Orders`; a Manager/Owner sees `Dashboard · Reports`. Same shell, filtered destinations.

### 12.2 Routes (Next.js App Router)

```text
/                         → role-aware home (redirects to /today for crews)
/today                    → daily route
/properties               → portfolio list
/properties/[unitCode]    → property detail
/tasks/[taskId]           → turnover overview (pipeline)
/tasks/[taskId]/inspect   → checklist runner
/voice                    → live voice console (also openable as an overlay)
/work-orders              → list
/work-orders/[id]         → detail
/reports/[reportId]       → report viewer
/dashboard                → manager/owner portfolio view
/settings                 → profile, theme, connectivity, integrations
```

---

## 13. Key screens & flows

Each screen: **purpose · anatomy · primary action · states.** The **Voice Console is the signature** — design it first and best.

### 13.1 ⭐ Live Voice Console (`/voice`)

**Purpose.** The primary way work gets done: a hands-free, photo-verified, voice-guided turnover with the agent. The human is always in control and can see everything the agent hears, thinks, does, and shows.

**Anatomy (mobile, top → bottom).**

1. **Context header** — property name (Fraunces `title`), unit code (mono), current stage chip, and a compact `ReadinessMeter`.
2. **Stage / `ChecklistRail`** — collapsible; shows where in the checklist we are.
3. **Transcript** (`Conversation`) — dual-role `Message`s: worker (right, neutral) and agent (left, subtle ember tint). Agent audio is transcribed live (`Response` streaming). Tool activity appears inline as `Tool`/`Task` cards ("📷 Capturing kitchen — sink", "📝 Logged: Bathroom 1 · towels · PASS", "🔧 Work order opened · smoke detector · URGENT"). Captured photos appear as inline `PhotoEvidenceCard`s the moment they're taken.
4. **`VoiceOrb`** — anchored in the thumb zone, animating per state (§9, §14).
5. **`MicControl`** — push-to-talk / hands-free toggle · mute · end. `Suggestion` chips offer quick spoken-or-tapped answers ("Pass", "Fail — needs repair", "Skip", "Repeat").

**Primary action.** Speak. Everything else supports it.

**States.** `connecting · idle · listening · thinking · speaking · tool-running · capturing (camera) · interrupted · offline (queued) · error (mic/permission/network)`. Permission-denied and offline states are explicit, calm, and recoverable (§14, §18).

### 13.2 Today / Daily Route (`/today`)

**Purpose.** Answer "where do I go and what's next?" **Anatomy.** A dated header; tasks grouped by **geo/cluster**, ordered by **arrival deadline**; each `RouteList` row shows property, arrival countdown, stage chips, assignee. A map (`RouteMap`) can expand; each row launches **directions**. **Primary action.** "Start" the next task (→ overview or straight into Voice). **States.** loading (skeleton rows), empty ("No turnovers today"), offline (cached route + banner), running-late (fault-tinted countdown).

### 13.3 Property detail (`/properties/[unitCode]`)

**Purpose.** The structured House object. **Anatomy.** Fraunces property name + address; **credentials** (`PropertyCredential`, masked door/Wi-Fi with reveal); **spaces & assets** (features w/ quantity + location); **standing instructions**; **baseline photos**; **history** (past turnovers, WOs, reports). **Primary action.** "Start turnover" / "Open checklist." **States.** include a clear "credential reveal" audit affordance.

### 13.4 Checklist / Inspection runner (`/tasks/[taskId]/inspect`)

**Purpose.** Category-by-category QC — voice-guided or manual. **Anatomy.** `ChecklistRail` (progress) + the current item large and legible: item text, **PASS / FAIL / NA** as big `field`-sized controls, a note field, and a **required-photo** capture button (`CaptureSheet`). Temperatures/values render in mono (`103°F`). **Primary action.** Set the current item's result → auto-advance. **States.** required-photo-missing (blocks completion), fail-captured (offers "open work order"), offline (queues locally), category-complete (satisfying, quiet confirmation).

### 13.5 Work Orders (`/work-orders`, `/work-orders/[id]`)

**Purpose.** Facilities triage and resolution. **Anatomy.** List filterable by status/priority; `WorkOrderCard`s. Detail shows the **source checklist item**, before/after `PhotoEvidenceCard`s, `StagePipeline` (NEW→…→DONE), assignee, priority. **Primary action.** advance status / add resolution photo. **States.** blocked (needs escalation, fault), urgent (removes unit from availability — flag prominently).

### 13.6 Report viewer (`/reports/[reportId]`)

**Purpose.** The premium, self-contained proof of readiness (also the artifact delivered to Slack). **Anatomy.** An **editorial report cover** (Fraunces `display`, property, date, "Ready for guests" verdict), category PASS/FAIL summaries, **embedded** `PhotoEvidenceCard`s, "repairs needed" + WO status, and **sign-off** + **delivery status** (`PENDING/SENT/FAILED`). **Primary action.** Sign off (→ triggers delivery). **States.** draft, awaiting-sign-off, signed, delivered, delivery-failed (retry).

### 13.7 Manager/Owner dashboard (`/dashboard`, desktop-first)

**Purpose.** Portfolio readiness at a glance. **Anatomy.** Readiness by property (`ReadinessMeter` grid), the pipeline funnel, today's exceptions (late, failed, blocked WOs), recent deliveries. **Primary action.** Drill into an exception. **States.** all-clear (calm, reassuring), exceptions (surfaced, prioritized).

### 13.8 Cross-cutting flows

- **Turnover happy path:** Today → Start → Voice-guided checklist (capture photos) → all PASS → Report → sign-off → Slack delivery.
- **Failure path:** FAIL item → agent confirms → **work order** opened + Facilities notified → stage → report reflects repair status.
- **Offline path:** capture + checklist queued locally → banner → auto-sync on reconnect → conflict-free reconciliation.

---

## 14. Voice & multimodal interaction patterns

This is what makes the product distinct. The agent runs on **Gemini Live** (bidirectional audio); the UI is its transparent, controllable window.

### 14.1 Presence & state (the `VoiceOrb`)

The orb is the agent's body. Its state is always truthful to the connection:

| State | Visual | Meaning |
| --- | --- | --- |
| `connecting` | ring shimmer, muted | establishing the live session |
| `idle` | slow breathing (§9) | ready, listening for wake/hold |
| `listening` | neutral waveform, mic hot | capturing the human's speech |
| `thinking` | ring shimmer | model is reasoning / awaiting tool |
| `speaking` | ember waveform | agent audio is playing |
| `tool` | orbiting dot + inline `Tool` card | a tool is running (capture/log/WO/call) |
| `interrupted` | waveform collapses instantly | human barged in — agent yields immediately |
| `offline` | dimmed, offline pip | no connection — queued mode |

### 14.2 Turn-taking & barge-in

- **Interruption is sacred.** The moment the human speaks, the agent stops talking (`BidiInterruptionEvent`). Reflect it instantly — the orb collapses the speaking waveform within one frame. Never let the agent talk over a person.
- **Two input modes:** **hands-free** (VAD, default in the field) and **push-to-talk** (explicit, for noisy environments). The `MicControl` makes the active mode obvious.
- **Latency honesty:** show `thinking`/`Loader` the instant a turn ends; never a dead, ambiguous pause. Target perceived responsiveness < 2–3s (NFR); if a tool is slow, the inline `Task` card names what's happening.

### 14.3 Multimodal capture

- The agent can **request a photo** ("Point the camera at the sink"). This opens `CaptureSheet` with framing guidance; the captured image returns **inline** in the transcript as a `PhotoEvidenceCard` and is linked to the current checklist item/asset.
- Photo _understanding_ is the model's (Gemini Live is natively multimodal) — the UI never claims to "analyze"; it shows the agent's grounded observation as a normal turn, with the photo as the citation.

### 14.4 Transparency & control

- **See everything:** live transcript of both sides, every tool call, every verdict. Nothing the agent does to real data (open WO, send report, place a call) happens without a visible card and — for high-stakes/irreversible actions — a **confirm** step (`Actions`).
- **Override anything:** any agent verdict can be corrected by the human inline (a FAIL→PASS override is logged with who/when).
- **Text fallback:** when voice isn't possible (quiet lobby, hearing needs), `Prompt Input` drives the exact same flow.

### 14.5 Permissions & failure

- **Mic/camera permission** requests are explained _before_ the browser prompt (why we need it), with a graceful denied-state and a path to re-enable.
- **Connection loss** mid-session → switch to `offline`/queued, keep the checklist usable, resync on reconnect. Never lose captured work.

---

## 15. Status & data-visualization language

A tiny, ruthless vocabulary — learn it once, read it everywhere. **Color + icon + label, always** (never color alone).

| Concept | Values | Color token | Icon | Label style |
| --- | --- | --- | --- | --- |
| Checklist result | PASS / FAIL / NA | ready / fault / muted | check / triangle-alert / minus | `label` chip |
| Readiness | Ready / Attention / Not ready | ready / caution / fault | check-circle / dot / x-circle | `ReadinessMeter` |
| WO priority | LOW / MEDIUM / HIGH / URGENT | info / muted / caution / fault | flag scale | `PriorityChip` |
| WO status | NEW→ASSIGNED→IN_PROGRESS→BLOCKED→DONE→CANCELLED | info…ready…fault | pipeline | `StagePipeline` |
| Turnover stage | QC · B2B · CLN · DONE · OWN · WO · DONE_WO · REPORT | neutral + current/complete | — | `StagePipeline` |
| Delivery | PENDING / SENT / FAILED | caution / ready / fault | clock / check / alert | inline in `ReportSheet` |
| Connectivity | Online / Syncing / Offline-queued | ready / info / offline | wifi states | `SyncIndicator` |

Charts (dashboard) are minimal: hairline axes, ink strokes, ember for the "focus" series, semantic colors only for status breakdowns. No 3D, no gradients-for-decoration, no pie charts where a bar will do.

---

## 16. Content, voice & tone

### 16.1 Product copy

- **Plain, warm, precise.** Short sentences. Verbs first ("Start turnover", "Open work order", "Sign off"). No jargon, no exclamation-mark cheerfulness, no dark patterns.
- **Terminology (be consistent):** _property / home_ (not "listing"), _turnover_ (not "job"), _checklist item_, _work order_, _readiness_, _sign-off_, _the Keeper_ (agent, if named).
- **Numbers & facts** in mono; times relative where humane ("in 40 min") with absolute on tap.

### 16.2 Agent voice (spoken + transcript)

- **Persona:** a seasoned, unflappable head of housekeeping. Warm, direct, safety-first, never robotic, never chatty.
- **Behavior:** confirms before consequential actions ("I'll open an urgent work order for the smoke detector — okay?"); states observations as grounded facts tied to a photo; asks one clear question at a time; hands control back readily.
- **Never:** guess when it can verify; hide a failure; overwrite a human's override; use filler ("As an AI…").

### 16.3 States are content too

- **Empty states** earn their space — a Fraunces line + one action ("No turnovers today. Enjoy the mountain.").
- **Errors** say what happened, why, and the next step — calm, blame-free, recoverable.
- **Permissions** explain the _why_ before the ask.
- **Offline** reassures: "You're offline. Keep working — everything's saved and will sync automatically."

---

## 17. Accessibility

Target **WCAG 2.2 AA** (aim AAA for body contrast). Non-negotiable — field crews and owners of all abilities.

- **Contrast:** all tokens validated in both themes (§4.4); provide the outdoor high-contrast mode (§18).
- **Color independence:** every status carries icon + text (§15). The app is fully usable in grayscale.
- **Keyboard:** everything operable; visible ember focus ring (`focus-visible`); logical order; no traps; skip-to-content.
- **Screen readers:** semantic HTML + ARIA; the **live transcript is the accessible representation of voice** — announce agent turns via a polite live region; tool actions and captured photos have descriptive labels/alt.
- **Voice a11y:** always offer the text-input path (§14.4); captions/transcript for all agent speech; no task requires hearing.
- **Motion:** honor `prefers-reduced-motion` (§9); nothing critical conveyed by motion alone.
- **Targets:** ≥ 44px (≥ 48px field actions); spacing prevents mis-taps with gloves.
- **Forms:** labels always visible, errors associated, inputs never placeholder-only.

---

## 18. Responsive & field-use

Design for a cold cabin with one bar of signal before you design for a desk.

- **Mobile-first**, single column, bottom thumb zone for the primary action + Voice.
- **One-handed & gloved:** large targets, generous spacing, primary actions reachable by thumb; avoid tiny toggles and long-press-only interactions for critical paths.
- **Outdoor legibility:** a **high-contrast toggle** (bumps foreground/border, disables grain, strengthens shadows) and full dark mode; avoid low-contrast gray-on-gray anywhere.
- **Offline-capable (NFR):** checklist + photo capture work fully offline; an `OfflineBanner` + `SyncIndicator` communicate state; a local queue (IndexedDB) reconciles on reconnect; **never lose captured work**.
- **Performance (NFR):** route lists and photo interactions feel instant (< 2–3s); lazy-load photos; optimistic UI for checklist marks; keep the main thread free during voice.
- **Battery:** dark theme default at night; pause non-essential animation when backgrounded; downscale/queue photo uploads on poor networks.

---

## 19. Frontend architecture & stack

| Concern | Choice | Notes |
| --- | --- | --- |
| Framework | **Next.js (App Router) + TypeScript** | RSC where sensible; the "mobile app" is a mobile-first **PWA**. |
| Styling | **Tailwind CSS v4** + CSS variables (§10) | Tokens in `@theme`; no raw values in components. |
| UI primitives | **shadcn/ui** (Radix) | Themed by tokens; central variants. |
| AI surface | **AI Elements** + **Vercel AI SDK v5** | Transcript, tools, reasoning, streaming (§11.2). |
| Realtime voice transport | **WebSocket** bridge to the Python Gemini Live agent | Browser mic (16 kHz PCM) ⇄ agent ⇄ audio out (24 kHz PCM) + transcript/tool/interrupt events (TASKS.md M6.2). WebRTC an option if latency demands. |
| Server state | **TanStack Query** | Caching, optimistic updates, offline retries. |
| Client/UI state | **Zustand** | Voice-session + ephemeral UI state (orb state, capture flow). |
| Offline | **Serwist** (service worker) + **Dexie** (IndexedDB) | Installable PWA; queue checklist/photos; sync on reconnect. |
| Media | `getUserMedia` (mic/camera), Web Audio (waveform amplitude) | `CaptureSheet`, `VoiceOrb` visualizer. |
| Maps | **Google Maps JS + Directions** | `RouteMap`, directions launch (via `strands-google` server-side for planning). |
| Fonts | `next/font` — **Fraunces**, **Geist**, **Geist Mono** | Self-hosted, preloaded. |
| Auth | Role-based sessions (provider TBD — §22) | Map user → stakeholder role; gate nav + tools. |
| Icons | **Lucide** | Ships with shadcn. |
| Packaging (optional) | **Capacitor** wrapper | Only if app-store presence / native camera+push are required (TASKS.md M7.13). |

**Principles.** Server components for data-heavy reads; client components for anything interactive/voice. Optimistic UI for checklist marks. Keep the render thread free during a live session (offload audio viz to Web Audio/rAF). Every network call assumes it might fail or be offline.

**Token → Tailwind mapping.** CSS vars (§10) are the source of truth; Tailwind v4 `@theme` exposes them as `bg-surface`, `text-foreground`, `border-border`, `text-status-fault`, `rounded-[var(--radius)]`, `shadow-[var(--elev-2)]`, `font-display`, etc. Re-theming = editing `globals.css` only.

---

## 20. Definition of Done (per screen)

A screen is "done" when:

- [ ] Uses **only** tokens (§10) — zero hardcoded colors/sizes/fonts.
- [ ] Built from shadcn/ui + AI Elements before any custom code (§11).
- [ ] All component **states** present (§11.4), including empty/error/offline/loading.
- [ ] **One** clear primary action (§2.3); hierarchy legible at a glance.
- [ ] Responsive `sm→2xl`; thumb-reachable primary action on mobile (§18).
- [ ] Light + dark + high-contrast all pass **AA** (§17).
- [ ] Keyboard-operable; visible focus; SR-labeled; reduced-motion honored (§17, §9).
- [ ] Copy matches voice & terminology (§16); numbers/codes in mono.
- [ ] Offline behavior defined; no captured work can be lost (§18).
- [ ] Any agent action on real data shows a visible card + confirm where irreversible (§14.4).

---

## 21. Governance — do's & don'ts

### Do

- Prefer removing over adding. Whitespace is a feature.
- Reach for a hairline rule before a shadow; a label before an icon-only control.
- Keep green for "ready" only; keep ember for brand/primary only.
- Frame photos like evidence; caption them in mono.
- Make the agent's every action visible and reversible-or-confirmed.

### Don't

- Introduce new colors, fonts, or radii outside §10 without a PR to this file.
- Use gradients/glassmorphism/neon or "AI purple." This isn't that product.
- Pill-shape everything or over-round; keep corners composed.
- Let the agent speak over a human, or act on real data silently.
- Ship a status that reads as color alone.
- Block the field user when offline.

---

## 22. Open design decisions

Confirm or redirect (defaults chosen to keep momentum):

1. **Brand name & mark** — `Threshold` (proposal, §3.2) vs. an existing/preferred name. Affects wordmark, tone, domain.
2. **Agent persona name** — "the Keeper" vs. unnamed vs. operator's choice; affects voice copy (§16).
3. **Serif choice** — **Fraunces** (recommended, characterful) vs. Newsreader/Source Serif (quieter). Affects the editorial feel.
4. **Primary accent** — **ember/terracotta** (warm, hearth) vs. a deep pine or twilight indigo. Ember chosen for warmth + trust; easy to swap (one token).
5. **Mobile packaging** — PWA-only vs. PWA + Capacitor (native camera/push, store presence).
6. **Light vs. dark default** — proposal: **light** for day crews & owner reports, dark auto at night/low-battery.
7. **Dashboard depth for v1** — minimal exceptions view vs. fuller analytics (defer heavy analytics to Phase 2).

---

_Build calm, precise, and warm. When in doubt, make it quieter — and let the evidence speak._
