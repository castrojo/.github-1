#!/usr/bin/env python3
"""Shared YAML loading and introspection for the workflow-validator scripts.

tuna-os/.github#275: ``reusable-ci-contract.yml`` and ``reusable-fork-safety.yml``
each embedded their own 140-160 line Python validator. Both loaded workflow YAML,
normalised the ``on:`` trigger block, walked ``uses:`` edges, and answered "is
this workflow reachable from an active trigger". That scaffolding was duplicated
word for word; this module is the single source of truth the two validators now
import.

The validators that use this are themselves invoked through composite actions
(``.github/actions/ci-contract-check`` and ``.github/actions/fork-safety-check``)
from *reusable* workflows, so they run inside the calling repository's checkout.
Every path here is therefore relative to ``$GITHUB_WORKSPACE`` (the caller's
repo), while the module file itself is reached through ``$GITHUB_ACTION_PATH``
from the hosting repo -- the same split ``ste-lint`` already relies on.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Set

import yaml

# Triggers that make a workflow "active" for reachability: something that can
# actually start it without a human reaching into the Actions UI.
ACTIVE_TRIGGERS = {"schedule", "push", "pull_request", "merge_group", "workflow_run", "release"}


def load_workflow(path: Path) -> dict:
    """Load a single workflow file, returning ``{}`` for an empty/blank file.

    Mirrors the original per-file loader: ``yaml.safe_load`` on the file's text,
    coalescing a ``None`` result (an empty document) to an empty dict so callers
    never have to guard against it.
    """
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_workflows(directory: Path) -> Dict[str, dict]:
    """Load every ``*.yml``/``*.yaml`` in ``directory``, indexed two ways.

    Each document is stored under both its ``{directory}/{name}`` key and its bare
    ``{name}`` key. The ci-contract validator names gate workflows by path in
    ``green-criteria.yml`` but only ever has the basename available on disk, so it
    falls back to ``workflows.get(wf) or workflows.get(wf_basename)`` -- this dual
    index makes that lookup work without a second glob.
    """
    docs: Dict[str, dict] = {}
    files: Iterable[Path] = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
    for f in files:
        doc = load_workflow(f)
        key = f"{directory}/{f.name}"
        docs[key] = doc
        docs[f.name] = doc
    return docs


def get_triggers(doc: dict) -> dict:
    """Normalise a workflow's ``on:`` block to ``{trigger: None}``.

    ``on:`` may be a string, a list, or a mapping, and YAML parses the bare key
    ``on`` as the boolean ``True`` -- all three shapes (plus the missing case)
    are handled identically to the original validators.
    """
    on = doc.get("on", doc.get(True, {}))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def find_callers(workflows: Dict[str, dict]) -> Dict[str, Set[str]]:
    """Map each locally-called ``./relative`` workflow to the files that call it.

    Only ``uses:`` values starting with ``./`` are in-repo references; the
    ``owner/repo/.github/...`` cross-repo calls (the composite actions) are
    ignored because they resolve to another repository's checkout.
    """
    out: Dict[str, Set[str]] = {}
    for name, doc in workflows.items():
        for job in (doc.get("jobs") or {}).values():
            uses = (job or {}).get("uses", "")
            if isinstance(uses, str) and uses.startswith("./"):
                out.setdefault(uses[2:], set()).add(name)
    return out


def is_reachable(name: str, workflows: Dict[str, dict], _seen: Set[str] | None = None) -> bool:
    """True if ``name`` has an active trigger, or is called (transitively) by one.

    ``_seen`` guards against cycles in the ``./`` call graph; revisiting a node
    stops the recursion rather than looping forever.
    """
    _seen = _seen or set()
    if name in _seen:
        return False
    _seen.add(name)
    doc = workflows.get(name)
    if doc is None:
        return False
    if ACTIVE_TRIGGERS & set(get_triggers(doc)):
        return True
    return any(is_reachable(c, workflows, _seen) for c in find_callers(workflows).get(name, ()))
