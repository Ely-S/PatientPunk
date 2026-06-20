"""
patientpunk.consolidate
~~~~~~~~~~~~~~~~~~~~~~~~~
Merge the discovered schemas from several discovery runs into ONE deduplicated
emergent schema.

Inductive discovery (Phase 3) is non-deterministic: run it on different samples
(or shards) and the same concept comes back under different names --
``medication_trial_outcome_category`` / ``medication_trial_outcome`` /
``med_response``.  Left unconsolidated those become separate, individually-sparse
columns and the feature matrix can't be clustered (a *moving* coordinate system).

``consolidate`` collapses that naming drift across runs: it groups near-synonym
discovered variables into one canonical field, tracks how many independent runs
each concept appeared in (``_n_runs_seen`` -- a robustness/stability signal),
and emits a single emergent schema ready to ``promote`` and extract deductively
at scale.

Grouping is deterministic by default (normalized-name + token-overlap union-find;
no API, reproducible).  An optional ``llm_group_fn`` adds semantic synonym
detection for the harder cases that share no tokens.

Pure functions; the deterministic path makes no API calls.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

# Suffixes discovery habitually appends to the same underlying concept; stripped
# for matching so e.g. ``medication_trial_outcome_category`` == ``..._outcome``.
_NOISE_SUFFIXES = {
    "category", "type", "status", "pattern", "reported", "used", "tried",
    "level", "score", "value", "info", "detail", "details", "experience",
    "focus", "specificity",
}
_TOKEN_SPLIT = re.compile(r"[_\W]+")


def _tokens(name: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT.split(name.lower()) if t]


def _normalized(name: str) -> str:
    """Token form with trailing noise-suffixes stripped (keep >=1 token)."""
    toks = _tokens(name)
    while len(toks) > 1 and toks[-1] in _NOISE_SUFFIXES:
        toks.pop()
    return "_".join(toks)


def _token_jaccard(a: str, b: str) -> float:
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _similar(a: str, b: str, threshold: float) -> bool:
    if _normalized(a) == _normalized(b):
        return True
    return _token_jaccard(a, b) >= threshold


class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> list[list[str]]:
        out: dict[str, list[str]] = {}
        for x in self.parent:
            out.setdefault(self.find(x), []).append(x)
        return [sorted(g) for g in out.values()]


class ConsolidateResult(BaseModel):
    """Outcome of a consolidation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    consolidated_schema: dict
    n_input_schemas: int
    n_input_fields: int        # distinct field names across all inputs
    n_consolidated: int        # fields kept after merge + min-runs filter
    n_dropped_low_runs: int
    merges: list[dict]         # [{canonical, members, n_runs}], multi-member first

    def summary(self) -> str:
        return (
            f"{self.n_input_fields} distinct variables across {self.n_input_schemas} "
            f"run(s) -> {self.n_consolidated} consolidated "
            f"({self.n_dropped_low_runs} dropped below --min-runs)"
        )


def _hit(defn: dict) -> float:
    v = defn.get("hit_rate_at_discovery", 0)
    return float(v) if isinstance(v, (int, float)) else 0.0


def _merge_group(members: list[tuple[str, int, dict]], n_runs: int) -> tuple[str, dict]:
    """Merge a synonym group's members -> (canonical_name, merged_defn).

    *members* is a list of ``(field_name, run_idx, defn)``.  Canonical name is
    the one appearing in the most runs (consensus), tie-broken by highest
    discovery hit-rate then shortest name.  Patterns and allowed_values are
    unioned across all members.
    """
    name_runs: dict[str, set] = {}
    for nm, run_idx, _ in members:
        name_runs.setdefault(nm, set()).add(run_idx)

    def name_score(nm: str):
        defns = [d for n, _, d in members if n == nm]
        return (len(name_runs[nm]), max((_hit(d) for d in defns), default=0.0), -len(nm))

    canonical_name = max(name_runs, key=name_score)
    canonical_defn = next(d for n, _, d in members if n == canonical_name)

    merged = dict(canonical_defn)  # start verbatim from the consensus definition
    patterns: list[str] = []
    allowed: list = []
    max_hit = 0.0
    for _, _, defn in members:
        for p in defn.get("patterns") or []:
            if p not in patterns:
                patterns.append(p)
        allowed_values = defn.get("allowed_values")
        if isinstance(allowed_values, list):
            for v in allowed_values:
                if v not in allowed:
                    allowed.append(v)
        max_hit = max(max_hit, _hit(defn))

    merged["patterns"] = patterns
    if allowed:
        merged["allowed_values"] = allowed
    merged["source"] = "llm_discovered"
    merged["hit_rate_at_discovery"] = max_hit
    merged["_n_runs_seen"] = n_runs
    merged["_consolidated_from"] = sorted(name_runs)
    return canonical_name, merged


