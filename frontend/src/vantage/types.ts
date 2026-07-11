export type SaveState = "local" | "saving" | "saved" | "queued" | "failed" | "conflict" | "offline";
export type Role = "org_admin" | "property_manager" | "inspector" | "housekeeper" | "facilities" | "office_dispatch" | "owner";
export type Organization = { id: string; name: string; role: Role };
export type UserSession = { id: string; email: string; name?: string; activeOrganizationId?: string; organizations: Organization[] };
export type RoomType = { id: string; name: string; active: boolean };
export type Media = { id: string; status: "pending" | "uploading" | "verified" | "failed"; originalName: string; sha256?: string; retryable?: boolean };
export type Asset = { id: string; clientId: string; roomId: string; type: string; name: string; locationDetail?: string; manufacturer?: string; modelNumber?: string; serialNumber?: string; notes?: string; completionStatus: "draft" | "complete"; originals: Media[]; saveState?: SaveState; version?: number };
export type Room = { id: string; clientId: string; homeId: string; roomType: RoomType; name: string; floorArea?: string; notes?: string; displayOrder: number; state: "active" | "archived"; assets: Asset[]; saveState?: SaveState; version?: number };
export type Home = { id: string; name: string; unitCode: string; address: string; cluster?: string; onboardingStatus?: "not_started" | "draft" | "complete"; roomCount?: number; assetCount?: number };
export type Inspection = { id: string; clientId: string; home: Home; type: "onboarding" | "turnover"; status: "draft" | "completed"; rooms: Room[]; updatedAt: string; saveState?: SaveState; version: number };
export type ApiError = { code: string; message: string; retryable: boolean; fields?: Record<string, string>; currentVersion?: number };
export type Result<T> = { ok: true; data: T } | { ok: false; error: ApiError };
export type DayStop = { id: string; home: Home; stage: string; timeLabel?: string; assignee?: string; exception?: string; progress?: { complete: number; total: number } };
export type ReportSummary = { id: string; homeName: string; kind: "operational" | "owner"; status: "pending" | "ready" | "failed"; createdAt: string };

export type PlaceValidation = { status: "validated" | "stale" | "unverified" | "failed"; formattedAddress?: string; validatedAt?: string };
export type CalendarDayStop = DayStop & { taskId: string; calendarEventId?: string; calendarTitle?: string; startAt?: string; endAt?: string; place?: PlaceValidation };
export type RouteStep = { id: string; instruction: string; distanceText: string; durationText?: string; maneuver?: string };
export type RouteLeg = { id: string; fromLabel: string; toLabel: string; distanceText: string; durationText: string; eta: string; trafficAware?: boolean; path?: string; googleMapsUrl: string; steps: RouteStep[] };
export type DayRoute = { date: string; stops: CalendarDayStop[]; legs: RouteLeg[]; calendarSyncedAt?: string; routeGeneratedAt?: string; connectionStatus: "connected" | "stale" | "disconnected" | "failed" };
export type AgentMessage = { id: string; role: "agent" | "user" | "system"; text: string; createdAt: string };
export type ApprovalStatus = "pending" | "reshoot" | "resolving" | "approved" | "expired" | "cancelled" | "disconnected" | "upload_failed" | "resumed";
export type ApprovalRequest = { approvalId: string; inspectionId: string; itemId?: string; assetId?: string; destinationLabel: string; proposedVerdict?: "PASS" | "FAIL" | "NA"; rationale: string; mediaId: string; mediaUrl?: string; expiresAt: string; status: ApprovalStatus; error?: string };
export type ApprovalResolution = { approvalId: string; decision: "approve" | "reshoot" | "cancel"; feedback?: string; inputMode?: "text" | "voice" };
export type AgentServerEvent =
  | ({ type: "agent_message" } & AgentMessage)
  | ({ type: "approval_requested" } & Omit<ApprovalRequest, "status" | "destinationLabel"> & { destinationLabel?: string; itemLabel?: string; assetLabel?: string })
  | { type: "approval_completed"; approvalId: string; message?: string }
  | { type: "approval_expired" | "approval_cancelled"; approvalId: string; message?: string }
  | { type: "approval_resumed"; approvalId: string }
  | { type: "camera_requested"; mode: "photo"; instruction: string; destinationLabel: string }
  | { type: "bidi_transcript_stream"; text?: string; transcript?: string; role?: "agent" | "user"; isFinal?: boolean }
  | { type: "navigation_progress"; legIndex: number; stepIndex: number; state?: "locating" | "active" | "rerouting" | "arrived" | "error"; message?: string };
