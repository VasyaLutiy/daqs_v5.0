"""Модели графа мира."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Union
from enum import Enum, auto
from collections import defaultdict
from pydantic import BaseModel, Field
from . import logger


# ============================================================
# ПЕРЕЧИСЛЕНИЯ
# ============================================================

class NodeType(str, Enum):
    """Типы узлов графа."""
    REGION = "region"
    LOCATION = "location"
    SUB_LOCATION = "sub_location"
    OBJECT = "object"
    ITEM = "item"
    NPC = "npc"


class EdgeType(str, Enum):
    """Типы связей."""
    PATH = "path"
    DOOR = "door"
    PORTAL = "portal" # <-- RESTORED
    CONTAINS = "contains"
    LEADS_TO = "leads_to"
    GUARDS = "guards"
    UNLOCKS = "unlocks"
    REQUIRES = "requires"


class NodeState(str, Enum):
    """Состояния узлов."""
    UNKNOWN = "unknown"       # Не обнаружен
    DISCOVERED = "discovered" # Обнаружен
    VISITED = "visited"       # Посещён
    COMPLETED = "completed"   # Завершён
    LOCKED = "locked"         # Заблокирован
    UNLOCKED = "unlocked"     # Разблокирован
    INTACT = "intact"         # Цел
    DESTROYED = "destroyed"   # Уничтожен


# ============================================================
# УСЛОВИЯ
# ============================================================

class ConditionType(str, Enum):
    """Типы условий."""
    HAS_ITEM = "has_item"
    HAS_ABILITY = "has_ability"
    ABILITY_LEVEL = "ability_level"
    DEFEATED = "defeated"
    AVOIDED = "avoided"
    DISCOVERED = "discovered"
    STATE = "state"
    OR = "OR"
    AND = "AND"


@dataclass
class Condition:
    """Условие для перехода/действия."""
    type: ConditionType
    target: str
    value: Any = None
    sub_conditions: List['Condition'] = field(default_factory=list)
    
    def to_pddl_precondition(self) -> str:
        """Конвертирует в PDDL предусловие."""
        if self.type == ConditionType.HAS_ITEM:
            return f"(has-item player {self.target})"
        elif self.type == ConditionType.HAS_ABILITY:
            return f"(has-ability player {self.target})"
        elif self.type == ConditionType.ABILITY_LEVEL:
            return f"(>= (ability-level player {self.target}) {self.value})"
        elif self.type == ConditionType.DEFEATED:
            return f"(defeated {self.target})"
        elif self.type == ConditionType.AVOIDED:
            return f"(avoided {self.target})"
        elif self.type == ConditionType.DISCOVERED:
            return f"(discovered {self.target})"
        elif self.type == ConditionType.STATE:
            obj, state = self.target.split(":")
            return f"(state-{state} {obj})"
        elif self.type == ConditionType.OR:
            subs = " ".join(c.to_pddl_precondition() for c in self.sub_conditions)
            return f"(or {subs})"
        elif self.type == ConditionType.AND:
            subs = " ".join(c.to_pddl_precondition() for c in self.sub_conditions)
            return f"(and {subs})"
        return ""
    
    @classmethod
    def from_yaml(cls, data: Union[str, dict]) -> 'Condition':
        """Парсит условие из YAML."""
        if isinstance(data, str):
            # Формат "has_item: torch" или "has_ability: stealth"
            if ":" in data:
                parts = data.split(":", 1)
                return cls(
                    type=ConditionType(parts[0].strip()),
                    target=parts[1].strip()
                )
            return cls(type=ConditionType.STATE, target=data)
        
        if isinstance(data, dict):
            if "OR" in data:
                return cls(
                    type=ConditionType.OR,
                    target="",
                    sub_conditions=[cls.from_yaml(c) for c in data["OR"]]
                )
            if "AND" in data:
                return cls(
                    type=ConditionType.AND,
                    target="",
                    sub_conditions=[cls.from_yaml(c) for c in data["AND"]]
                )
            
            # Одиночное условие как dict
            for key, value in data.items():
                return cls(
                    type=ConditionType(key),
                    target=str(value)
                )
        
        raise ValueError(f"Invalid condition format: {data}")


# ============================================================
# ВЗАИМОДЕЙСТВИЯ
# ============================================================

@dataclass
class Interaction:
    """Возможное взаимодействие с объектом."""
    action: str                             # examine, use, unlock, pickup...
    result: str                             # Результат действия
    conditions: List[Condition] = field(default_factory=list)
    target: Optional[str] = None            # Цель действия (для use X on Y)
    consumes_item: Optional[str] = None     # Расходует предмет
    grants_item: Optional[str] = None       # Даёт предмет
    changes_state: Optional[str] = None     # Меняет состояние


# ============================================================
# УЗЛЫ ГРАФА
# ============================================================

@dataclass
class WorldNode:
    """Базовый узел графа мира."""
    id: str
    type: NodeType
    name: str
    description: str
    properties: Dict[str, Any] = field(default_factory=dict)
    
    # Состояние (для player graph)
    state: NodeState = NodeState.UNKNOWN
    custom_states: Dict[str, str] = field(default_factory=dict)
    
    # Дочерние узлы
    children: Dict[str, 'WorldNode'] = field(default_factory=dict)
    
    # Связи
    connections: List['Edge'] = field(default_factory=list)
    
    # Взаимодействия (для объектов)
    interactions: List[Interaction] = field(default_factory=list)
    
    def get_pddl_type(self) -> str:
        """Возвращает PDDL тип."""
        type_map = {
            NodeType.REGION: "region",
            NodeType.LOCATION: "location",
            NodeType.SUB_LOCATION: "location",
            NodeType.OBJECT: "object",
            NodeType.ITEM: "item",
            NodeType.NPC: "npc",
        }
        return type_map.get(self.type, "object")


@dataclass
class LocationNode(WorldNode):
    """Узел локации."""
    objects: Dict[str, WorldNode] = field(default_factory=dict)
    items: Dict[str, ItemNode] = field(default_factory=dict)
    npcs: Dict[str, NPCNode] = field(default_factory=dict)
    
    # Для новой архитектуры
    region: Optional[str] = None
    contained_items: List[str] = field(default_factory=list)
    contained_objects: List[str] = field(default_factory=list)
    contained_npcs: List[str] = field(default_factory=list)
    
    # Свойства локации
    is_safe_zone: bool = False
    has_fast_travel: bool = False
    danger_level: str = "low"


@dataclass
class ItemNode(WorldNode):
    """Узел предмета."""
    pickable: bool = True
    consumable: bool = False
    quest_item: bool = False
    effect: Optional[str] = None
    used_for: Optional[str] = None


@dataclass
class NPCNode(WorldNode):
    """Узел NPC."""
    hostile: bool = False
    can_talk: bool = True
    can_be_avoided: bool = False
    avoid_condition: Optional[str] = None
    defeat_reward: Optional[str] = None
    dialogue_tree: Optional[str] = None  # ID дерева диалогов
    personality: Optional[str] = None
    speech_style: Optional[str] = None


# ============================================================
# СВЯЗИ
# ============================================================

@dataclass
class Edge:
    """Связь между узлами."""
    from_node: str
    to_node: str
    edge_type: EdgeType
    bidirectional: bool = False
    conditions: List[Condition] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict) # <-- RESTORED
    
    def to_pddl_action_precondition(self) -> str:
        """Генерирует предусловие для PDDL действия."""
        preconditions = [f"(at player {self.from_node})"]
        
        if self.edge_type == EdgeType.LEADS_TO:
            preconditions.append(f"(accessible {self.to_node})")
        
        for cond in self.conditions:
            preconditions.append(cond.to_pddl_precondition())
        
        return " ".join(preconditions)


# ============================================================
# ГЛАВНЫЙ ГРАФ
# ============================================================

@dataclass
class WorldGraph:
    """Полный граф мира."""
    
    world_id: str
    name: str
    description: str
    
    # Узлы по типам
    regions: Dict[str, WorldNode] = field(default_factory=dict)
    locations: Dict[str, LocationNode] = field(default_factory=dict)
    objects: Dict[str, WorldNode] = field(default_factory=dict)
    items: Dict[str, ItemNode] = field(default_factory=dict)
    npcs: Dict[str, NPCNode] = field(default_factory=dict)
    
    # Все узлы (flat index)
    all_nodes: Dict[str, WorldNode] = field(default_factory=dict)
    
    # Все связи
    edges: List[Edge] = field(default_factory=list)
    
    # Для новой архитектуры
    region_to_locations: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    
    # Квесты
    quest_chains: Dict[str, Any] = field(default_factory=dict)
    
    # Способности мира
    abilities: Dict[str, Any] = field(default_factory=dict)
    
    def get_node(self, node_id: str) -> Optional[WorldNode]:
        """Получает узел по ID."""
        return self.all_nodes.get(node_id)
    
    def get_connections_from(self, node_id: str) -> List[Edge]:
        """Получает все исходящие связи."""
        return [e for e in self.edges if e.from_node == node_id]
    
    def get_connections_to(self, node_id: str) -> List[Edge]:
        """Получает все входящие связи."""
        return [e for e in self.edges if e.to_node == node_id]
    
    def get_accessible_locations(
        self, 
        from_node: str, 
        player_state: 'PlayerState'
    ) -> List[str]:
        """Возвращает доступные локации с учётом состояния игрока."""
        accessible = []
        
        for edge in self.get_connections_from(from_node):
            if edge.edge_type in (EdgeType.PATH, EdgeType.LEADS_TO):
                if self._check_conditions(edge.conditions, player_state):
                    accessible.append(edge.to_node)
        
        return accessible
    
    def _check_conditions(
        self, 
        conditions: List[Condition], 
        player_state: 'PlayerState'
    ) -> bool:
        """Проверяет выполнение условий."""
        for cond in conditions:
            if not player_state.check_condition(cond):
                return False
        return True
    
    def get_all_pddl_types(self) -> Dict[str, List[str]]:
        """Собирает все типы для PDDL."""
        logger.debug(f"Collecting PDDL types for world '{self.name}' with {len(self.all_nodes)} nodes")
        
        types = {
            "region": [],
            "location": [],
            "object": [],
            "item": [],
            "npc": [],
        }
        
        for node_id, node in self.all_nodes.items():
            pddl_type = node.get_pddl_type()
            if pddl_type in types:
                types[pddl_type].append(node_id)
        
        # Log type counts
        total_objects = sum(len(obj_list) for obj_list in types.values())
        logger.debug(f"PDDL types collected: {total_objects} total objects")
        for type_name, obj_list in types.items():
            if obj_list:
                logger.debug(f"  {type_name}: {len(obj_list)} objects - {obj_list[:3]}{'...' if len(obj_list) > 3 else ''}")
        
        return types