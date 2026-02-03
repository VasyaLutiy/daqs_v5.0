from typing import Dict, Callable, Any, Optional
import logging

logger = logging.getLogger("master.hooks")

# The global registry of dialogue hooks
# Format: { "hook_name": function }
DIALOGUE_HOOKS: Dict[str, Callable] = {}

def register_hook(name: str):
    """Decorator to register a function as a dialogue hook."""
    def decorator(func: Callable):
        DIALOGUE_HOOKS[name] = func
        logger.info(f"Registered dialogue hook: '{name}'")
        return func
    return decorator

def execute_hook(name: str, *args, **kwargs) -> Any:
    """Executes a registered hook by name."""
    if name in DIALOGUE_HOOKS:
        return DIALOGUE_HOOKS[name](*args, **kwargs)
    else:
        logger.warning(f"Attempted to execute unknown hook: '{name}'")
        return None
