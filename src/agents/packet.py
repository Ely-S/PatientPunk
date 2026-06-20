"""EvidencePacket — the single source of truth for "The Trial" debate.

`build_packet(drug_query, db_path)` is a DETERMINISTIC resolver: it calls the
read-only tools, deduplicates reports by user (one sentiment per user_id,
strongest signal wins — mirroring `verify.py`'s tiebreaker), computes every
headline number, picks verbatim quotes, derives a confidence tier, and assigns
a stable `claim_id` to each fact. The resulting `EvidencePacket.as_prompt_block()`
is the ONLY evidence the debate agents ever see — they may cite claim_ids, never
invent numbers. All headline %/quotes are code-templated downstream, never
LLM-written.

Frozen contract (the files integrate, names are fixed):
  EvidencePacket fields, claim_id scheme (S1..S4, SE1.., Q-pos-N, Q-neg-N,
  C1..C4, PROV), methods as_prompt_block()/claim(), function build_packet().

`src/` system — imports only from `utilities` and sibling `tools`. NEVER imports
`patientpunk` / `variable_extraction` (frozen decoupling boundary).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from utilities.db import open_db

from agents.tools import (
    SIG_RANK,
    _resolve_drug,
    get_caveats,
    get_example_reports,
    get_sentiment_breakdown,
    get_side_effects,
)

# Max verbatim quotes surfaced per pole (positive / negative).
_MAX_QUOTES_PER_POLE = 3
# Small-n threshold (distinct users) — fewer than this and we hedge hard.
_SMALL_N = 30

# IRON RULES the agents must obey — embedded verbatim in the prompt block so the
# constraint travels with the evidence the model sees.
_IRON_RULES = (
    "IRON RULES (non-negotiable):\n"
    "  1. Cite ONLY the claim_ids below. Never invent a number, percentage, or quote.\n"
    "     Refer to evidence as cite(\"S2\") or quote(\"Q-pos-1\"); the system fills in\n"
    "     the literal text. If a fact is not a claim_id here, you do not have it.\n"
    "  2. NEVER tell anyone to start, stop, switch, or dose a drug. You weigh evidence;\n"
    "     a doctor decides. Keep it about what the reports do and do not show.\n"
    "  3. A low negative count is NOT proof of safety: see C3 — reports exist only when\n"
    "     an author expressed personal experience, so non-experiential mentions are\n"
    "     silently dropped. Absence of negatives != safe.\n"
    "  4. This is anecdotal self-report from one community (C2, C4), not a trial.\n"
    "  5. Keep any humor PG and OFF the evidence path.\n"
)


@dataclass
class EvidencePacket:
    """Frozen, deterministic evidence dossier for one drug query.

    Every number here is computed in `build_packet` from the DB — agents only
    read `as_prompt_block()`. `claims` maps each claim_id to a dict carrying a
    literal `render` string (what gets substituted into agent text) plus the
    structured `value`.
    """

    drug_query: str
    drug: str
    found: bool
    n_reports: int
    n_users: int
    counts: dict  # {positive, negative, mixed, neutral} on USER-deduped rows
    pct: dict  # same keys, int % of n_users
    signal_mix: dict  # {strong, moderate, weak}
    side_effects: list  # [{effect, count}]
    quotes: list  # [{claim_id, pole, text, post_id, signal}]
    caveats: list  # [{claim_id, text}]
    confidence_tier: str  # none | thin | moderate | suggestive
    provenance: dict  # {claim_id:'PROV', run_id, commit_hash, run_at}
    claims: dict = field(default_factory=dict)  # claim_id -> {kind, render, value}

    def claim(self, cid: str) -> dict:
        """Return the claim dict for a claim_id, or a safe 'unknown' stub."""
        return self.claims.get(
            cid,
            {"kind": "unknown", "render": f"[unknown claim {cid}]", "value": None},
        )

    def as_prompt_block(self) -> str:
        """The ONLY evidence the debate agents see.

        Lists every claim_id with its rendered content, then the IRON RULES.
        Deterministic string — no LLM, no fabrication.
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append(f"EVIDENCE PACKET — drug: {self.drug!r} (query: {self.drug_query!r})")
        lines.append(f"confidence tier: {self.confidence_tier}")
        lines.append("=" * 60)
        if not self.found:
            lines.append("")
            lines.append(
                "NO REPORTS. The corpus has zero personal-experience reports for "
                "this query. There is nothing to debate — say so plainly and stop."
            )
            lines.append("")
            lines.append(_IRON_RULES)
            return "\n".join(lines)

        lines.append("")
        lines.append("CLAIMS (cite these ids — this is the whole of your evidence):")
        # Emit in a stable, readable order: stats, side effects, quotes, caveats, prov.
        for cid in self._ordered_claim_ids():
            c = self.claims[cid]
            lines.append(f"  [{cid}] {c['render']}")
        lines.append("")
        lines.append(_IRON_RULES)
        return "\n".join(lines)

    def _ordered_claim_ids(self) -> list[str]:
        def sort_key(cid: str) -> tuple:
            if cid == "PROV":
                return (4, 0, cid)
            if cid.startswith("SE"):
                return (1, _tail_int(cid[2:]), cid)
            if cid.startswith("S"):
                return (0, _tail_int(cid[1:]), cid)
            if cid.startswith("Q-pos"):
                return (2, 0, cid)
            if cid.startswith("Q-neg"):
                return (2, 1, cid)
            if cid.startswith("C"):
                return (3, _tail_int(cid[1:]), cid)
            return (9, 0, cid)

        return sorted(self.claims.keys(), key=sort_key)


