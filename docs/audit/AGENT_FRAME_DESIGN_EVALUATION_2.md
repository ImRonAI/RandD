# Vantage Persistent Agent Frame — Design Evaluation 2

**Verdict: MAJOR REVISION**

**Reviewed:** 2026-07-11  
**Build:** `http://127.0.0.1:5173/?review=agent-frame`  
**Reference:** `/var/folders/c8/y41r0sp91172dqm_0jk3wcww0000gn/T/codex-clipboard-83dbe88c-c606-4ba9-8750-6d685b2cdb78.png`  
**Viewports:** 1280×720 desktop and 390×844 mobile

The revision is a substantial visual and interaction improvement. It now communicates a distinct, premium field product; the desktop uses its space; the mobile camera opens inside the agent frame; and the proposed-photo / approve / retake sequence closely follows the supplied reference. It is not yet ready to sign off because three requirements remain structurally unproven or contradicted by the current UI: Vantage does not remain present on the mobile itinerary, the route surface is a decorative route diagram rather than a functioning Google map/navigation experience, and the review harness never renders a captured image in the approval preview.

## What passed

### Persistent agent home and responsive layout

- Desktop now uses a purposeful two-pane composition: Vantage remains the primary interaction surface on the left while a day/route overview occupies the right. The prior narrow-phone-strip-in-empty-canvas problem is resolved.
- The mobile home presents the connected-agent state, next Google Calendar stop, verified Places address, travel time, ETA, full-day entry point, navigation action, voice action, text composer, and camera entry point in one coherent frame.
- Visual hierarchy, cream/forest palette, editorial headings, restrained green/gold accents, spacing, and control styling are polished and consistent.
- A visible gold focus ring appeared during keyboard traversal. The inspected controls have useful accessible names, including camera, voice, navigation, itinerary close, route reordering, approval, and retry actions.
- The clean reload produced no browser console errors or warnings. Earlier console entries were attributable to the live development session/hot reload and did not recur after reload.

### Camera transition

- The camera opens in the upper portion of the existing agent frame instead of navigating to a disconnected camera screen.
- Vantage remains visible immediately beneath the camera in the normal camera-opening state, matching the intended “upper side reveals camera” behavior.
- Opening, permission failure, retry, original-file selection, continue-without-camera, flip-camera, shutter-disabled, and stop/close controls are represented.
- The failure state uses an alert and moves focus to the failure panel, which is appropriate recovery behavior.

### Approval lifecycle

- The proposed-evidence panel identifies the exact destination (`Kitchen · Refrigerator cold and clean`) and proposed verdict (`PASS`).
- The normal approval screen provides the two correct primary decisions: **Take Again** and **Approve**.
- **Take Again** becomes a clear instruction flow with both Voice and Type modes, a concrete prompt, and a disabled-until-populated send action.
- Resolving, approved, expired, disconnected, upload-failed, and resumed states are present with distinct status copy. Upload failure is exposed as an alert rather than silently accepted.
- The persistent live region announces connection and approval state changes.

### Calendar, Places, itinerary, and route ordering

- The home and itinerary explicitly show Google Calendar connection/freshness instead of presenting unexplained seeded stops.
- Places verification and address-review states are differentiated per stop.
- The itinerary provides keyboard-operable earlier/later controls, correctly disables impossible moves, and states that reordering refreshes the remaining route.
- Navigation retains voice and text access and exposes a Google Maps deep link.

## Release-blocking findings

### 1. The agent is not persistent on the mobile itinerary

**Severity: Critical to the stated product direction**

At 390×844, opening **My Day** replaces the entire Vantage agent frame with a full-screen itinerary sheet. The agent identity, live status, voice action, text composer, and contextual response surface all disappear. This directly conflicts with the requirement that the agent remain within the UI frame at all times, regardless of modality or task.

The itinerary should remain a layer *inside* the persistent agent shell. On mobile, retain at minimum a compact Vantage header/orb plus a docked voice/text composer (or an agent drawer that remains visibly available). The itinerary may own the content area, but it should not replace the agent.

### 2. The route visualization is not a real navigation surface

**Severity: Critical to turn-by-turn acceptance**

The inspected “map” is a CSS illustration with two roads and markers. The active navigation view always renders the first supplied step; there is no visible current-location acquisition, step progression, maneuver list, rerouting state, off-route handling, traffic disruption, route polyline from Google Maps, or transition from one completed house to the next. A Google Maps deep link is useful fallback, but it does not prove the in-product turn-by-turn requirement.

