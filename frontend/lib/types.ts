export type InventoryItems = Record<string, number>;

export interface PlayerSnapshot {
  id: string;
  session_id?: string | null;
  location: string;
  inventory: {
    items: InventoryItems;
  };
  knowledge: {
    discovered_locations: string[];
    visited_locations: string[];
    known_npcs?: string[];
    known_facts?: string[];
  };
  history?: {
    defeated_enemies?: string[];
    avoided_enemies?: string[];
    talked_to?: string[];
  };
  goal?: string | null;
}

export interface WorldLocation {
  id: string;
  name: string;
  description: string;
}

export interface WorldNpc {
  id: string;
  name: string;
  description?: string;
  personality?: string;
  speech_style?: string;
  dialogue_quest?: boolean;
  social_persona?: string;
}

export interface WorldExit {
  id: string;
  name: string;
}

export interface WorldItem {
  id: string;
  name: string;
  description?: string;
  is_goal_item?: boolean;
}

export interface WorldPortal {
  id: string;
  name: string;
  target_location_id: string;
  target_location_name: string;
  requires_item?: string | null;
  is_available: boolean;
  blocked_reason?: string | null;
}

export interface AvailableQuest {
  id: string;
  name: string;
  goal: string;
}

export interface WorldSnapshot {
  location: WorldLocation;
  npcs_nearby: WorldNpc[];
  exits: WorldExit[];
  portals_nearby?: WorldPortal[];
  items_nearby: WorldItem[];
  available_quests: AvailableQuest[];
  image_path?: string | null;
}

export interface ActiveSocialSession {
  social_session_id: string;
  persona_id: string;
  social_state: Record<string, unknown>;
  history: Array<Record<string, unknown>>;
  image_path?: string | null;
  reply?: unknown;
}

export interface ActiveQuest {
  name: string;
  goal: string;
  plan: string[];
  quest_steps: Array<Record<string, unknown>>;
  payload?: Record<string, unknown> | null;
  accepted_at: string;
}

export interface QuestJournalEntry {
  id: string;
  quest_goal: string;
  quest_name: string;
  status: string;
  first_seen_at: string;
  updated_at: string;
  previewed_at?: string | null;
  accepted_at?: string | null;
  plan: string[];
  quest_steps: Array<Record<string, unknown>>;
  payload?: Record<string, unknown> | null;
}

export interface QuestJournalEvent {
  id: string;
  timestamp: string;
  type: string;
  summary: string;
  quest_goal?: string | null;
  quest_name?: string | null;
  details?: Record<string, unknown>;
}

export interface QuestJournalSnapshot {
  entries: QuestJournalEntry[];
  history: QuestJournalEvent[];
}

export interface GameSessionSnapshotResponse {
  status: string;
  game_session_id: string;
  player_snapshot: PlayerSnapshot;
  world_snapshot: WorldSnapshot;
  active_social_session?: ActiveSocialSession | null;
  active_quest?: ActiveQuest | null;
  quest_journal: QuestJournalSnapshot;
  ui_context: {
    mode: "world" | "social" | string;
  };
  metadata: Record<string, unknown>;
}

export interface GameSessionCreateResponse {
  status: string;
  game_session_id: string;
  player_id: string;
  created_at: string;
  expires_at?: string | null;
  player_snapshot: PlayerSnapshot;
  world_snapshot: WorldSnapshot;
  active_social_session?: ActiveSocialSession | null;
  active_quest?: ActiveQuest | null;
  quest_journal: QuestJournalSnapshot;
  ui_context: {
    mode: "world" | "social" | string;
  };
}

export interface GameQuestPreviewResponse {
  status: string;
  game_session_id: string;
  quest_goal: string;
  quest_name: string;
  plan: string[];
  quest: Array<Record<string, unknown>>;
  payload?: Record<string, unknown> | null;
  error?: string | null;
  active_quest?: ActiveQuest | null;
  quest_journal: QuestJournalSnapshot;
}