def _tail_int(s: str) -> int:
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _pct(part: int, whole: int) -> int:
    """Integer percent of whole, 0 when whole is 0."""
    return round(part / whole * 100) if whole else 0


def _dedup_by_user(db_path: str | Path, canonical: str) -> list[dict]:
    """Return one row per user_id: strongest-signal sentiment wins.

    Mirrors verify.py's per-user dedup but uses signal strength as the primary
    key (then post_date as a tiebreaker), since the live sentiment DB is the
    relevant denominator (n_users). Each row: {user_id, sentiment, signal,
    side_effects:list, post_id}.
    """
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT tr.user_id, tr.sentiment, tr.signal_strength, tr.side_effects, "
            "       tr.post_id, p.post_date "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "JOIN posts p ON tr.post_id = p.post_id "
            "WHERE t.canonical_name = ? COLLATE NOCASE",
            (canonical,),
        ).fetchall()
    finally:
        conn.close()

    import json as _json

    by_user: dict[str, dict] = {}
    for user_id, sentiment, signal, side_effects, post_id, post_date in rows:
        sig_r = SIG_RANK.get(signal, 0)
        date = post_date or 0
        try:
            se = _json.loads(side_effects) if side_effects else []
        except (ValueError, TypeError):
            se = []
        se = [str(x).strip().lower() for x in se if str(x).strip()] if isinstance(se, list) else []
        cand = {
            "user_id": user_id,
            "sentiment": sentiment,
            "signal": signal or "n/a",
            "side_effects": se,
            "post_id": post_id,
            "_rank": (sig_r, date),
        }
        cur = by_user.get(user_id)
        # Strongest signal wins; date breaks ties (more recent preferred).
        if cur is None or cand["_rank"] > cur["_rank"]:
            by_user[user_id] = cand
    return list(by_user.values())


def _confidence_tier(n_users: int, signal_mix: dict) -> str:
    """Derive a tier from deduped-user count, nudged by signal mix.

    Base ladder: 0 -> none, <10 -> thin, <30 -> moderate, else suggestive.
    Blend: if the base would be 'suggestive' but no strong/moderate signal
    backs it, step down to 'moderate' (volume without strength is weaker).
    """
    if n_users <= 0:
        return "none"
    if n_users < 10:
        base = "thin"
    elif n_users < _SMALL_N:
        base = "moderate"
    else:
        base = "suggestive"

    strong_backing = signal_mix.get("strong", 0) + signal_mix.get("moderate", 0)
    if base == "suggestive" and strong_backing == 0:
        return "moderate"
    if base == "thin" and strong_backing == 0:
        # All-weak thin evidence is barely above noise, but still > none.
        return "thin"
    return base


