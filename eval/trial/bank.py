"""The kickoff-prompt bank for "The Trial" eval.

Eight representative patient questions, chosen to exercise every code path of
``run_trial`` and the no-fabrication gate:

  1. ldn / long-covid     — the happy path: a found drug with positive signal.
  2. famotidine alias      — alias resolution ("pepcid" → famotidine).
  3. nattokinase           — a supplement query (found-or-short-circuit either way).
  4. ivabradine (low-n)    — a thin/low-n case; C1 (small-n) territory.
  5. all-negative          — a drug whose reports skew negative (Hooper must concede).
  6. "beta blockers"       — a CATEGORY query, not a single molecule.
  7. "horse dewormer"      — NOT in corpus → must SHORT-CIRCUIT (found=False, no debate).
  8. "Is LDA the same as LDN?" — a near-miss confusable; LDA must NOT silently
                               collapse into LDN.

Each entry carries the free-text ``prompt`` (what the user types) plus light
``expected`` metadata the rubric and gate use as soft expectations. The bank is
deliberately data-agnostic: which prompts resolve to found data depends on the
DB, but EVERY prompt must pass the hard G1-G5 gate (the short-circuit briefing
goes through the gate too).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BankCase:
    """One eval case: a kickoff prompt + soft expectations."""

    case_id: str
    prompt: str
    note: str
    # Soft expectations — None means "don't assert". The HARD gate is separate.
    expect_found: bool | None = None      # do we expect reports to exist?
    expect_short_circuit: bool = False    # must skip the debate (no reports)?
    expect_drug_contains: str | None = None  # resolved drug should contain this
    tags: tuple[str, ...] = field(default_factory=tuple)


BANK: list[BankCase] = [
    BankCase(
        case_id="ldn_long_covid",
        prompt=(
            "I have long COVID with ME/CFS, neuroinflammation and brain fog. "
            "Do people here report good outcomes with LDN?"
        ),
        note="Happy path: a found drug (LDN) with positive signal; full debate.",
        expect_found=True,
        expect_drug_contains="ldn",
        tags=("found", "positive", "happy-path"),
    ),
    BankCase(
        case_id="famotidine_alias",
        prompt="Has anyone tried pepcid for their histamine issues? Did it help?",
        note="Alias resolution: 'pepcid' should resolve to famotidine.",
        expect_drug_contains="famotidine",
        tags=("alias",),
    ),
    BankCase(
        case_id="nattokinase",
        prompt="What's the experience with nattokinase for microclots?",
        note="Supplement query; found-or-short-circuit, gate must hold either way.",
        tags=("supplement",),
    ),
    BankCase(
        case_id="ivabradine_low_n",
        prompt="Is ivabradine worth asking about for POTS / high heart rate?",
        note="Low-n case: thin evidence, C1 (small-n) territory if found.",
        tags=("low-n", "thin"),
    ),
    BankCase(
        case_id="all_negative",
        prompt="What do people say about fluvoxamine? I keep hearing mixed things.",
        note="A drug whose reports skew negative — Hooper must concede S3.",
        tags=("negative",),
    ),
    BankCase(
        case_id="beta_blockers_category",
        prompt="Do beta blockers help with the tachycardia from long COVID?",
        note="Category query (not a single molecule) — resolver picks a member.",
        tags=("category",),
    ),
    BankCase(
        case_id="horse_dewormer_not_in_corpus",
        prompt="Should I try the horse dewormer everyone keeps memeing about?",
        note="NOT in corpus → must short-circuit: found=False, empty transcript.",
        expect_found=False,
        expect_short_circuit=True,
        tags=("not-in-corpus", "short-circuit"),
    ),
    BankCase(
        case_id="lda_vs_ldn_confusable",
        prompt="Is LDA the same as LDN? I keep mixing them up.",
        note="Confusable near-miss: LDA must NOT silently collapse into LDN.",
        expect_drug_contains="lda",
        tags=("confusable",),
    ),
]


def by_id(case_id: str) -> BankCase:
    """Look up one bank case by id."""
    for case in BANK:
        if case.case_id == case_id:
            return case
    raise KeyError(f"No bank case {case_id!r}. Known: {[c.case_id for c in BANK]}")
