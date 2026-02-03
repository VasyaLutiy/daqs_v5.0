"""
Cache Manager for DAQS Game Engine

Handles loading, caching, and management of YAML configuration files
for personas, contexts, triggers, and world maps.
"""

from npc_engine.engine.logging_config import get_logger
from pathlib import Path
from typing import Dict, Any
import yaml

logger = get_logger("gamemaster.cache")


class CacheManager:
    """
    Manages configuration caching for the game engine.

    Loads and caches all YAML configurations from the social world
    and physical world directories. Supports both new atlas format
    and legacy individual files.

    Attributes:
        config_dir (Path): Base configuration directory
        cache (Dict[str, Dict]): Cached configuration data
    """

    def __init__(self, config_dir: Path):
        """
        Initialize cache manager with configuration directory.

        Args:
            config_dir (Path): Path to configuration root directory
        """
        self.config_dir = config_dir
        self.cache = self._load_cache()
        logger.info("CacheManager: Initialized and cache loaded.")

    def reload(self):
        """Force reload of all configuration caches."""
        self.cache = self._load_cache()
        logger.info("CacheManager: Cache reloaded.")

    def _load_cache(self) -> Dict[str, Dict]:
        """
        Load all YAML configurations into memory cache.

        Processes both new persona atlas format and legacy individual files.
        Handles contexts, personas, triggers, and world maps.

        Returns:
            Dict[str, Dict]: Nested cache structure containing all configs

        Cache Structure:
            {
                "contexts": {context_id: context_data},
                "personas": {persona_id: persona_data},
                "triggers": {trigger_id: trigger_data},
                "world_map": {location_id: location_data}
            }
        """
        cache = {"contexts": {}, "personas": {}, "triggers": {}, "world_map": {}}

        # 1. Load from persona atlases (new format)
        self._load_persona_atlases(cache)

        # 2. Load legacy individual files
        self._load_legacy_contexts(cache)
        self._load_legacy_triggers(cache)

        # 3. Load physical world maps
        self._load_world_maps(cache)

        return cache

    def _load_persona_atlases(self, cache: Dict[str, Dict]):
        """
        Load persona atlas files (new format with nested definitions).

        Args:
            cache (Dict[str, Dict]): Cache to populate
        """
        p_dir = self.config_dir / "social_world" / "nodes" / "personas"
        if not p_dir.exists():
            return

        for f in p_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text())

                if data.get('type') == 'persona_group':
                    # Extract from atlas format
                    self._extract_atlas_data(cache, data)
                else:
                    # Legacy single persona file
                    self._extract_legacy_persona(cache, f.stem, data)

            except Exception as e:
                logger.error(f"Error loading persona atlas {f.name}: {e}")

    def _extract_atlas_data(self, cache: Dict[str, Dict], atlas_data: Dict[str, Any]):
        """
        Extract contexts, personas, and triggers from atlas format.

        Args:
            cache (Dict[str, Dict]): Cache to populate
            atlas_data (Dict[str, Any]): Atlas data from YAML
        """
        for persona in atlas_data.get('personas', []):
            # Extract persona
            cache["personas"][persona['id']] = persona

            # Extract nested contexts
            for context in persona.get('contexts', []):
                cache["contexts"][context['id']] = context

            # Extract nested triggers
            for trigger in persona.get('triggers', []):
                cache["triggers"][trigger['id']] = trigger

    def _extract_legacy_persona(self, cache: Dict[str, Dict], persona_id: str, data: Dict[str, Any]):
        """
        Extract data from legacy single persona format.

        Args:
            cache (Dict[str, Dict]): Cache to populate
            persona_id (str): Persona identifier
            data (Dict[str, Any]): Persona data
        """
        cache["personas"][persona_id] = data

        # Extract contexts and triggers from legacy format
        for context in data.get("contexts", []):
            cache["contexts"][context['id']] = context

        for trigger in data.get("triggers", []):
            cache["triggers"][trigger['id']] = trigger

    def _load_legacy_contexts(self, cache: Dict[str, Dict]):
        """
        Load legacy context files from separate directory.

        Args:
            cache (Dict[str, Dict]): Cache to populate
        """
        ctx_dir = self.config_dir / "social_world" / "nodes" / "contexts"
        if not ctx_dir.exists():
            return

        for f in ctx_dir.glob("*.yaml"):
            try:
                cache["contexts"][f.stem] = yaml.safe_load(f.read_text())
            except Exception as e:
                logger.error(f"Error loading context {f.name}: {e}")

    def _load_legacy_triggers(self, cache: Dict[str, Dict]):
        """
        Load legacy trigger files from separate directory.

        Args:
            cache (Dict[str, Dict]): Cache to populate
        """
        t_dir = self.config_dir / "nodes" / "triggers"
        if not t_dir.exists():
            return

        for f in t_dir.glob("*.yaml"):
            try:
                cache["triggers"][f.stem] = yaml.safe_load(f.read_text())
            except Exception as e:
                logger.error(f"Error loading trigger {f.name}: {e}")

    def _load_world_maps(self, cache: Dict[str, Dict]):
        """
        Load physical world map data from regional atlases.

        Args:
            cache (Dict[str, Dict]): Cache to populate
        """
        reg_dir = Path("npc_engine/config/world/nodes/regions")
        if not reg_dir.exists():
            return

        for f in reg_dir.glob("*.yaml"):
            try:
                reg_data = yaml.safe_load(f.read_text())
                if reg_data and "locations" in reg_data:
                    for loc in reg_data["locations"]:
                        if "id" in loc:
                            cache["world_map"][loc["id"]] = loc
            except Exception as e:
                logger.error(f"Error loading regional atlas {f.name}: {e}")

    def get_context(self, context_id: str) -> Dict[str, Any]:
        """
        Get context data by ID.

        Args:
            context_id (str): Context identifier

        Returns:
            Dict[str, Any]: Context data or empty dict if not found
        """
        return self.cache["contexts"].get(context_id, {})

    def get_persona(self, persona_id: str) -> Dict[str, Any]:
        """
        Get persona data by ID.

        Args:
            persona_id (str): Persona identifier

        Returns:
            Dict[str, Any]: Persona data or empty dict if not found
        """
        return self.cache["personas"].get(persona_id, {})

    def get_trigger(self, trigger_id: str) -> Dict[str, Any]:
        """
        Get trigger data by ID.

        Args:
            trigger_id (str): Trigger identifier

        Returns:
            Dict[str, Any]: Trigger data or empty dict if not found
        """
        return self.cache["triggers"].get(trigger_id, {})

    def get_world_location(self, location_id: str) -> Dict[str, Any]:
        """
        Get world location data by ID.

        Args:
            location_id (str): Location identifier

        Returns:
            Dict[str, Any]: Location data or empty dict if not found
        """
        return self.cache["world_map"].get(location_id, {})