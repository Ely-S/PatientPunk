"""Merge the recovered dose/route extractions into the original exposure set.

Original exposures come from pipeline_b_compound_exposures. Recovered ones come from
the 2026-09-01 recall-repair run, gated on the corroboration check: a numeric dose is
kept only when it appears within CORROBORATION_WINDOW characters of a mention of the
compound it was attributed to. That filter exists because the recall fix cost
attribution accuracy -- without it, three doses belonging to other compounds survive.

Recovered rows FILL, never OVERWRITE. Where the original run already recorded a dose or
route for an (author, compound), the original wins.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from pathlib import Path

# Data lives beside the checkout, not in it (AGENTS.md). PATIENTPUNK_DATA wins when
# set, so a contributor keeping it elsewhere does not have to edit this file.
ROOT = Path(__file__).resolve().parents[2]          # repo root
DATA_ROOT = Path(os.environ.get("PATIENTPUNK_DATA") or ROOT.parent / "PatientPunk_data")
DATA = DATA_ROOT / "studies" / "tropoflavin_nootropics" / "runs"
COMP_DB = DATA / "2026-08-31-comparator-cohort/sentiment/comparators.db"
LINKED_DB = DATA / "2026-08-31-comparator-cohort/study/nootropics_pipeline_a_b_linked.db"
REPAIR = DATA / "2026-09-01-recall-repair"
CORPUS = DATA / "2026-08-27-linked-dose-route/corpus/users"

CORROBORATION_WINDOW = 400
TARGET = re.compile(r"7[,.\s-]?8[\s-]?dhf|dihydroxyflavone|tropoflavin|\bdhf\b"
                    r"|4'?\s?-?\s?dma|eutropoflavin", re.I)
DMA = re.compile(r"4'?\s?-?\s?dma|eutropoflavin", re.I)
DRUG_ID = {"7,8-DHF": 1, "4'-DMA": 2}
# The linked db's own route -> bucket vocabulary. Recovered rows carry raw route
# words, so they must be mapped into the same buckets or the two sources will not
# stack (an "oral" row and a "swallowed oral" row are the same thing).
ROUTE_BUCKET = {
    "topical": "dermal", "transdermal": "dermal",
    "intranasal": "nasal mucosal", "nasal": "nasal mucosal",
    "buccal": "oral mucosal", "sublingual": "oral mucosal",
    "injection": "parenteral", "intramuscular": "parenteral",
    "intravenous": "parenteral", "subcutaneous": "parenteral",
    "inhaled": "pulmonary",
    "rectal": "rectal or vaginal", "suppository": "rectal or vaginal",
    "oral": "swallowed oral",
}

BANDS = [(5, "<5 mg"), (10, "5 to <10 mg"), (25, "10 to <25 mg"),
         (50, "25 to <50 mg"), (100, "50 to <100 mg")]


def connect():
    con = sqlite3.connect(f"file:{COMP_DB}?mode=ro", uri=True)
    con.execute("attach database ? as L", (f"file:{LINKED_DB}?mode=ro",))
    return con


def band_of(mg: float) -> str:
    for hi, label in BANDS:
        if mg < hi:
            return label
    return ">=100 mg"


def to_mg(value: str) -> float | None:
    m = re.search(r"([\d.]+)\s*(mg|mcg|g)\b", value, re.I)
    if not m:
        return None
    x, unit = float(m.group(1)), m.group(2).lower()
    return x / 1000 if unit == "mcg" else x * 1000 if unit == "g" else x


def author_text(author: str) -> str:
    path = CORPUS / f"{author}.json"
    if not path.exists():
        return ""
    d = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for p in d.get("posts") or []:
        parts += [p.get("title") or "", p.get("body") or ""]
    parts += [c.get("body") or "" for c in (d.get("comments") or [])]
    return "\n".join(parts)


def corroborated(text: str, value: str) -> bool:
    num = re.search(r"[\d.]+", value)
    if not num:
        return False
    mentions = [m.start() for m in TARGET.finditer(text)]
    hits = [m.start() for m in re.finditer(re.escape(num.group()), text)]
    if not mentions or not hits:
        return False
    return min(abs(h - m) for h in hits for m in mentions) <= CORROBORATION_WINDOW


def load_recovered() -> dict[tuple[str, str], dict]:
    """(author, compound) -> {'mg': float|None, 'route': str|None} from the repair run."""
    records = REPAIR / "improved" / "records.csv"
    if not records.exists():
        return {}
    out: dict[tuple[str, str], dict] = {}
    for row in csv.DictReader(records.open(encoding="utf-8")):
        author, text = row["author_hash"], None
        for field, kind in (("dosage", "mg"), ("administration_route", "route")):
            for item in (row.get(field) or "").split("|"):
                if ":" not in item:
                    continue
                treatment, value = (s.strip() for s in item.split(":", 1))
                if not TARGET.search(treatment):
                    continue
                compound = "4'-DMA" if DMA.search(treatment) else "7,8-DHF"
                slot = out.setdefault((author, compound), {"mg": None, "route": None})
                if kind == "mg":
                    mg = to_mg(value)
                    if mg is None:
                        continue
                    if text is None:
                        text = author_text(author)
                    if not corroborated(text, value):
                        continue          # another compound's dose; drop it
                    slot["mg"] = mg if slot["mg"] is None else max(slot["mg"], mg)
                else:
                    bucket = ROUTE_BUCKET.get(value.lower())
                    if bucket:
                        slot["route"] = slot["route"] or bucket
    return {k: v for k, v in out.items() if v["mg"] is not None or v["route"]}


def side_effect_flag(con, author: str, drug_id: int) -> tuple[bool, int, bool]:
    """(has_side_effect, n_distinct, observed) for one author-drug from pipeline A."""
    rows = con.execute(
        "select side_effects from treatment_reports where drug_id=? and user_id=?",
        (drug_id, author)).fetchall()
    terms: set[str] = set()
    for (raw,) in rows:
        if not raw:
            continue
        try:
            arr = json.loads(raw)
        except Exception:
            continue
        terms |= {str(x).strip().lower() for x in (arr or []) if str(x).strip()}
    return bool(terms), len(terms), bool(rows)


def build(con):
    """One row per (author, compound) exposure, original and recovered merged."""
    rows: dict[tuple[str, str], dict] = {}
    for author, compound, band, order, route in con.execute("""
            select author_hash, target_compound, dose_band, dose_band_order, route_bucket
            from L.pipeline_b_compound_exposures"""):
        rows[(author, compound)] = dict(
            author=author, compound=compound,
            dose_band=band if band not in ("not reported",) else None,
            dose_order=order,
            route=None if route == "not reported" else route,
            origin="original")

    for (author, compound), rec in load_recovered().items():
        row = rows.get((author, compound))
        if row is None:
            row = rows[(author, compound)] = dict(
                author=author, compound=compound, dose_band=None,
                dose_order=None, route=None, origin="recovered")
        filled = False
        if row["dose_band"] is None and rec["mg"] is not None:
            row["dose_band"] = band_of(rec["mg"])
            row["dose_order"] = next((i for i, (_, lab) in enumerate(BANDS, 1)
                                      if lab == row["dose_band"]), 6)
            filled = True
        if row["route"] is None and rec["route"]:
            row["route"] = rec["route"]
            filled = True
        if filled and row["origin"] == "original":
            row["origin"] = "original+recovered"

    out = []
    for row in rows.values():
        has, n, observed = side_effect_flag(con, row["author"], DRUG_ID[row["compound"]])
        out.append({**row, "has_se": has, "n_se": n, "observed": observed})
    return out


# --------------------------------------------------------------------------------------
# Statistics. Kept here so the notebook and any script agree on the same definitions.
# --------------------------------------------------------------------------------------
import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Point estimate and interval. Wilson, not normal-approximation: at these cell
    sizes (often < 10) the normal interval runs past 0 and 1 and understates width."""
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, max(0.0, centre - half), min(1.0, centre + half)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact on [[a, b], [c, d]]."""
    from math import comb
    n, r1, c1 = a + b + c + d, a + b, a + c
    if not n or not comb(n, c1):
        return float("nan")
    pr = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p0 = pr(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p0 * (1 + 1e-9))


def cochran_armitage(cells: list[tuple[int, int, int]]) -> tuple[float, float]:
    """Trend across ordered dose bands. cells = [(score, events, n)]."""
    N = sum(n for _, _, n in cells)
    K = sum(k for _, k, _ in cells)
    if N == 0 or K in (0, N):
        return float("nan"), float("nan")
    pbar = K / N
    tbar = sum(s * n for s, _, n in cells) / N
    num = sum(s * (k - n * pbar) for s, k, n in cells)
    var = pbar * (1 - pbar) * sum(n * (s - tbar) ** 2 for s, _, n in cells)
    if var <= 0:
        return float("nan"), float("nan")
    z = num / math.sqrt(var)
    return z, math.erfc(abs(z) / math.sqrt(2))


BAND_ORDER = ["<5 mg", "5 to <10 mg", "10 to <25 mg", "25 to <50 mg",
              "50 to <100 mg", ">=100 mg", "multiple bands"]
ROUTE_ORDER = ["oral mucosal", "swallowed oral", "nasal mucosal", "dermal",
               "rectal or vaginal", "parenteral", "pulmonary", "multiple route families"]
