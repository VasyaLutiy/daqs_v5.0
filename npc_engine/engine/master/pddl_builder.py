"""Jinja-based renderer for PDDL templates with shared search paths."""

from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

import jinja2


class PDDLTemplateRenderer:
    """Centralized Jinja renderer for PDDL templates."""

    def __init__(self, search_paths: Iterable[Path]):
        self.loader_paths: Sequence[Path] = list(search_paths)
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.loader_paths),
            autoescape=False,
            keep_trailing_newline=True,
        )

    def render(self, template_path: str, context: Dict[str, Any]) -> str:
        template = self.env.get_template(template_path)
        return template.render(**context)
