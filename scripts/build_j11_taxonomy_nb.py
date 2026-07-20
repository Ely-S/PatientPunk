"""
build_j11_taxonomy_nb.py — the ⑪ value-error problem and the tiered fix (design synthesis).

A self-contained map of the judgement-⑪ variable-coding value problem and the solution we have
worked out for each field tier, so the extraction pipeline can trust the covariates the clustering
study will cluster on. Grounds every claim in the Opus semantic re-score + the producer co-failure
analysis. This is the design doc that the Tier-2 `conditions` prototype (next notebook) tests.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

DV = ROOT / "data" / "validation"
REJ = (DV / "j11_rejudge.json").as_posix()
COD = (DV / "j11_coding_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

TITLE = "Judgement 11 — the value-error problem and the tiered fix"

FRAME = (
"# Judgement ⑪ — the value-error problem, and the fix for each field tier\n\n"
"*A design synthesis, grounded in the Opus semantic re-score and the producer co-failure analysis.*\n\n"
"**The job.** Judgement ⑪ (*variable coding*) fills a fixed schema of **37 patient covariates** — age, "
"conditions, medications, dosage, functional status, symptom trajectory, and so on — from each Reddit post. "
"**These are exactly the covariates the planned clustering study will cluster patients on**, so if their "
"values are wrong or inconsistent the clusters measure noise, not patients. This notebook maps how wrong the "
"values are, *why*, and the concrete fix for each kind of field — then hands off to a prototype that tests the "
"hardest tier on the single highest-volume field.\n\n"
"**The one idea.** The 37 fields are not one problem. They sort into **three tiers by what it takes to fix "
"them** — a cheap deterministic pass, a tool-plus-rule, or a judge panel — and the whole extraction "
"architecture (two cheap producers, escalate on disagreement) only works once you route each field to the "
"right tier. Most *fields* are cheap to fix; most *errors* are not, and they cluster in one tier.")

LOAD = r'''
import json
from collections import defaultdict, Counter
import difflib, re

_R = json.load(open(r"__REJ__", encoding="utf-8"))
_C = json.load(open(r"__COD__", encoding="utf-8"))
V = [v for v in _R["verdicts"] if v["verdict"] in ("equivalent","model_subset","different")]
GOLD = {g["sample_id"]: g["fields"] for g in _C["gold"]}
val = defaultdict(dict)
for c in _C["codings"]: val[c["model"]][c["sample_id"]] = c["fields"]
verd = {(v["model"], v["sample_id"], v["field"]): v["verdict"] for v in V}

# field -> (genuine-error rate, ruled n, different n)
_bf = defaultdict(lambda: [0,0])
for v in V:
    _bf[v["field"]][0]+=1
    if v["verdict"]=="different": _bf[v["field"]][1]+=1
ferr = {f:(d/r if r else float("nan"), r, d) for f,(r,d) in _bf.items()}
TOTAL_DIFF = sum(d for _,_,d in ferr.values())

TIER = {
 "Tier 1 — deterministic post-collection": ["age","age_at_onset","infection_count","long_covid_duration_months","time_to_diagnosis","symptom_duration","dosage","procedures","prior_infections","onset_trigger","location_country","biomarker_results","dietary_interventions","vaccination_status","sex_gender","work_disability_status","diagnosis_source","clinical_trial_participation","covid_wave","location_us_state","ethnicity"],
 "Tier 2 — tool + rule": ["conditions","medications","alternative_treatments","mental_health","functional_status_tier","activity_level","symptom_trajectory"],
 "Tier 3 — judge panel / redesign": ["social_impact","healthcare_costs","diagnostic_odyssey","doctor_dismissal","misdiagnosis","healthcare_system","treatment_outcome","family_history","hormonal_events"],
}
FT = {f:t for t,fs in TIER.items() for f in fs}
def tier_agg(fs):
    r=sum(ferr[f][1] for f in fs if f in ferr); d=sum(ferr[f][2] for f in fs if f in ferr)
    return (d/r if r else float("nan")), r, len(fs), d

# producer co-failure by tier for a representative cheap cross-lab pair
def _norm(x):
    if isinstance(x,list): x=" ".join(map(str,x))
    return re.sub(r"[^a-z0-9 ]"," ",str(x).lower()).strip()
def _sim(a,b):
    ta,tb=set(_norm(a).split()),set(_norm(b).split())
    j=len(ta&tb)/len(ta|tb) if (ta|tb) else 1.0
    return max(j, difflib.SequenceMatcher(None,_norm(a),_norm(b)).ratio())
A, B = "deepseek/deepseek-v4-pro", "google/gemini-3.1-flash-lite"
cof = defaultdict(lambda:[0,0,0])   # tier -> [both_pop, agree, agree_and_wrong]
for s,gf in GOLD.items():
    for f,gv in gf.items():
        av=val[A].get(s,{}).get(f); bv=val[B].get(s,{}).get(f)
        if not (gv and av and bv): continue
        t=FT.get(f,"?"); cof[t][0]+=1
        if _sim(av,bv)>=0.5:
            cof[t][1]+=1
            if verd.get((A,s,f))=="different": cof[t][2]+=1
_tot=len(V); _c=Counter(v["verdict"] for v in V)
display(Markdown(f"*(loaded — {_tot:,} judged values, {len(TIER)} tiers; co-failure pair = {A.split('/')[-1]} + {B.split('/')[-1]})*"))
'''.replace("__REJ__", REJ).replace("__COD__", COD)

S1 = "## 1. The problem — how wrong are the coded values, and where"
S1_CODE = r'''
off = sorted([(f,e) for f,(e,r,d) in ferr.items() if r>=15 and e>=0.25], key=lambda x:-x[1])
clean = [f for f,(e,r,d) in ferr.items() if r>=15 and e<0.10]
display(Markdown(
 f"Across the 37-field schema and **{_tot:,}** co-populated values, the Opus semantic judge ruled "
 f"**{_c['equivalent']/_tot:.0%} equivalent**, **{_c['model_subset']/_tot:.0%} correct-but-less-complete "
 f"subset**, **{_c['different']/_tot:.0%} genuinely different**. So ~1-in-6 values is genuinely wrong — but "
 f"**not evenly**: **{len(off)} fields carry ≥25% error** ({', '.join(f'`{f}` {e:.0%}' for f,e in off)}), while "
 f"**{len(clean)} fields sit under 10%** (numeric / identity / geo). The shape of the fix has to follow that "
 f"concentration — which is what the tiers below encode."))
'''

S2 = ("## 2. The three tiers — most fields are cheap, most errors are not\n\n"
      "Every field sorts by *what it takes to fix it*. The counts and error come straight from the re-score.")
S2_CODE = r'''
rows=[]
for t in TIER:
    e,r,n,d = tier_agg(TIER[t]); rows.append([t, n, f"{e:.0%}", f"{d/TOTAL_DIFF:.0%}"])
tb=pd.DataFrame(rows, columns=["tier","# fields","genuine-error (wtd)","share of all errors"])
display(HTML(tb.to_html(index=False)))
fig, ax = plt.subplots(1,2, figsize=(11,3.2))
names=[t.split(" — ")[0] for t in TIER]
ax[0].bar(names,[tier_agg(TIER[t])[2] for t in TIER], color=["#27ae60","#e67e22","#c0392b"])
ax[0].set_title("# fields per tier"); ax[0].set_ylabel("fields")
share=[tier_agg(TIER[t])[3]/TOTAL_DIFF for t in TIER]
ax[1].bar(names, share, color=["#27ae60","#e67e22","#c0392b"])
for i,s in enumerate(share): ax[1].text(i,s+0.01,f"{s:.0%}",ha="center",fontweight="bold")
ax[1].set_title("share of all genuine errors"); ax[1].set_ylim(0,0.7)
for a in ax: a.tick_params(axis="x", labelsize=8)
fig.tight_layout(); plt.show()
display(Markdown(
 "**The punchline of the whole notebook:** **Tier 1 is 21 of 37 fields but a small slice of the errors; Tier 2 "
 "is only 7 fields yet carries the majority of them.** A fix that treats all fields alike would spend its effort "
 "where the errors aren't. The tiers tell you where to aim."))
'''

S3 = ("## 3. Why the tier matters for the *architecture* — producer co-failure\n\n"
      "The planned extraction runs **two cheap producers** (e.g. DeepSeek + a second LLM); where they **agree** "
      "the value is accepted, where they **disagree** it escalates to judges. That gate is only as good as its "
      "**correlated-failure** rate — how often both produce the *same wrong* value, which sails through "
      "unjudged. And co-failure is not uniform: it lives almost entirely in Tier 2.")
S3_CODE = r'''
rows=[]; barx=[]; bary=[]
for t in ["Tier 1 — deterministic post-collection","Tier 2 — tool + rule","Tier 3 — judge panel / redesign"]:
    n,ag,cf = cof[t]
    leak = cf/ag if ag else float("nan")
    rows.append([t.split(" — ")[0], n, f"{ag/n:.0%}" if n else "-", f"{leak:.0%}" if ag else "-", f"{cf/n:.0%}" if n else "-"])
    barx.append(t.split(" — ")[0]); bary.append(leak if ag else 0)
tb=pd.DataFrame(rows, columns=["tier","n","producers agree","leak (wrong | agree)","co-fail / all"])
display(HTML("<b>Producer co-failure by tier — DeepSeek-v4-pro + gemini-flash-lite</b>"+tb.to_html(index=False)))
fig, ax = plt.subplots(figsize=(7,2.7))
ax.bar(barx, bary, color=["#27ae60","#c0392b","#95a5a6"])
for i,y in enumerate(bary): ax.text(i,y+0.005,f"{y:.0%}",ha="center",fontweight="bold")
ax.set_ylabel("leak: wrong | producers agree"); ax.set_title("When two cheap producers agree, how often are they both wrong?")
fig.tight_layout(); plt.show()
_lk = {barx[i]: bary[i] for i in range(len(barx))}
_ag = {r[0]: r[2] for r in rows}
display(Markdown(
 f"**What this shows:** on **Tier 1** two producers agree {_ag['Tier 1']} of the time and are both wrong only "
 f"**{_lk['Tier 1']:.0%}** of those — agreement is trustworthy, auto-accept it. On **Tier 2** they agree "
 f"{_ag['Tier 2']} but are **wrong {_lk['Tier 2']:.0%} of the time when they agree** — they share the same "
 f"schema-boundary blind spot (both call PEM a *condition*, both file a drug under *alternative*), so agreement "
 f"does **not** mean correct. On **Tier 3** they agree only {_ag['Tier 3']}, so disagreement escalates it to "
 f"judges on its own. **Tier 2 is the dangerous tier: the gate trusts it but "
 "shouldn't — until the fix makes agreement mean something.** *(Small n; the pattern is the signal.)*"))
'''

S4 = '''## 4. The solution, tier by tier

Each tier gets the *cheapest* fix that actually closes it. The guiding rule: **fix a value where the
correct answer is recoverable; only pay a judge where it genuinely isn't.**

### Tier 1 — deterministic post-collection (21 fields, ~8% error)

The correct value is recoverable from the **extracted string alone**, so the fix is a deterministic
normalizer — **no LLM, re-runnable, free** — with three mechanisms:

- **Numeric parse** — `"at least 2 (second infection)"` → `2`; `"since March 2020"` → a duration. (age,
  counts, durations, dosage value.)
- **Ontology lookup** — `"netherlands"` → ISO `NL`; a procedure → SNOMED; a pathogen → a fixed vocabulary.
  (location, procedures, prior_infections, vaccination, biomarker test names.)
- **Enum map** — `"male (inferred from 'my wife')"` → `male`; `"alabama"` → `AL`. (sex, US-state, covid_wave,
  diagnosis_source.)

Runs **after** collection because the transform is a pure function of the stored value — you see the full
value distribution before writing the map, and it is versioned and auditable. This tier is already near zero
error; the normalizer just closes the residual and makes producer-agreement trustworthy (it already is, ~2%).

### Tier 2 — tool + rule (7 fields, the error and co-failure hotspot)

Predefined-category-able, but the tool alone leaves the residual that *causes the co-failure*. Splits into
two kinds needing different fixes.

**Kind A — ontology concept-lists** (`conditions`, `medications`, `alternative_treatments`, `mental_health`).
Two steps; the second is the one that kills the co-failure:

1. **Ontology normalization** (post-collection, deterministic) — map each value to a controlled vocabulary
   (`conditions` → UMLS, `medications`/`alternative_treatments` → RxNorm). Collapses `"b12"` = `"b12
   supplements"`, `"dysautonomia"` = `"severe dysautonomia"`. Fixes the *surface-form* half — **but not the
   co-failure**, which isn't about spelling.
2. **Schema-boundary rule** — the definitional decision the map can't make: *what counts as a member of this
   field.* The shared error is an *inclusion* mistake both producers make: `conditions` = gold `"long covid"`
   vs both producers `"long covid; PEM; fatigue"` (symptoms treated as conditions); `alternative_treatments`
   with `cetirizine`/`famotidine` (prescription drugs filed as "alternative"). Make the call **once**, write
   it into the field definition, enforce it at both the prompt and a post-collection filter — and use the
   ontology's own **semantic type** as the deterministic test (UMLS *Sign/Symptom* T184 vs *Disease/Syndrome*
   T047; RxNorm "is this a prescription drug?"). *What's left after the rule* — genuine content misreads
   (`"asthma"` where the post says `OSA`) — is the true residual, and only that goes to a judge.

**Kind B — ordinal enums** (`functional_status_tier`, `symptom_trajectory`, `activity_level`). These co-fail
because they're free text on an inherently small ordered set. The fix:

- **Design a fixed ordered scale** — `functional_status_tier`: `minimal < mild < moderate < severe <
  housebound < bedbound`; `symptom_trajectory`: `improving | worsening | relapsing-remitting | plateaued |
  recovered | mixed`.
- **Constrain the model to pick from it at extraction** (*pre*-collection — the model needs the post in view
  to judge the tier; mapping free text to a tier afterward is itself error-prone). This is the one place the
  earlier pre-collection instinct is right, as a *fixed designed* scale, not a grow-as-you-go enum.
- **Merge the duplicate** — `activity_level` and `functional_status_tier` code the same thing ("housebound /
  bedridden"); collapse to one ordinal field to stop them inflating the co-failure.

**Why this kills the co-failure:** the 21% Tier-2 leak exists *because agreement doesn't mean correct there* —
both models land on the same value inside a fog of ambiguity. The rule / enum removes the fog, so producer
agreement on a canonicalized, boundary-enforced value now *does* mean correct, and the leak should fall
toward Tier-1 levels (~2%). That is exactly what the next notebook tests on `conditions`.

### Tier 3 — judge panel / field redesign (9 fields)

No predefined-category handle: the disagreement is about **content, not format**, and Opus's own reference is
just one debatable reading (on `healthcare_system`, a model saying "US" vs gold "Canada" can *both* be right
when the post mentions both). No parser or ontology helps. The fix is a **multi-lab judge panel** that rules,
per disagreement, whether it is a real model error, a *gold* error (the reference was wrong), or *irreducibly
ambiguous* (the field is ill-posed → **redesign at ⑩**). At corpus scale you panel a **sample** to
characterize each field, not every item to correct it; a field that is mostly "ambiguous" gets dropped from
the clustering set. *(Three nominally-open fields — `family_history`, `hormonal_events`, `misdiagnosis` —
score fine only because they are rare/small; leave them.)*'''

S5 = ("## 5. How it fits together — the tier-aware routing\n\n"
      "The fixes compose into one gate stack. The point is that **each tier exits the stack at a different "
      "stage** — you never pay for a judge on a field a normalizer already closed.")
S5_CODE = r'''
rows = [
 ["1. Two cheap producers extract", "DeepSeek + a 2nd LLM code every field", "—", "cheap ×2"],
 ["2. Deterministic normalizer", "parse / ontology-lookup / enum-map every value", "Tier-1 surface + Tier-2 surface half", "free"],
 ["3. Tier-2 rule / ordinal enum", "boundary rule (lists) + designed scale (ordinals)", "Tier-2 shared blind spots", "one-time design + free enforce"],
 ["4. Producer-consensus gate", "agree -> accept, disagree -> escalate", "Tier-1 (2% leak) + Tier-2 AFTER step 3", "free"],
 ["5. Cheap-judge consensus", "llama & qwen both-OK auto-skip (3% leak)", "surface-form escalations", "cheap ×2"],
 ["6. Frontier panel (sampled)", "multi-lab vote: real error / gold error / ambiguous", "Tier-3 + the genuine residual", "expensive, rare"],
]
tb=pd.DataFrame(rows, columns=["stage","what","catches","cost"])
display(HTML(tb.to_html(index=False)))
display(Markdown(
 "**Reading it by tier:** **Tier 1** exits at stage 4 (normalized + producers agree) — **no judge ever**. "
 "**Tier 2** needs stage 3 first, *then* the producer gate becomes trustworthy and it exits at 4, with only the "
 "genuine-misread residual reaching stage 5–6. **Tier 3** falls through to stage 6, where a *sampled* panel "
 "characterizes it rather than correcting every value. Expensive frontier calls are spent only on the ~23% of "
 "errors that are genuinely content, not the 77% that are format or boundary."))
'''

S6 = ('''## 6. What the next notebook tests

The whole Tier-2 claim — *"normalize + boundary-rule makes producer agreement mean correct, dropping both the
genuine-error and the co-failure"* — is a hypothesis until measured. The prototype takes **`conditions`** (the
highest-volume Tier-2 field, 462 judged values, 30% genuine-error, a co-failure hotspot), builds the fix
(surface canonicalization + a symptoms-vs-conditions boundary rule), applies it to every producer's output and
the gold, **re-scores with Opus**, and reports **before → after** on two numbers:

1. **genuine-error** (Opus "different" rate) — does the boundary rule strip the shared symptom-inclusion error?
2. **producer co-failure** — once agreement is on canonicalized, boundary-enforced lists, does the ~21% leak
   fall toward Tier-1's ~2%?

If both drop, the tiered architecture is validated on its hardest single field and the pattern generalizes to
the rest of Tier 2. If they don't, we learn the residual is genuine content error (a judge problem), not a
boundary problem — either way, a real answer.''')

LIM = '''## Limitations

- **The tier assignment is our design judgment**, not a measured fact — the per-tier *error rates* are from the
  re-score, but which field sits in which tier is a classification we chose (and defend above).
- **"Genuine error" is vs Opus-gold, which is the reference, not ground truth** — most load-bearing on Tier 3,
  where some "error" is the gold being debatable. That is precisely why Tier 3's fix is a *panel*, not a metric.
- **Producer co-failure is a first-pass** (string-proxy agreement, small per-pair n, one representative pair);
  the pattern (Tier-2 hotspot) is robust, the exact rates are directional.
- **The routing is a design, not yet a running pipeline** — this notebook maps it; the prototype tests one tier
  of it. Describes the correctness/cost of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha=_h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha="n/a"
prov=pd.DataFrame({"item":["error source","co-failure source","fields","judged values","status","skill"],
 "value":[_R["manifest"]["source"]+" via "+_R["manifest"]["judge_model"], "j11_coding_runs (22 candidates)",
          "37", f"{_tot:,}", "design synthesis + Tier-2 prototype pending", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Describes the correctness and cost of a measurement pipeline, not population-level treatment '
             'effects. This is not medical advice.</div>'))
'''.replace("__DB__", DB)


def main():
    cells = [
        ("md", FRAME), ("code", LOAD),
        ("md", S1), ("code", S1_CODE),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", S4),
        ("md", S5), ("code", S5_CODE),
        ("md", S6),
        ("md", LIM), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title=TITLE)
    html = execute_and_export(nb, "notebooks/validation/j11_value_error_taxonomy", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
