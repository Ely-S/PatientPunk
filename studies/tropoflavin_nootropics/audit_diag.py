"""Diagonal cells of the side-effect-by-indication table, decircularized.

The indication regexes and the side-effect canonicalizer share vocabulary, so
naming a side effect tags the author into that side effect's own indication
column. Here the indication is read only from sentences that do not describe an
outcome, so "it made me tired" can no longer file someone under energy/fatigue.
"""
import sqlite3, json, re, sys, collections
from study_support import StudyPaths, readonly_sqlite_uri

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SIG={"strong":3,"moderate":2,"weak":1,"n/a":0,None:0,"":0}
COND={"depression / mood":r"\bdepress|\bantidepress|\bmood\b|anhedoni","anxiety":r"\banxiet|\banxious\b|\bpanic\b",
 "focus / cognition":r"\bfocus\b|\bconcentrat|\bcognit|\bbrain fog\b|\bclarity\b|\bproductiv",
 "memory / learning":r"\bmemory\b|\brecall\b|\blearning\b","sleep":r"\bsleep\b|\binsomnia\b",
 "energy / fatigue":r"\benergy\b|\bfatigue\b|\btired\b|\bstamina\b",
 "neurogenesis / BDNF":r"\bbdnf\b|\btrkb\b|neurogenes|neuroplastic|\brewir"}
CRX={k:re.compile(v,re.I) for k,v in COND.items()}
SE_CANON=[(re.compile(p,re.I),l) for p,l in [
 (r"insomnia|sleep (issue|disrupt|disturb|problem)|can'?t sleep|trouble sleeping|poor sleep","insomnia / sleep disruption"),
 (r"headache|migraine","headache / migraine"),(r"hair (loss|thinning|shed)|weak hair|balding","hair loss / thinning"),
 (r"irritab|restless|agitat|overstimulat|jitter|wired|anxious|anxiety|panic","overstimulation / anxiety"),
 (r"appetite|hunger","appetite change"),(r"nausea|stomach|gi\b|diarrh|gut|digest","GI"),
 (r"fatigue|tired|lethargy|sedat|drowsy|sleepy","fatigue / sedation"),
 (r"depress|anhedoni|blunt|apath|emotional","mood flattening / depression"),
 (r"brain fog|cognitive|memory|concentrat|verbal|articulat","cognitive dulling"),
 (r"dizz|lightheaded|vertigo","dizziness"),(r"crash|tolerance|withdraw|dependen|rebound","crash / tolerance / withdrawal"),
 (r"blood pressure|\bbp\b|heart|palpit|tachy","cardiovascular"),(r"vision|visual|aura|eye","visual"),
 (r"rash|itch|allerg|hives","allergic / skin"),(r"libido|sexual|erectile","sexual")]]
def canon(t):
    for rx,l in SE_CANON:
        if rx.search(t): return l
DIAG={"sleep":"insomnia / sleep disruption","anxiety":"overstimulation / anxiety",
 "energy / fatigue":"fatigue / sedation","depression / mood":"mood flattening / depression",
 "focus / cognition":"cognitive dulling","memory / learning":"cognitive dulling"}
# a sentence reporting an outcome cannot establish why someone started
OUT=re.compile(r"\bmade me\b|\bmakes me\b|\bgave me\b|\bgot\b|\bcaused\b|\bcausing\b|\bexacerbat|\bside.?effect|"
 r"\bworsen|\bwore off\b|\bcrash|\bfelt\b|\bfeel\b|\bfeeling\b|\bexperienc|\bresulted\b|\bleft me\b|\bended up\b",re.I)
c=sqlite3.connect(readonly_sqlite_uri(StudyPaths.from_environment().database),uri=True); c.row_factory=sqlite3.Row
rows=list(c.execute("""SELECT r.user_id,r.signal_strength sig,r.side_effects,p.post_date,
 REPLACE(COALESCE(p.title,'')||' '||COALESCE(p.body_text,''),CHAR(10),' ') txt
 FROM treatment_reports r JOIN posts p ON p.post_id=r.post_id"""))
raw=collections.defaultdict(set); clean=collections.defaultdict(set)
rawN=collections.defaultdict(set); cleanN=collections.defaultdict(set)
for r in rows:
    t=re.sub(r"\s+"," ",r["txt"]); u=r["user_id"]
    try: ses=sorted({canon(str(v)) for v in json.loads(r["side_effects"] or "[]")}-{None})
    except Exception: ses=[]
    sents=re.split(r"(?<=[.!?])\s+",t)
    safe=" ".join(s for s in sents if not (OUT.search(s) or any(rx.search(s) for rx,_ in SE_CANON)))
    for cond,rx in CRX.items():
        if rx.search(t):
            rawN[cond].add(u)
            if DIAG.get(cond) in ses: raw[cond].add(u)
        if rx.search(safe):
            cleanN[cond].add(u)
            if DIAG.get(cond) in ses: clean[cond].add(u)
print(f"{'indication':<21}{'diagonal side effect':<30}{'as charted':>12}{'decircularized':>17}")
print("-"*82)
for cond in ("anxiety","sleep","energy / fatigue","depression / mood","focus / cognition","memory / learning"):
    a,b=len(raw[cond]),len(rawN[cond]); x,y=len(clean[cond]),len(cleanN[cond])
    f=f"{100*a/b:.0f}% ({a}/{b})" if b else "-"
    g=f"{100*x/y:.0f}% ({x}/{y})" if y else "-"
    print(f"{cond:<21}{DIAG[cond]:<30}{f:>12}{g:>17}")