def _read_provenance(db_path: str | Path, canonical: str) -> dict:
    """Read provenance from the latest extraction_runs row backing these reports."""
    conn = open_db(Path(db_path))
    try:
        row = conn.execute(
            "SELECT er.run_id, er.commit_hash, er.run_at "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "JOIN extraction_runs er ON tr.run_id = er.run_id "
            "WHERE t.canonical_name = ? COLLATE NOCASE "
            "ORDER BY er.run_at DESC, er.run_id DESC "
            "LIMIT 1",
            (canonical,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"claim_id": "PROV", "run_id": None, "commit_hash": None, "run_at": None}
    run_id, commit_hash, run_at = row
    return {
        "claim_id": "PROV",
        "run_id": run_id,
        "commit_hash": commit_hash,
        "run_at": run_at,
    }


def _empty_packet(drug_query: str, canonical: str) -> EvidencePacket:
    """Packet for a drug with zero reports — found=False, no claims to debate."""
    claims = {
        "PROV": {
            "kind": "provenance",
            "render": "provenance: no reports (no run)",
            "value": {"claim_id": "PROV", "run_id": None, "commit_hash": None, "run_at": None},
        }
    }
    return EvidencePacket(
        drug_query=drug_query,
        drug=canonical,
        found=False,
        n_reports=0,
        n_users=0,
        counts={"positive": 0, "negative": 0, "mixed": 0, "neutral": 0},
        pct={"positive": 0, "negative": 0, "mixed": 0, "neutral": 0},
        signal_mix={"strong": 0, "moderate": 0, "weak": 0},
        side_effects=[],
        quotes=[],
        caveats=[],
        confidence_tier="none",
        provenance=claims["PROV"]["value"],
        claims=claims,
    )


def build_packet(drug_query: str, db_path: str | Path) -> EvidencePacket:
    """Deterministically assemble the EvidencePacket for one drug query.

    Steps: resolve -> pull tool data -> dedup by user (strongest signal) ->
    counts/pct on the deduped set -> signal mix -> side effects -> <=3 verbatim
    quotes per pole (strongest signal first) -> confidence tier -> caveats
    (C1..C4) -> provenance (PROV) -> assign every claim_id into `.claims`.

    Robust to the tiny demo DB (7 reports): every step degrades to empty rather
    than raising; an unknown / zero-report drug short-circuits to a found=False
    packet with no claims beyond PROV.
    """
    canonical = _resolve_drug(drug_query, db_path)

    breakdown = get_sentiment_breakdown(canonical, db_path)
    if not breakdown["found"]:
        return _empty_packet(drug_query, canonical)

    deduped = _dedup_by_user(db_path, canonical)
    n_users = len(deduped)
    if n_users == 0:
        return _empty_packet(drug_query, canonical)

    n_reports = breakdown["n_reports"]

    # ── User-deduped sentiment counts + pct (denominator = n_users) ──────────
    counts = {"positive": 0, "negative": 0, "mixed": 0, "neutral": 0}
    for r in deduped:
        s = r["sentiment"]
        counts[s] = counts.get(s, 0) + 1
    pct = {k: _pct(counts.get(k, 0), n_users) for k in ("positive", "negative", "mixed", "neutral")}

    # ── Signal mix over the deduped rows ─────────────────────────────────────
    sig_counter: Counter[str] = Counter()
    for r in deduped:
        sig = r["signal"] if r["signal"] in ("strong", "moderate", "weak") else None
        if sig:
            sig_counter[sig] += 1
    signal_mix = {
        "strong": sig_counter.get("strong", 0),
        "moderate": sig_counter.get("moderate", 0),
        "weak": sig_counter.get("weak", 0),
    }

    # ── Side effects: prefer deduped-row tally, fall back to the tool ────────
    se_counter: Counter[str] = Counter()
    for r in deduped:
        for effect in r["side_effects"]:
            se_counter[effect] += 1
    if se_counter:
        side_effects = [{"effect": e, "count": c} for e, c in se_counter.most_common()]
    else:
        side_effects = get_side_effects(canonical, db_path).get("side_effects", [])

    # ── Verbatim quotes: <=3 per pole, strongest signal first ────────────────
    quotes: list[dict] = []
    quotes.extend(_collect_quotes(canonical, db_path, "positive", "pos"))
    quotes.extend(_collect_quotes(canonical, db_path, "negative", "neg"))

    # ── Confidence tier ──────────────────────────────────────────────────────
    confidence_tier = _confidence_tier(n_users, signal_mix)

    # ── Provenance ───────────────────────────────────────────────────────────
    provenance = _read_provenance(db_path, canonical)

    # ── Caveats (C1..C4) ─────────────────────────────────────────────────────
    cav = get_caveats(canonical, db_path)
    caveats = _build_caveats(n_users, cav)

    # ── Assemble claims dict (every claim_id) ────────────────────────────────
    claims: dict[str, dict] = {}

    claims["S1"] = {
        "kind": "stat",
        "render": f"{n_users} distinct patients reported personal experience "
        f"with {canonical} ({n_reports} raw reports before per-user dedup).",
        "value": {"n_users": n_users, "n_reports": n_reports},
    }
    claims["S2"] = {
        "kind": "stat",
        "render": f"positive: {counts['positive']} of {n_users} patients "
        f"({pct['positive']}%).",
        "value": {"count": counts["positive"], "pct": pct["positive"]},
    }
    claims["S3"] = {
        "kind": "stat",
        "render": f"negative: {counts['negative']} of {n_users} patients "
        f"({pct['negative']}%).",
        "value": {"count": counts["negative"], "pct": pct["negative"]},
    }
    claims["S4"] = {
        "kind": "stat",
        "render": f"signal mix (deduped patients): strong={signal_mix['strong']}, "
        f"moderate={signal_mix['moderate']}, weak={signal_mix['weak']}. "
        f"mixed={counts.get('mixed', 0)}, neutral={counts.get('neutral', 0)} sentiment.",
        "value": {"signal_mix": signal_mix, "mixed": counts.get("mixed", 0),
                  "neutral": counts.get("neutral", 0)},
    }

    for i, se in enumerate(side_effects, start=1):
        cid = f"SE{i}"
        claims[cid] = {
            "kind": "side_effect",
            "render": f"reported side effect: {se['effect']} (x{se['count']}).",
            "value": se,
        }

    for q in quotes:
        claims[q["claim_id"]] = {
            "kind": "quote",
            "render": f"\"{q['text']}\" — [{q['pole']}, signal={q['signal']}, "
            f"post {q['post_id']}]",
            "value": q,
        }

    for cav_item in caveats:
        claims[cav_item["claim_id"]] = {
            "kind": "caveat",
            "render": cav_item["text"],
            "value": cav_item,
        }

    claims["PROV"] = {
        "kind": "provenance",
        "render": f"provenance: run_id={provenance.get('run_id')}, "
        f"commit={str(provenance.get('commit_hash'))[:8]}, "
        f"run_at={provenance.get('run_at')}.",
        "value": provenance,
    }

    return EvidencePacket(
        drug_query=drug_query,
        drug=canonical,
        found=True,
        n_reports=n_reports,
        n_users=n_users,
        counts=counts,
        pct=pct,
        signal_mix=signal_mix,
        side_effects=side_effects,
        quotes=quotes,
        caveats=caveats,
        confidence_tier=confidence_tier,
        provenance=provenance,
        claims=claims,
    )


def _collect_quotes(canonical: str, db_path: str | Path, sentiment: str, pole: str) -> list[dict]:
    """Up to _MAX_QUOTES_PER_POLE verbatim quotes for one pole, strongest first."""
    res = get_example_reports(canonical, sentiment, _MAX_QUOTES_PER_POLE, db_path)
    out: list[dict] = []
    for i, ex in enumerate(res.get("examples", []), start=1):
        text = (ex.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "claim_id": f"Q-{pole}-{i}",
                "pole": pole,
                "text": text,
                "post_id": ex.get("post_id"),
                "signal": ex.get("signal", "n/a"),
            }
        )
    return out


