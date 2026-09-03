import re, sqlite3, sys, random

from study_support import (
    DOSE,
    PROXIMITY_ALIAS as ALIAS,
    PROXIMITY_WINDOW as WINDOW,
    UNIT,
    StudyPaths,
    proximity_dose_bin as bin_of,
    readonly_sqlite_uri,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c=sqlite3.connect(readonly_sqlite_uri(StudyPaths.from_environment().database),uri=True); c.row_factory=sqlite3.Row
rows=list(c.execute("""SELECT r.sentiment, COALESCE(p.title,'')||' '||COALESCE(p.body_text,'') txt
                       FROM treatment_reports r JOIN posts p ON p.post_id=r.post_id"""))
hits=[]
for r in rows:
    t=re.sub(r"\s+"," ",r["txt"])
    spans=[m.start() for m in ALIAS.finditer(t)]
    if not spans: continue
    for m in DOSE.finditer(t):
        d=min(abs(m.start()-s) for s in spans)
        if d>WINDOW: continue
        lo,hi,u=m.group(1),m.group(2),m.group(3).lower()
        v=((float(lo)+float(hi))/2 if hi else float(lo))*UNIT[u]
        b=bin_of(v)
        if b: hits.append((b,v,d,r["sentiment"],t[max(0,m.start()-110):m.start()+80]))
random.seed(7)
for want in ("1-9 mg","10-19 mg","100-1000 mg"):
    s=[h for h in hits if h[0]==want]
    print(f"\n{'='*72}\n{want}  —  {len(s)} dose matches\n{'='*72}")
    for b,v,d,sent,q in random.sample(s,min(6,len(s))):
        print(f"\n[{v:g} mg | {d} chars from alias | {sent}]")
        print("  ..."+q.strip()+"...")
