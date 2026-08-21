import sqlite3, json, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SIG={"strong":3,"moderate":2,"weak":1,"n/a":0,None:0,"":0}
COND=re.compile(r"\benergy\b|\bfatigue\b|\btired\b|\bstamina\b",re.I)
SE  =re.compile(r"fatigue|tired|lethargy|sedat|drowsy|sleepy",re.I)
c=sqlite3.connect("file:noots.db?mode=ro",uri=True); c.row_factory=sqlite3.Row
rows=list(c.execute("""SELECT r.user_id,r.sentiment,r.signal_strength sig,r.side_effects,p.post_date,
  REPLACE(COALESCE(p.title,'')||' '||COALESCE(p.body_text,''),CHAR(10),' ') txt
  FROM treatment_reports r JOIN posts p ON p.post_id=r.post_id"""))
hits=[]
for r in rows:
    t=re.sub(r"\s+"," ",r["txt"])
    if not COND.search(t): continue
    try: ses=json.loads(r["side_effects"] or "[]")
    except Exception: ses=[]
    fat=[s for s in ses if SE.search(str(s))]
    if fat: hits.append((r["user_id"],r["post_date"] or 0,SIG.get(r["sig"],0),fat,t))
seen={}
for u,d,g,fat,t in sorted(hits,key=lambda x:(x[1],x[2]),reverse=True): seen.setdefault(u,(fat,t))
print(f"{len(seen)} distinct users in the energy/fatigue x fatigue-sedation cell\n")
for i,(u,(fat,t)) in enumerate(seen.items(),1):
    m=SE.search(t); w=t[max(0,m.start()-160):m.start()+160] if m else t[:300]
    # does the indication word appear ONLY inside the side-effect description?
    print(f"--- {i}. side_effects={fat}")
    print(f"    ...{w.strip()}...\n")
