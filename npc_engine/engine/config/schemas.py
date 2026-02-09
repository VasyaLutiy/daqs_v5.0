from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ContextConnection(BaseModel):
    to: str
    direction: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ContextConfig(BaseModel):
    id: str
    connections: List[ContextConnection] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ConceptConfig(BaseModel):
    id: str
    properties: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class TriggerConfig(BaseModel):
    id: str
    parent_context: Optional[str] = None
    yields: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class TraitConfig(BaseModel):
    id: str
    model_config = ConfigDict(extra="allow")


class SecretConfig(BaseModel):
    id: str
    requires_item: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class EquipmentItem(BaseModel):
    id: str
    pddl_tags: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class BehaviorRule(BaseModel):
    id: str
    mood: Optional[str] = None
    requires_holding_tag: Optional[str] = None
    requires_wearing_tag: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class PersonaConfig(BaseModel):
    id: str
    contexts: List[ContextConfig] = Field(default_factory=list)
    concepts: List[ConceptConfig] = Field(default_factory=list)
    triggers: List[TriggerConfig] = Field(default_factory=list)
    traits: List[TraitConfig] = Field(default_factory=list)
    secrets: List[SecretConfig] = Field(default_factory=list)
    equipment: Dict[str, List[EquipmentItem]] = Field(default_factory=dict)
    behavior_rules: List[BehaviorRule] = Field(default_factory=list)
    world_overrides: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


def validate_persona_payload(payload: Dict[str, Any], logger) -> Optional[Dict[str, Any]]:
    """
    Validates a persona or atlas payload using pydantic.
    Returns a sanitized dict or None on validation errors.
    """
    if not payload:
        return None

    try:
        if "personas" in payload and isinstance(payload["personas"], list):
            personas = [PersonaConfig.model_validate(p) for p in payload["personas"] if isinstance(p, dict)]
            payload["personas"] = [p.model_dump() for p in personas]
            return payload
        if "id" in payload:
            persona = PersonaConfig.model_validate(payload)
            return persona.model_dump()
        return payload
    except ValidationError as e:
        logger.error(f"Validation error in persona payload: {e}")
        return None
