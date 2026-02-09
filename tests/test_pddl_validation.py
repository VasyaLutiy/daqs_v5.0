import sys
from pathlib import Path
import types
import pytest


class _DummyFormatter:
    def __init__(self, *args, **kwargs):
        pass

    def format(self, record):
        return record.getMessage()


sys.modules.setdefault(
    "coloredlogs",
    types.SimpleNamespace(
        install=lambda *args, **kwargs: None,
        ColoredFormatter=_DummyFormatter,
    ),
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    from npc_engine.engine.master.planner_libs import (
        validate_problem_predicates,
        validate_problem_types,
    )
except ModuleNotFoundError as e:  # pragma: no cover
    pytest.skip(f"Dependency missing for import: {e}", allow_module_level=True)


def test_validation_accepts_known_predicates():
    domain = """
    (define (domain d)
      (:predicates
        (at ?x)
        (foo)
      )
    )
    """
    problem = """
    (define (problem p)
      (:domain d)
      (:objects a)
      (:init (at a))
      (:goal (foo))
    )
    """
    assert validate_problem_predicates(domain, problem) is None


def test_validation_rejects_unknown_predicates():
    domain = """
    (define (domain d)
      (:predicates (at ?x))
    )
    """
    problem = """
    (define (problem p)
      (:domain d)
      (:objects a)
      (:init (at a) (unknown a))
      (:goal (at a))
    )
    """
    err = validate_problem_predicates(domain, problem)
    assert err is not None
    assert "unknown" in err.lower()


def test_validation_rejects_unknown_types():
    domain = """
    (define (domain d)
      (:types agent location)
      (:predicates (at ?a - agent ?l - location))
    )
    """
    problem = """
    (define (problem p)
      (:domain d)
      (:objects hero - agent room - place)
      (:init (at hero room))
      (:goal (at hero room))
    )
    """
    err = validate_problem_types(domain, problem)
    assert err is not None
    assert "types" in err.lower()
