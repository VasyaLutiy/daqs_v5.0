import {
  GameQuestPreviewResponse,
  GameSessionCreateResponse,
  GameSessionSnapshotResponse,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8001";

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
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<T>(response);
}

async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
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
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
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
