import {
  GameQuestPreviewResponse,
  GameSessionCreateResponse,
  GameSessionSnapshotResponse,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8001";
const REQUEST_TIMEOUT_MS = 15000;

function timeoutMessage() {
  return `Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s. Check API reachability and NEXT_PUBLIC_API_BASE.`;
}

async function fetchWithTimeout(input: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error && typeof error === "object" && "name" in error && error.name === "AbortError") {
      throw new Error(timeoutMessage());
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // ignore secondary parse errors
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetchWithTimeout(`${API_BASE}${path}`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<T>(response);
}

async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetchWithTimeout(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  return parseJson<T>(response);
}

export function assetUrl(path?: string | null): string | null {
  if (!path) {
    return null;
  }
  // Backend may return absolute filesystem paths (e.g. /home/.../static/images/...).
  // Normalize those to public static URL paths.
  const normalized = path.replace(/\\/g, "/");
  const staticMarkerIndex = normalized.indexOf("/static/");
  if (staticMarkerIndex >= 0) {
    return `${API_BASE}${normalized.slice(staticMarkerIndex)}`;
  }
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${API_BASE}${normalized.startsWith("/") ? normalized : `/${normalized}`}`;
}

export async function createGameSession(): Promise<GameSessionCreateResponse> {
  return apiPost<GameSessionCreateResponse>("/game/sessions");
}

export async function getGameSession(
  gameSessionId: string,
): Promise<GameSessionSnapshotResponse> {
  return apiGet<GameSessionSnapshotResponse>(`/game/sessions/${gameSessionId}`);
}

export async function moveGameWorld(
  gameSessionId: string,
  targetLocationId: string,
): Promise<GameSessionSnapshotResponse> {
  return apiPost<GameSessionSnapshotResponse>(
    `/game/sessions/${gameSessionId}/world/move`,
    { target_location_id: targetLocationId },
  );
}

export async function pickupGameItem(
  gameSessionId: string,
  itemId: string,
): Promise<GameSessionSnapshotResponse> {
  return apiPost<GameSessionSnapshotResponse>(
    `/game/sessions/${gameSessionId}/world/pickup`,
    { item_id: itemId },
  );
}

export async function teleportGameWorld(
  gameSessionId: string,
  portalId: string,
  targetLocationId?: string,
): Promise<GameSessionSnapshotResponse> {
  return apiPost<GameSessionSnapshotResponse>(
    `/game/sessions/${gameSessionId}/world/teleport`,
    {
      portal_id: portalId,
      target_location_id: targetLocationId,
    },
  );
}

export async function generateWorldImage(
  locationId: string,
): Promise<{ image_path?: string | null }> {
  return apiPost<{ image_path?: string | null }>(
    "/world/image",
    { location_id: locationId },
  );
}

export async function previewQuest(
  gameSessionId: string,
  questGoal: string,
  questName: string,
): Promise<GameQuestPreviewResponse> {
  return apiPost<GameQuestPreviewResponse>(
    `/game/sessions/${gameSessionId}/quests/preview`,
    { quest_goal: questGoal, quest_name: questName, oracle_mode: true },
  );
}

export async function acceptQuest(
  gameSessionId: string,
  questGoal: string,
  questName: string,
): Promise<GameSessionSnapshotResponse> {
  return apiPost<GameSessionSnapshotResponse>(
    `/game/sessions/${gameSessionId}/quests/accept`,
    { quest_goal: questGoal, quest_name: questName, oracle_mode: true },
  );
}

export async function initSocial(
  gameSessionId: string,
  personaId: string,
  canQuest: boolean,
): Promise<GameSessionSnapshotResponse> {
  return apiPost<GameSessionSnapshotResponse>(
    `/game/sessions/${gameSessionId}/social/init`,
    { persona_id: personaId, can_quest: canQuest },
  );
}

export async function sendSocialMessage(
  gameSessionId: string,
  socialSessionId: string,
  message: string,
  action?: string,
): Promise<GameSessionSnapshotResponse> {
  return apiPost<GameSessionSnapshotResponse>(
    `/game/sessions/${gameSessionId}/social/message`,
    {
      social_session_id: socialSessionId,
      message,
      action,
    },
  );
}

export async function exitSocial(
  gameSessionId: string,
  socialSessionId?: string,
): Promise<GameSessionSnapshotResponse> {
  return apiPost<GameSessionSnapshotResponse>(
    `/game/sessions/${gameSessionId}/social/exit`,
    { social_session_id: socialSessionId },
  );
}
