"""PDDL domain/problem pair validator.

Provides a single entry-point ``validate_domain_problem_pair`` that runs all
structural checks before a domain+problem pair is handed to the planner.

Checks
------
1. Domain name match   – (:domain X) in problem must equal (domain X) in domain.
2. Unknown predicates  – every predicate in :init / :goal must be declared.
3. Unknown types       – every type in :objects must appear in :types.
4. Duplicate init facts – duplicate facts in :init waste tokens and confuse some
                          planners (Fast-Downward warns; some silently deduplicate).

The module intentionally has no imports from the rest of the engine so it can
be used standalone in tests and external tools.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_domain_problem_pair(domain_pddl: str, problem_pddl: str) -> list[str]:
    """Run all structural checks on a domain+problem pair.

    Returns a list of error/warning strings.  Empty list → valid.
    """
    errors: list[str] = []

    err = check_domain_name_match(domain_pddl, problem_pddl)
    if err:
        errors.append(err)

    err = check_unknown_predicates(domain_pddl, problem_pddl)
    if err:
        errors.append(err)

    err = check_unknown_types(domain_pddl, problem_pddl)
    if err:
        errors.append(err)

    dupes = find_duplicate_init_facts(problem_pddl)
    if dupes:
        errors.append(f"Duplicate facts in :init: {sorted(dupes)}")

    return errors


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_domain_name_match(domain_pddl: str, problem_pddl: str) -> Optional[str]:
    """Return error string if (:domain ...) in problem differs from domain name."""
    domain_name = _extract_domain_name(domain_pddl)
    problem_ref = _extract_problem_domain_ref(problem_pddl)

    if domain_name is None:
        return "Domain file missing (domain <name>) declaration."
    if problem_ref is None:
        return "Problem file missing (:domain <name>) declaration."
    if domain_name != problem_ref:
        return (
            f"Domain name mismatch: domain declares '{domain_name}' "
            f"but problem references '{problem_ref}'."
        )
    return None


def check_unknown_predicates(domain_pddl: str, problem_pddl: str) -> Optional[str]:
    """Return error string if :init/:goal use predicates not in :predicates."""
    declared = _extract_declared_predicates(domain_pddl)
    if not declared:
        return None  # can't validate without predicate list

    ignore = {"and", "not", "or", "forall", "exists", "imply", "when"}
    unknown: set[str] = set()

    for block_re in (r"\(:init(.*?)(?=\s*\(:goal|\s*\)$)", r"\(:goal(.*?)\)\s*\)"):
        m = re.search(block_re, problem_pddl, re.DOTALL)
        if m:
            for pred in re.findall(r"\(\s*([\w-]+)", m.group(1)):
                if pred not in ignore and pred not in declared:
                    unknown.add(pred)

    if unknown:
        return f"Unknown predicates in problem: {sorted(unknown)}"
    return None


def check_unknown_types(domain_pddl: str, problem_pddl: str) -> Optional[str]:
    """Return error string if :objects use types not declared in :types."""
    domain_types = _extract_domain_types(domain_pddl)
    if not domain_types:
        return None

    obj_block = re.search(r"\(:objects(.*?)\)", problem_pddl, re.DOTALL)
    if not obj_block:
        return None

    unknown: set[str] = set()
    # Capture both the identifier and its type (identifier - type)
    for _name, typ in re.findall(r"([\w-]+)\s*-\s*([\w-]+)", obj_block.group(1)):
        if typ not in domain_types:
            unknown.add(typ)

    if unknown:
        return f"Unknown types in :objects: {sorted(unknown)}"
    return None


def find_duplicate_init_facts(problem_pddl: str) -> set[str]:
    """Return set of fact strings that appear more than once in :init."""
    init_match = re.search(r"\(:init(.*?)\)\s*\(:goal", problem_pddl, re.DOTALL)
    if not init_match:
        # Fallback: grab everything between :init and the last closing paren group
        init_match = re.search(r"\(:init(.*)", problem_pddl, re.DOTALL)
    if not init_match:
        return set()

    # Extract individual facts — each is a balanced-paren expression
    raw = init_match.group(1)
    facts: list[str] = _extract_top_level_facts(raw)

    seen: set[str] = set()
    dupes: set[str] = set()
    for f in facts:
        norm = _normalize_fact(f)
        if norm in seen:
            dupes.add(norm)
        seen.add(norm)
    return dupes


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_domain_name(domain_pddl: str) -> Optional[str]:
    """Extract name from ``(define (domain NAME) ...)``."""
    m = re.search(r"\(\s*define\s+\(\s*domain\s+([\w-]+)\s*\)", domain_pddl)
    return m.group(1) if m else None


def _extract_problem_domain_ref(problem_pddl: str) -> Optional[str]:
    """Extract name from ``(:domain NAME)`` in problem."""
    m = re.search(r"\(:domain\s+([\w-]+)\s*\)", problem_pddl)
    return m.group(1) if m else None


def _extract_declared_predicates(domain_pddl: str) -> set[str]:
    """Parse :predicates block and return declared predicate names."""
    start = domain_pddl.find("(:predicates")
    if start == -1:
        return set()

    # Walk balanced parens to find end of :predicates block
    depth = 0
    end = -1
    for i in range(start, len(domain_pddl)):
        if domain_pddl[i] == "(":
            depth += 1
        elif domain_pddl[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return set()

    block = domain_pddl[start : end + 1]
    names: set[str] = set()
    for m in re.finditer(r"\(\s*([\w-]+)", block):
        name = m.group(1)
        if name not in (":predicates",):
            names.add(name)
    return names


def _extract_domain_types(domain_pddl: str) -> set[str]:
    """Parse :types block and return all declared type names (including 'object').

    Handles both multi-line blocks (closing ')' on its own line) and
    compact single-line blocks like ``(:types agent context trigger)``.
    """
    m = re.search(r"\(:types(.*?)\)", domain_pddl, re.DOTALL)
    if not m:
        return set()

    types: set[str] = {"object"}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        left = line.split("-", 1)[0]
        for tok in left.split():
            if tok:
                types.add(tok)
    return types


def _extract_top_level_facts(raw: str) -> list[str]:
    """Extract top-level parenthesised expressions from raw :init content."""
    facts: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(raw):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start != -1:
                facts.append(raw[start : i + 1])
                start = -1
    return facts


def _normalize_fact(fact: str) -> str:
    """Collapse whitespace for comparison."""
    return " ".join(fact.split())