Replace the decorative map with the real Maps rendering boundary (or clearly label the in-app view as a route summary and hand off turn-by-turn to Google Maps). For an in-product experience, the review state must demonstrate: geolocation status, Google route/polyline, current maneuver, following maneuver, step advancement, ETA refresh, reroute/error state, arrival, and continuation to the next itinerary stop.

### 3. The photo preview is never demonstrated

**Severity: Critical to photo approval acceptance**

Every approval lifecycle state in the dev harness shows **“Original preview is loading”**. The reference design depends on the actual captured image being embedded in the agent frame so the user can judge the photograph before approving it. The current review harness therefore cannot prove the central approval interaction, image cropping/fit, loading-to-loaded transition, image failure recovery, or whether the correct original appears for the correct checklist item.

Seed the dev-only approval request with a representative local image/data URL and add explicit preview-loading and preview-failed states. The proposed, retake, resolving, approved, disconnected, resumed, expired, and upload-failed states should be inspectable with the actual preview visible where appropriate.

### 4. Camera failure and navigation can obscure the persistent agent on mobile

**Severity: High**

The camera-denied panel consumes most of the mobile viewport, pushing the Vantage conversation card below the fold. Triggering camera state while navigation is open also places camera content behind the navigation layer; the user sees the navigation surface rather than a clear camera takeover or a blocked-action explanation.

Keep the compact agent identity/status pinned during recovery, constrain the camera error panel, and define a single ownership rule for camera vs. navigation (for example: pause/collapse navigation when capture starts, then restore it after approval).

### 5. The review toolbar obstructs the controls it is meant to evaluate

**Severity: High for evaluation confidence; development-only**

At 390×844, the fixed dev toolbar covers the agent composer, itinerary navigation action, approval feedback submit button, navigation footer, and parts of long error/approval states. This does not affect production, but it prevents reliable visual and pointer testing of the full lifecycle.

Make the review controls collapsible, place them outside the simulated device viewport, or reserve layout space. A test harness must not cover the subject under review.

## Additional product and accessibility findings

- The itinerary’s “Refresh” and connection copy are good, but there is no visible Calendar disconnected/re-authentication state in the harness.
- Places exposes verified and needs-review states, but no editable address/Place selection flow is available from the reviewed screens.
- The navigation view has a labelled route overview but no semantic step list. If multiple maneuvers are available, expose them to screen readers and provide a concise next/then structure.
- The proposed photo’s destination is readable, but long destination labels become dense at mobile width. Preserve the checklist item and room identity without allowing the header to crowd the preview.
- The generic Vantage composer remains in the DOM below the retake-specific feedback composer. This creates two text/voice entry surfaces during retake. Prefer one clearly scoped active composer, or explain the difference semantically.
- Camera permission failure is well structured, but “Continue without camera” must not allow completion of an asset/checkpoint that requires an original photo; the UI should state that the requirement remains incomplete.
- The review mode covers approval statuses but not cancelled, preview-failed, route-loading, route-error, Calendar-disconnected, Places-resolution, or geolocation-denied states.

## Recommended acceptance gate for the next review

1. Vantage identity plus voice/text access remains visible on agent, itinerary, navigation, camera, photo preview, retake, and all recovery states at 390×844.
2. The approval harness displays a real representative image and separately demonstrates image loading and image failure.
3. The navigation harness proves either a real Google-rendered in-app route with step progression or an explicit Google Maps handoff contract; no decorative map is presented as live turn-by-turn.
4. The route demonstrates house-to-house continuation, reordering, current-location/geolocation denial, rerouting, arrival, and next-stop transition.
5. Calendar disconnected/reconnect and Places search/selection/address-review states are inspectable.
6. The dev controls no longer obscure application controls at mobile or desktop widths.
7. Keyboard-only traversal reaches all route, camera, approval, retry, and retake controls with visible focus; a screen-reader pass confirms state announcements and destination association.

## Summary

The agent-first home, embedded camera transition, approval card, and voice/text retake instruction are strong and substantially match the intended reference interaction. The remaining problems are not cosmetic. The product promise is “Vantage stays with the user throughout the day,” and the current mobile itinerary still removes Vantage; the navigation surface does not yet prove actual turn-by-turn behavior; and the approval surface has not been demonstrated with an image. Resolve those points before design approval.
