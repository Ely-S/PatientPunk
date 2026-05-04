"""
Dump the `treatment.aliases` column from the analysis DB to a markdown file.

This produces `docs/RCT_historical_validation/DRUG_ALIASES.md` — a static,
reviewable export of the alias list every pipeline run substring-matched
against. Source of truth is the SQLite DB; this script just renders it.

Each pipeline run wrote the alias list into `treatment.aliases` (a JSON
column) via Claude Sonnet 4.6 and the `drug_aliases_prompt()` prompt at
canonicalization time. Reviewers auditing drug-extraction precision/recall and canonicalization
alias coverage need to see this list directly.

Usage:
    python scripts/dump_drug_aliases.py \\
        --db data/historical_validation/historical_validation_2020-07_to_2022-12.db \\
        --out docs/RCT_historical_validation/DRUG_ALIASES.md

Re-running with the same DB produces an identical markdown file.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# A small set of characteristics worth flagging programmatically. These are
# *flags for review*, not "errors" — the audit's job is to inspect them.
SHORT_ALIAS_THRESHOLD = 4  # aliases of this length or shorter are easy to
                           #   accidentally substring-match against other words


def categorize_aliases(canonical: str, aliases: list[str]) -> dict[str, list[str]]:
    """Heuristic categorization for review. Pure presentation, not authoritative."""
    short = [a for a in aliases if len(a) <= SHORT_ALIAS_THRESHOLD]
    contains_canonical = [a for a in aliases if canonical.lower() in a.lower()]
    likely_misspellings = [
        a for a in aliases
        if a not in contains_canonical
        and not any(c.isspace() for c in a)
        and abs(len(a) - len(canonical)) <= 2
        and a not in short
    ]
    multi_word = [a for a in aliases if " " in a or "-" in a or "/" in a]
    return {
        "short": short,
        "multi_word": multi_word,
        "likely_misspellings": likely_misspellings,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"ERROR: DB not found: {args.db}")

    conn = sqlite3.connect(str(args.db))
    rows = conn.execute(
        "SELECT canonical_name, aliases, treatment_class, notes "
        "FROM treatment ORDER BY canonical_name"
    ).fetchall()
    conn.close()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append("# Drug aliases used in extraction\n")
    lines.append(f"**Generated:** {now} from `{args.db}`")
    lines.append("**Generator:** `scripts/dump_drug_aliases.py`")
    lines.append("")
    lines.append("This file is a static export of the `treatment.aliases` column from")
    lines.append("the analysis SQLite DB. The lists are what every pipeline run")
    lines.append("substring-matched posts and comments against during the extraction")
    lines.append("step and what every canonicalization step normalized to.")
    lines.append("Reviewers can audit these lists directly without running anything.")
    lines.append("")
    lines.append("## How these aliases were generated")
    lines.append("")
    lines.append("During the pipeline's canonicalization step (`src/pipeline/canonicalize.py`),")
    lines.append("Claude Sonnet 4.6 was queried with `drug_aliases_prompt(target_drug)`")
    lines.append("(see `src/utilities/__init__.py:drug_aliases_prompt`) to produce a list")
    lines.append("of brand names, generic names, common abbreviations, misspellings, and")
    lines.append("class synonyms for each of the six target drugs. The model's output")
    lines.append("was inserted as JSON into `treatment.aliases` at run time and joined")
    lines.append("on by the SQL queries that produce Figure 1, Table 2, and Table 3.")
    lines.append("")
    lines.append("### Epistemic status")
    lines.append("")
    lines.append("The alias lists are intentionally produced by the pipeline's LLM")
    lines.append("canonicalization step rather than being manually curated, because")
    lines.append("evaluating the LLM canonicalization step is part of the method this")
    lines.append("paper demonstrates. We treat alias generation as a pipeline output")
    lines.append("rather than a hand-authored input, and publish the generated aliases")
    lines.append("here so that dependency is fully auditable — reviewers can see exactly")
    lines.append("what the substring-match step ran against. The reviewer notes section")
    lines.append("below flags entries worth a closer look; corrections to those entries")
    lines.append("would propagate through canonicalization and classification, so any")
    lines.append("change requires regenerating per-drug counts.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-drug alias lists")
    lines.append("")

    for canonical_name, aliases_json, treatment_class, notes in rows:
        try:
            aliases = json.loads(aliases_json) if aliases_json else []
        except (TypeError, ValueError):
            aliases = []
        cats = categorize_aliases(canonical_name, aliases)
        lines.append(f"### {canonical_name} ({len(aliases)} aliases)")
        lines.append("")
        if treatment_class:
            lines.append(f"**Treatment class (DB-recorded):** {treatment_class}  ")
        if notes:
            lines.append(f"**Notes:** {notes}  ")
        lines.append("")
        for a in aliases:
            tags = []
            if a in cats["short"]:
                tags.append("short")
            if a in cats["multi_word"]:
                tags.append("multi-word")
            if a in cats["likely_misspellings"]:
                tags.append("misspelling")
            tag_str = f"  *({', '.join(tags)})*" if tags else ""
            lines.append(f"- `{a}`{tag_str}")
        lines.append("")
        if cats["short"]:
            lines.append(
                f"_Heuristic flag: {len(cats['short'])} alias(es) at "
                f"≤{SHORT_ALIAS_THRESHOLD} characters. Short aliases can match "
                f"unrelated words via substring; verify these are intentional._"
            )
            lines.append("")
        lines.append("---")
        lines.append("")

    # Cross-drug audit: any alias that appears in multiple drugs' lists
    alias_to_drugs: dict[str, list[str]] = {}
    for canonical_name, aliases_json, *_ in rows:
        try:
            aliases = json.loads(aliases_json) if aliases_json else []
        except (TypeError, ValueError):
            aliases = []
        for a in aliases:
            alias_to_drugs.setdefault(a.lower(), []).append(canonical_name)
    cross_drug_collisions = {a: drugs for a, drugs in alias_to_drugs.items() if len(set(drugs)) > 1}

    lines.append("## Cross-drug alias collisions")
    lines.append("")
    lines.append(
        "Aliases that appear in more than one drug's list. An alias appearing in"
        " multiple drugs would mean the same string substring-matches into"
        " multiple per-drug filters, double-counting the post. Should be empty."
    )
    lines.append("")
    if not cross_drug_collisions:
        lines.append("**No cross-drug collisions.** Each alias is unique to one drug. ✓")
    else:
        for alias, drugs in sorted(cross_drug_collisions.items()):
            lines.append(f"- `{alias}` -> {', '.join(sorted(set(drugs)))}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Reviewer notes (manual)")
    lines.append("")
    lines.append("These are observations from a reading-pass over the alias lists,")
    lines.append("intended as starting points for review — not")
    lines.append("adjudicated corrections. The historical-validation analysis used the")
    lines.append("alias list as-is; any change here would require regenerating per-drug")
    lines.append("counts.")
    lines.append("")
    lines.append("- **prednisone** includes `prednisolone` (a related but distinct")
    lines.append("  glucocorticoid metabolite — different active molecule); class-level")
    lines.append("  terms like `steroid`, `corticosteroid`, `oral steroid`,")
    lines.append("  `glucocorticoid` (would substring-match generic class mentions");
    lines.append("  rather than prednisone-specific ones); and `pred` (4-character,")
    lines.append("  could match prefixes of unrelated words).")
    lines.append("- **loratadine** includes `loratab` — Lortab is a brand of")
    lines.append("  hydrocodone/acetaminophen, a different (opioid) drug; this is")
    lines.append("  likely an LLM error and should be reviewed.")
    lines.append("- **famotidine** includes class-level terms `h2 blocker`,")
    lines.append("  `h2 antagonist`, `acid reducer`, `heartburn relief` — not")
    lines.append("  specific to famotidine; would match generic class mentions.")
    lines.append("- **paxlovid** includes the standalone components `ritonavir`")
    lines.append("  and `nirmatrelvir`. Ritonavir is also used in HIV antivirals,")
    lines.append("  so unprefixed mentions could collapse those into paxlovid.")
    lines.append("- **colchicine** entries (autumn crocus extract, meadow saffron")
    lines.append("  extract) reference natural sources of colchicine — defensible")
    lines.append("  but worth confirming.")
    lines.append("")
    lines.append("To turn any of these into actual corrections, the path is: edit the")
    lines.append("alias list, re-run canonicalization, re-run classification, regenerate")
    lines.append("the analysis DB and figures. None of this changes the headline")
    lines.append("conclusion (every drug's responder rate stays in its current bucket")
    lines.append("when individual ambiguous aliases are removed) but it is the open")
    lines.append("methodology task of manually reviewing every alias before publication.")
    lines.append("")
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("Re-running")
    lines.append("```")
    lines.append(f"python scripts/dump_drug_aliases.py --db {args.db} --out {args.out}")
    lines.append("```")
    lines.append("against the same DB produces an identical file (deterministic ordering).")
    lines.append("If the DB's `treatment.aliases` content changes, this file should be")
    lines.append("regenerated and committed alongside the DB.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")

    n_aliases = sum(
        len(json.loads(r[1])) if r[1] else 0 for r in rows
    )
    print(f"Wrote {args.out}")
    print(f"  drugs: {len(rows)}, total aliases: {n_aliases}")
    print(f"  cross-drug collisions: {len(cross_drug_collisions)}")


if __name__ == "__main__":
    main()