def _build_caveats(n_users: int, cav: dict) -> list[dict]:
    """Build the four standing caveats C1..C4 from the caveats tool output."""
    subreddits = cav.get("subreddits") or []
    sub_label = subreddits[0] if len(subreddits) == 1 else f"{len(subreddits)} communities"
    return [
        {
            "claim_id": "C1",
            "text": (
                f"SMALL N: only {n_users} distinct patients"
                + (
                    " — below the n>=30 bar; treat every percentage as noisy and provisional."
                    if n_users < _SMALL_N
                    else " — still a community sample, not a trial."
                )
            ),
        },
        {
            "claim_id": "C2",
            "text": (
                f"SINGLE SOURCE: all reports come from {sub_label}; self-selected "
                "forum users are not the general patient population."
            ),
        },
        {
            "claim_id": "C3",
            "text": (
                "SILENT DROP / SELF-SELECTION: a report row exists ONLY when an "
                "author voiced personal experience (signal != 'n/a'). Non-experiential "
                "mentions are dropped before counting, so a low NEGATIVE count is NOT "
                "evidence of safety — absence of negatives != safe."
            ),
        },
        {
            "claim_id": "C4",
            "text": (
                "SELF-REPORT / ANECDOTAL: these are firsthand anecdotes, not measured "
                "outcomes — no dosing, no controls, no follow-up, recall and placebo "
                "uncontrolled."
            ),
        },
    ]
