"""Lightweight bootstrap helpers to avoid import-time side effects."""

from npc_engine.engine.logging_config import logging_manager

_logging_initialized = False


def init_logging():
    """Initialize structured logging once."""
    global _logging_initialized
    if _logging_initialized:
        return
    logging_manager.setup_all_loggers()
    _logging_initialized = True
