"""Side-effect structure for 7,8-DHF: canonicalised terms, burden, co-occurrence,
and whether the side-effect profile tracks WHY people say they're taking it."""
import sqlite3, json, re, collections, math, sys, itertools
from study_support import StudyPaths, readonly_sqlite_uri

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CANON = [
 (r"insomnia|sleep (issue|disrupt|disturb|problem)|can'?t sleep|trouble sleeping|poor sleep", "insomnia / sleep disruption"),
 (r"headache|migraine", "headache / migraine"),
 (r"hair (loss|thinning|shed)|weak hair|balding", "hair loss / thinning"),
 (r"irritab|restless|agitat|overstimulat|jitter|wired|anxious|anxiety|panic", "overstimulation / anxiety"),
 (r"appetite|hunger", "appetite change"),
 (r"nausea|stomach|gi\b|diarrh|gut|digest", "GI"),
 (r"fatigue|tired|lethargy|sedat|drowsy|sleepy", "fatigue / sedation"),
 (r"depress|anhedoni|blunt|apath|emotional", "mood flattening / depression"),
 (r"brain fog|cognitive|memory|concentrat|verbal|articulat", "cognitive dulling"),
 (r"dizz|lightheaded|vertigo", "dizziness"),
 (r"crash|tolerance|withdraw|dependen|rebound", "crash / tolerance / withdrawal"),
 (r"blood pressure|\bbp\b|heart|palpit|tachy", "cardiovascular"),
 (r"vision|visual|aura|eye", "visual"),
 (r"rash|itch|allerg|hives", "allergic / skin"),
 (r"libido|sexual|erectile", "sexual"),
]
CANON = [(re.compile(p, re.I), lab) for p, lab in CANON]
def canon(term):
    for rx, lab in CANON:
        if rx.search(term): return lab
    return None

COND = {
 "depression / mood":  r"\bdepress|\bantidepress|\bmood\b|anhedoni",
 "anxiety":            r"\banxiet|\banxious\b|\bpanic\b",
 "focus / cognition":  r"\bfocus\b|\bconcentrat|\bcognit|\bbrain fog\b|\bclarity\b|\bproductiv",
 "memory / learning":  r"\bmemory\b|\brecall\b|\blearning\b",
 "sleep":              r"\bsleep\b|\binsomnia\b",
 "energy / fatigue":   r"\benergy\b|\bfatigue\b|\btired\b|\bstamina\b",
 "neurogenesis / BDNF":r"\bbdnf\b|\btrkb\b|neurogenes|neuroplastic|\brewir",
}
CRX = {k: re.compile(v, re.I) for k, v in COND.items()}

c = sqlite3.connect(readonly_sqlite_uri(StudyPaths.from_environment().database), uri=True); c.row_factory = sqlite3.Row
rows = c.execute("""SELECT r.sentiment, r.side_effects, r.user_id, p.title, p.body_text
                    FROM treatment_reports r JOIN posts p ON p.post_id=r.post_id
                    WHERE r.run_id=(SELECT MAX(run_id) FROM treatment_reports)""").fetchall()

recs = []
for r in rows:
    ses = []
    if r["side_effects"] and r["side_effects"] != "[]":
        try: ses = [s for s in (canon(str(x)) for x in json.loads(r["side_effects"])) if s]
        except Exception: pass
    txt = (r["title"] or "") + " " + (r["body_text"] or "")
    conds = [k for k, rx in CRX.items() if rx.search(txt)]
    recs.append(dict(sent=r["sentiment"], ses=sorted(set(ses)), conds=conds, user=r["user_id"]))

n = len(recs); with_se = [r for r in recs if r["ses"]]
print(f"records {n:,} | with >=1 side effect {len(with_se):,} ({100*len(with_se)/n:.1f}%)")
tot = sum(len(r["ses"]) for r in recs)
print(f"canonicalised side-effect mentions {tot} across {len({s for r in recs for s in r['ses']})} categories")
print(f"mean per record (all) {tot/n:.2f} | mean among reporters {tot/len(with_se):.2f}\n")

freq = collections.Counter(s for r in recs for s in r["ses"])
print("SIDE EFFECT FREQUENCY (canonicalised)")
for s, k in freq.most_common():
    print(f"   {s:32s} {k:>4}  {100*k/n:>5.1f}% of records")

print("\nSENTIMENT GIVEN A SIDE EFFECT WAS REPORTED")
for lab, sub in (("reported >=1 side effect", with_se), ("reported none", [r for r in recs if not r["ses"]])):
    cnt = collections.Counter(r["sent"] for r in sub)
    m = len(sub)
    print(f"   {lab:26s} n={m:>4}  positive {100*cnt['positive']/m:>5.1f}%  negative {100*cnt['negative']/m:>5.1f}%")

print("\nCO-OCCURRENCE (pairs appearing together in >=3 records)")
pair = collections.Counter()
for r in recs:
    for a, b in itertools.combinations(r["ses"], 2): pair[tuple(sorted((a,b)))] += 1
for (a,b), k in pair.most_common(12):
    if k < 3: break
    lift = (k/n) / ((freq[a]/n)*(freq[b]/n))
    print(f"   {a[:26]:28s}+ {b[:26]:28s} {k:>3}  lift {lift:>5.1f}x")

print("\nSIDE EFFECT BY STATED CONDITION (share of that condition's records)")
hdr = sorted(COND)
print(f"   {'side effect':30s}" + "".join(f"{c[:11]:>13s}" for c in hdr))
base = {c: sum(1 for r in recs if c in r["conds"]) for c in hdr}
print(f"   {'(records)':30s}" + "".join(f"{base[c]:>13,}" for c in hdr))
for s, _ in freq.most_common(8):
    line = f"   {s[:30]:30s}"
    for cnd in hdr:
        d = base[cnd]
        k = sum(1 for r in recs if cnd in r["conds"] and s in r["ses"])
        line += f"{(f'{100*k/d:.0f}%' if d>=25 else '-'):>13s}"
    print(line)