def consolidate_schemas(
    schemas: list[dict],
    *,
    name_threshold: float = 0.6,
    min_runs: int = 1,
    base_schema_id: str | None = None,
    llm_group_fn=None,
) -> ConsolidateResult:
    """Merge ``extension_fields`` across *schemas* into one deduped schema.

    Parameters
    ----------
    schemas:
        Discovered schemas (each a dict with an ``extension_fields`` mapping),
        one per discovery run.
    name_threshold:
        Token-overlap (Jaccard) threshold for grouping near-synonym names.
    min_runs:
        Keep only concepts that appeared in at least this many input schemas
        (robustness filter -- the core quality knob).
    base_schema_id:
        Recorded as ``_base_schema`` on the output (lineage).
    llm_group_fn:
        Optional ``callable(names: list[str]) -> list[list[str]]`` returning
        groups of names judged semantically synonymous; their members are
        unioned in addition to the deterministic edges.
    """
    # 1. Collect (name, run_idx, defn) across all inputs.
    entries: list[tuple[str, int, dict]] = []
    for run_idx, sch in enumerate(schemas):
        ext = sch.get("extension_fields") or {}
        for name, defn in ext.items():
            if isinstance(defn, dict):
                entries.append((name, run_idx, defn))

    names = sorted({name for name, _, _ in entries})

    # 2. Group near-synonyms (deterministic union-find).
    uf = _UnionFind(names)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if _similar(a, b, name_threshold):
                uf.union(a, b)

    # 2b. Optional LLM semantic edges.
    if llm_group_fn is not None and names:
        for grp in llm_group_fn(names):
            present = [n for n in grp if n in uf.parent]
            for other in present[1:]:
                uf.union(present[0], other)

    # 3. Merge each group; filter by min_runs.
    by_name: dict[str, list[tuple[int, dict]]] = {}
    for name, run_idx, defn in entries:
        by_name.setdefault(name, []).append((run_idx, defn))

    ext_fields: dict[str, dict] = {}
    merges: list[dict] = []
    dropped = 0
    for group in uf.groups():
        members: list[tuple[str, int, dict]] = []
        runs_seen: set = set()
        for nm in group:
            for run_idx, defn in by_name.get(nm, []):
                members.append((nm, run_idx, defn))
                runs_seen.add(run_idx)
        n_runs = len(runs_seen)
        if n_runs < min_runs:
            dropped += 1
            continue
        canonical_name, merged = _merge_group(members, n_runs)
        ext_fields[canonical_name] = merged
        merges.append({"canonical": canonical_name, "members": group, "n_runs": n_runs})

    schema = {
        "schema_id": "consolidated",
        "_description": (
            "Consolidated emergent schema: near-synonym discovered variables "
            "merged across discovery runs. Promote into a base schema, then "
            "extract deductively at scale."
        ),
        "_base_schema": base_schema_id,
        "include_base_fields": [],
        "override_base_patterns": {},
        "extension_fields": ext_fields,
    }
    merges.sort(key=lambda m: (-len(m["members"]), -m["n_runs"], m["canonical"]))
    return ConsolidateResult(
        consolidated_schema=schema,
        n_input_schemas=len(schemas),
        n_input_fields=len(names),
        n_consolidated=len(ext_fields),
        n_dropped_low_runs=dropped,
        merges=merges,
    )
