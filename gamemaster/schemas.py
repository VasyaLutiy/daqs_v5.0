from pydantic import BaseModel, Field, conlist
from typing import Optional, Dict, List, Literal

class InventoryChange(BaseModel):
    item_id: str = Field(..., description="ID предмета.")
    action: Literal["add", "remove"] = Field(..., description="Действие: 'add' (добавить) или 'remove' (удалить).")
    quantity: int = Field(1, description="Количество предметов. По умолчанию 1.")

class KnowledgeChanges(BaseModel):
    add_discovered_locations: Optional[List[str]] = Field(None, description="Список ID локаций, которые стали известны игроку.")
    remove_discovered_locations: Optional[List[str]] = Field(None, description="Список ID локаций, которые больше не известны игроку.")
    add_known_npcs: Optional[List[str]] = Field(None, description="Список ID NPC, с которыми игрок познакомился.")
    remove_known_npcs: Optional[List[str]] = Field(None, description="Список ID NPC, с которыми игрок больше не знаком.")
    # Можно добавить другие типы знаний, например, про квесты, способности и т.д.

class PlayerIntent(BaseModel):
    """
    Представляет собой структурированное намерение игрока, извлеченное LLM из его сообщения.
    Используется для обновления PlayerState и запуска PDDL-планировщика.
    """
    summary: str = Field(..., description="Краткое описание намерения игрока в свободной форме.")
    player_id: str = Field(..., description="ID игрока, чье состояние должно быть обновлено.")
    
    new_location: Optional[str] = Field(None, description="ID локации, куда игрок хочет переместиться.")
    new_goal_pddl: Optional[str] = Field(None, description="Новая цель игрока в формате PDDL (например, '(has-item player_001 ancient_artifact)').")
    
    inventory_changes: Optional[conlist(InventoryChange, min_length=1)] = Field(None, description="Изменения в инвентаре игрока.")
    knowledge_changes: Optional[KnowledgeChanges] = Field(None, description="Изменения в знаниях игрока (открытые локации, известные NPC и т.д.).")

    direct_response: Optional[str] = Field(None, description="Текст прямого ответа игроку, если LLM считает, что не требуется взаимодействие с PDDL Engine (например, простой вопрос/ответ).")

    # Дополнительные поля могут быть добавлены по мере развития:
    # new_ability: Optional[str] = Field(None, description="Название способности, которую игрок хочет приобрести.")
    # interact_with_npc: Optional[str] = Field(None, description="ID NPC, с которым игрок хочет взаимодействовать.")
    # use_item: Optional[str] = Field(None, description="ID предмета, который игрок хочет использовать.")


class DialogueIntent(BaseModel):
    # ... (deprecated or keep for legacy compatibility, but we focus on Extraction now)
    summary: str

class DialogueExtraction(BaseModel):
    """
    Результат анализа реплики игрока LLM.
    Содержит намерение, извлеченные факты (способности) и мета-информацию.
    """
    intent: Literal["answer", "question", "statement", "clarification", "off_topic", "goodbye"] = Field("statement", description="Тип намерения игрока.")
    
    abilities_confirmed: List[str] = Field(default_factory=list, description="Список ID способностей, которыми игрок ТОЧНО владеет (confirmed).")
    abilities_denied: List[str] = Field(default_factory=list, description="Список ID способностей, которыми игрок ТОЧНО НЕ владеет.")
    abilities_mentioned: List[str] = Field(default_factory=list, description="Список ID способностей, которые просто упомянуты.")
    
    confidence: float = Field(1.0, description="Уверенность в извлечении (0.0 - 1.0).")
    
    needs_clarification: bool = Field(False, description="Требуется ли уточнение у игрока.")
    clarification_reason: Optional[str] = Field(None, description="Причина, если требуется уточнение.")
    
    sentiment: Literal["positive", "negative", "neutral", "confused"] = Field("neutral", description="Эмоциональный окрас ответа.")
    
    raw_abilities: List[str] = Field(default_factory=list, description="Как игрок описал свои навыки своими словами.")

