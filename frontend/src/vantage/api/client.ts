import type { ApiError, Asset, DayRoute, DayStop, Home, Inspection, Organization, ReportSummary, Result, Room, RoomType, UserSession } from "../types";

// Same-origin by default. Deployments can place the API behind the existing
// reverse proxy without exposing tenancy configuration to the browser.
const API = "";

async function request<T>(path: string, init: RequestInit = {}): Promise<Result<T>> {
  try {
    const response = await fetch(`${API}${path}`, { credentials: "include", ...init, headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers } });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const error = (body?.error ?? body?.detail?.error) as ApiError | undefined;
      return { ok: false, error: error ?? { code: `http_${response.status}`, message: "The service could not complete this request.", retryable: response.status >= 500 } };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: { code: "network_unavailable", message: "Vantage cannot reach the service. Your work can remain queued on this device.", retryable: true } };
  }
}

const json = (value: unknown) => JSON.stringify(value);
export const vantageApi = {
  requestCode: (email: string) => request<{ expiresAt: string }>("/api/auth/code/request", { method: "POST", body: json({ email }) }),
  verifyCode: (email: string, code: string) => request<UserSession>("/api/auth/code/verify", { method: "POST", body: json({ email, code }) }),
  me: () => request<UserSession>("/api/auth/me"),
  chooseOrganization: (organizationId: string) => request<{ organization: Organization }>("/api/auth/active-organization", { method: "POST", body: json({ organizationId }) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  wsToken: () => request<{ token: string; expiresAt: string }>("/api/auth/ws-token", { method: "POST" }),
  dayRoute: (date: string) => request<DayRoute>(`/api/navigation/day-route?date=${encodeURIComponent(date)}`),
  syncCalendar: () => request<{ syncedAt: string }>("/api/calendar/sync", { method: "POST" }),
  reorderDayRoute: (orderedTaskIds: string[], date = new Date().toISOString().slice(0, 10)) => request<DayRoute>("/api/navigation/day-route/reorder", { method: "POST", body: json({ orderedTaskIds, date }) }),
  roomTypes: () => request<RoomType[]>("/api/room-types"),
  homes: () => request<Home[]>("/api/field/properties"),
  day: () => request<DayStop[]>("/api/field/day"),
  reports: () => request<ReportSummary[]>("/api/reports"),
  inspection: (id: string) => request<Inspection>(`/api/inspections/${id}`),
  createInspection: (homeId: string, type: Inspection["type"], clientId: string) => request<Inspection>("/api/inspections", { method: "POST", headers: { "Idempotency-Key": clientId }, body: json({ homeId, type, clientId }) }),
  createRoom: (homeId: string, inspectionId: string, room: Pick<Room, "clientId" | "name"> & { roomTypeId: string; floorArea?: string }) => request<Room>(`/api/homes/${homeId}/rooms`, { method: "POST", headers: { "Idempotency-Key": room.clientId }, body: json({ ...room, inspectionId }) }),
  updateRoom: (roomId: string, value: Partial<Room>, key: string) => request<Room>(`/api/rooms/${roomId}`, { method: "PATCH", headers: { "Idempotency-Key": key }, body: json(value) }),
  archiveRoom: (roomId: string, key: string) => request<void>(`/api/rooms/${roomId}`, { method: "DELETE", headers: { "Idempotency-Key": key } }),
  createAsset: (roomId: string, inspectionId: string, asset: Pick<Asset, "clientId" | "type" | "name" | "locationDetail">) => request<Asset>(`/api/rooms/${roomId}/assets`, { method: "POST", headers: { "Idempotency-Key": asset.clientId }, body: json({ ...asset, inspectionId }) }),
  updateAsset: (assetId: string, value: Partial<Asset>, key: string) => request<Asset>(`/api/assets/${assetId}`, { method: "PATCH", headers: { "Idempotency-Key": key }, body: json(value) }),
  completeInspection: (inspectionId: string, key: string) => request<Inspection>(`/api/inspections/${inspectionId}/complete`, { method: "POST", headers: { "Idempotency-Key": key } }),
};

export function agentSocketUrl(token: string) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}/ws?token=${encodeURIComponent(token)}`;
}
