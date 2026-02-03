import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

class QuestGenerator:
    """
    Generates human-readable quest steps from PDDL planner output.

    This class transforms a sequence of PDDL actions into structured quest steps for NPCs,
    using a configuration-driven approach to parse actions and generate descriptions.
    It loads action definitions from a YAML config file to avoid hardcoding.

    Attributes:
        action_config (Dict[str, Dict]): Loaded configuration for actions, including parameters
            and description templates. Loaded from `config/actions/quest_actions.yaml` by default.

    Methods:
        generate_quest: Main method to convert a plan into quest steps.
        _parse_action: Parses a single PDDL action string into a dictionary.
        _generate_description: Creates a human-readable description for a quest step.

    Example:
        >>> generator = QuestGenerator()
        >>> plan = ["move player loc1 loc2", "pickup player item loc2"]
        >>> quest = generator.generate_quest(plan, {})
        >>> quest[0]["description"]
        'Переместиться из loc1 в loc2'
    """
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            # Resolve relative to the project root (assuming engine/master/../../config)
            base_dir = Path(__file__).resolve().parent.parent.parent
            config_path = base_dir / "config/actions/quest_actions.yaml"
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self.action_config = yaml.safe_load(f)["actions"]

    def generate_quest(self, plan: List[str]) -> List[Dict[str, Any]]:
        """Generate quest steps from plan."""
        quest_steps = []
        for i, action in enumerate(plan):
            step = self._parse_action(action)
            step["step_number"] = i + 1
            step["description"] = self._generate_description(step)
            quest_steps.append(step)
        return quest_steps

    def _parse_action(self, action: str) -> Dict[str, Any]:
        parts = action.strip("()").split()
        action_type = parts[0]
        if action_type in self.action_config:
            config = self.action_config[action_type]
            params = config["params"]
            if len(parts) - 1 == len(params):
                return {"action": action_type, **dict(zip(params, parts[1:]))}
        return {"action": action_type, "raw": action}

    def _generate_description(self, step: Dict[str, Any]) -> str:
        action = step["action"]
        if action in self.action_config:
            desc = self.action_config[action]["description"]
            return desc.format(**{k: v for k, v in step.items() if k != "action"})
        return f"Выполнить действие: {step.get('raw', action)}"