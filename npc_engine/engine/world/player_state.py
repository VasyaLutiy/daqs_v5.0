"""Состояние игрока и его граф."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
import json
import time  # used for respawn scheduling

from .graph import (
    WorldGraph, WorldNode, NodeState, Condition, 
    ConditionType, LocationNode
)


@dataclass
class PlayerAbility:
    """Способность игрока."""
    id: str
    level: int = 1
    experience: int = 0


@dataclass
class PlayerInventory:
    """Инвентарь игрока."""
    items: Dict[str, int] = field(default_factory=dict)  # item_id -> количество
    capacity: int = 20
    
    def has_item(self, item_id: str, count: int = 1) -> bool:
        return self.items.get(item_id, 0) >= count
    
    def add_item(self, item_id: str, count: int = 1) -> bool:
        if self.current_size + count > self.capacity:
            return False
        self.items[item_id] = self.items.get(item_id, 0) + count
        return True
    
    def remove_item(self, item_id: str, count: int = 1) -> bool:
        if not self.has_item(item_id, count):
            return False
        self.items[item_id] -= count
        if self.items[item_id] <= 0:
            del self.items[item_id]
        return True
    
    @property
    def current_size(self) -> int:
        return sum(self.items.values())


@dataclass
class QuestProgress:
    """Прогресс квеста."""
    quest_id: str
    current_stage: str
    completed_stages: Set[str] = field(default_factory=set)
    started_at: datetime = field(default_factory=datetime.now)
    is_complete: bool = False


# ============================================================
# DIFF СОСТОЯНИЯ (для регенерации)
# ============================================================

@dataclass
class GraphDiff:
    """Изменения графа относительно базового."""
    
    # Изменения состояний узлов
    node_states: Dict[str, NodeState] = field(default_factory=dict)
    
    # Кастомные состояния объектов
    object_states: Dict[str, Dict[str, str]] = field(default_factory=dict)
    
    # Разблокированные связи
    unlocked_edges: Set[str] = field(default_factory=set)  # "from:to"
    
    # Заблокированные связи (например, обвал)
    blocked_edges: Set[str] = field(default_factory=set)
    
    # Удалённые узлы (собранные предметы, побеждённые враги)
    removed_nodes: Set[str] = field(default_factory=set)
    
    # Добавленные узлы (спавн, квестовые)
    added_nodes: Dict[str, Dict] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Сериализация для хранения."""
        return {
            "node_states": {k: v.value for k, v in self.node_states.items()},
            "object_states": self.object_states,
            "unlocked_edges": list(self.unlocked_edges),
            "blocked_edges": list(self.blocked_edges),
            "removed_nodes": list(self.removed_nodes),
            "added_nodes": self.added_nodes,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GraphDiff':
        """Десериализация."""
        return cls(
            node_states={k: NodeState(v) for k, v in data.get("node_states", {}).items()},
            object_states=data.get("object_states", {}),
            unlocked_edges=set(data.get("unlocked_edges", [])),
            blocked_edges=set(data.get("blocked_edges", [])),
            removed_nodes=set(data.get("removed_nodes", [])),
            added_nodes=data.get("added_nodes", {}),
        )


# ============================================================
# СОСТОЯНИЕ ИГРОКА
# ============================================================

@dataclass
class PlayerState:
    """Полное состояние игрока."""
    
    # Идентификация
    player_id: str
    session_id: Optional[str] = None
    
    # Текущая позиция
    current_location: str = ""
    previous_location: Optional[str] = None
    
    # Способности
    abilities: Dict[str, PlayerAbility] = field(default_factory=dict)
    
    # Инвентарь
    inventory: PlayerInventory = field(default_factory=PlayerInventory)
    
    # Квесты
    active_quests: Dict[str, QuestProgress] = field(default_factory=dict)
    completed_quests: Set[str] = field(default_factory=set)
    
    # Знания об игрока о мире
    discovered_locations: Set[str] = field(default_factory=set)
    visited_locations: Set[str] = field(default_factory=set)
    known_npcs: Set[str] = field(default_factory=set)
    known_facts: Set[str] = field(default_factory=set) # Social concepts/facts
    
    # Взаимодействия
    defeated_enemies: Set[str] = field(default_factory=set)
    avoided_enemies: Set[str] = field(default_factory=set)
    talked_to: Set[str] = field(default_factory=set)
    
    # Diff для графа
    graph_diff: GraphDiff = field(default_factory=GraphDiff)

    # Respawn timers for per-player NPC respawns (npc_id -> epoch_seconds)
    respawn_timers: Dict[str, float] = field(default_factory=dict)
    
    # Метаданные
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    play_time_seconds: int = 0
    
    # ============================================================
    # ПРОВЕРКИ УСЛОВИЙ
    # ============================================================
    
    def check_condition(self, condition: Condition) -> bool:
        """Проверяет выполнение условия."""
        
        if condition.type == ConditionType.HAS_ITEM:
            return self.inventory.has_item(condition.target)
        
        elif condition.type == ConditionType.HAS_ABILITY:
            return condition.target in self.abilities
        
        elif condition.type == ConditionType.ABILITY_LEVEL:
            ability = self.abilities.get(condition.target)
            if not ability:
                return False
            return ability.level >= int(condition.value)
        
        elif condition.type == ConditionType.DEFEATED:
            return condition.target in self.defeated_enemies
        
        elif condition.type == ConditionType.AVOIDED:
            return condition.target in self.avoided_enemies
        
        elif condition.type == ConditionType.DISCOVERED:
            return condition.target in self.discovered_locations
        
        elif condition.type == ConditionType.STATE:
            obj_id, state = condition.target.split(":")
            obj_states = self.graph_diff.object_states.get(obj_id, {})
            return obj_states.get("state") == state
        
        elif condition.type == ConditionType.OR:
            return any(self.check_condition(c) for c in condition.sub_conditions)
        
        elif condition.type == ConditionType.AND:
            return all(self.check_condition(c) for c in condition.sub_conditions)
        
        return False
    
    # ============================================================
    # ИЗМЕНЕНИЕ СОСТОЯНИЯ
    # ============================================================
    
    def visit_location(self, location_id: str):
        """Посещает локацию."""
        self.previous_location = self.current_location
        self.current_location = location_id
        self.discovered_locations.add(location_id)
        self.visited_locations.add(location_id)
        self.graph_diff.node_states[location_id] = NodeState.VISITED
        self.last_activity = datetime.now()
    
    def pickup_item(self, item_id: str, count: int = 1) -> bool:
        """Подбирает предмет."""
        if self.inventory.add_item(item_id, count):
            self.graph_diff.removed_nodes.add(item_id)
            return True
        return False
    
    def use_item(self, item_id: str) -> bool:
        """Использует предмет."""
        return self.inventory.remove_item(item_id)
    
    def defeat_enemy(self, enemy_id: str, reward: Optional[str] = None, respawn_delay_seconds: Optional[int] = None, world: Optional['WorldGraph'] = None):
        """Побеждает врага.

        Optionally schedule a per-player respawn by providing `respawn_delay_seconds`.
        If `respawn_delay_seconds` is None and `world` is provided, this method will attempt to
        read respawn settings from the NPC node's `properties.respawn` configuration and schedule
        respawn accordingly (if enabled and per_player).
        """
        self.defeated_enemies.add(enemy_id)
        self.graph_diff.removed_nodes.add(enemy_id)
        if reward:
            self.inventory.add_item(reward)

        # Determine respawn delay from explicit argument or from world NPC config
        delay = respawn_delay_seconds
        if delay is None and world is not None and enemy_id in world.all_nodes:
            npc_node = world.all_nodes[enemy_id]
            props = getattr(npc_node, "properties", {}) or {}
            respawn_cfg = props.get("respawn", {})
            enabled = respawn_cfg.get("enabled", False)
            per_player = respawn_cfg.get("per_player", True)
            cfg_delay = respawn_cfg.get("delay_seconds") or respawn_cfg.get("ttl_seconds")
            # Only schedule if enabled and per_player (default true)
            if enabled and per_player and cfg_delay:
                try:
                    delay = int(cfg_delay)
                except Exception:
                    delay = None

        if delay is not None and delay > 0:
            # Schedule a respawn for this player
            self.schedule_respawn(enemy_id, delay)
    
    def avoid_enemy(self, enemy_id: str):
        """Избегает врага."""
        self.avoided_enemies.add(enemy_id)
    
    def unlock_path(self, from_node: str, to_node: str):
        """Разблокирует путь."""
        edge_key = f"{from_node}:{to_node}"
        self.graph_diff.unlocked_edges.add(edge_key)
    
    def set_object_state(self, object_id: str, state: str):
        """Устанавливает состояние объекта."""
        if object_id not in self.graph_diff.object_states:
            self.graph_diff.object_states[object_id] = {}
        self.graph_diff.object_states[object_id]["state"] = state
    
    def add_ability(self, ability_id: str, level: int = 1):
        """Добавляет способность."""
        self.abilities[ability_id] = PlayerAbility(id=ability_id, level=level)
    
    # ============================================================
    # КВЕСТЫ
    # ============================================================
    
    def start_quest(self, quest_id: str, first_stage: str):
        """Начинает квест."""
        self.active_quests[quest_id] = QuestProgress(
            quest_id=quest_id,
            current_stage=first_stage
        )

    # ============================================================
    # RESPAWN SCHEDULING
    # ============================================================

    def schedule_respawn(self, npc_id: str, delay_seconds: int):
        """Schedule a per-player respawn for an NPC.

        Stores the respawn epoch timestamp (UTC seconds since epoch) in `respawn_timers`.
        """
        respawn_at = time.time() + int(delay_seconds)
        self.respawn_timers[npc_id] = respawn_at
        # ensure npc is marked as removed/defeated now
        self.defeated_enemies.add(npc_id)
        self.graph_diff.removed_nodes.add(npc_id)

    def check_and_process_respawns(self, now: Optional[float] = None) -> list:
        """Process expired respawn timers and update player state.

        Returns a list of npc_ids that were respawned (i.e., timers expired and state updated).
        """
        if now is None:
            now = time.time()
        respawned = []
        expired = [nid for nid, ts in self.respawn_timers.items() if ts <= now]
        for nid in expired:
            # Remove respawn scheduling
            del self.respawn_timers[nid]
            # Remove from defeated/removed sets so regeneration will re-add the NPC
            if nid in self.defeated_enemies:
                self.defeated_enemies.remove(nid)
            if nid in self.graph_diff.removed_nodes:
                self.graph_diff.removed_nodes.remove(nid)
            respawned.append(nid)
        if respawned:
            # Update last activity/time if desired
            self.last_activity = datetime.now()
        return respawned
    
    def advance_quest(self, quest_id: str, next_stage: str):
        """Продвигает квест."""
        if quest_id in self.active_quests:
            progress = self.active_quests[quest_id]
            progress.completed_stages.add(progress.current_stage)
            progress.current_stage = next_stage
    
    def complete_quest(self, quest_id: str):
        """Завершает квест."""
        if quest_id in self.active_quests:
            del self.active_quests[quest_id]
            self.completed_quests.add(quest_id)