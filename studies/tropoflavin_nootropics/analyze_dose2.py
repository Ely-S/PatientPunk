"""Dose-stratified 7,8-DHF, strict attribution.

Proximity windows fail on r/Nootropics: a 150-char window around an alias
typically spans 3-5 other compounds, each with its own dose (see audit_dose.py).
A dose counts here only if everything between it and the alias is connective
filler, so "7,8-DHF, 25 mg" binds but "7,8-DHF ... 10 mg Noopept" does not.
"""
from __future__ import annotations
import json, re, sqlite3, sys, collections, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SIG = {"strong":3,"moderate":2,"weak":1,"n/a":0,None:0,"":0}
ALIAS = re.compile(r"(?i)(tropoflavin|eutropoflavin\w*|(?:4.?dma.?)?7[ .,'-]{0,2}8[ .,'-]{0,2}dhf|7[ .,'-]{0,2}8[ .,'-]{0,2}dihydroxyflavone|dihydroxyflavone)")
DOSE  = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(?:(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*)?(mg|mcg|ug|µg|g|gram|grams)\b")
UNIT  = {"mg":1.0,"mcg":.001,"ug":.001,"µg":.001,"g":1000.,"gram":1000.,"grams":1000.}

# only these may sit between the alias and its dose
FILLER = {"a","an","and","around","at","about","approx","approximately","av","average",
          "caps","capsule","capsules","daily","day","days","dose","dosed","doses","dosing",
          "each","every","for","from","g","have","i","in","is","it","just","maybe","mg","my",
          "night","of","on","once","one","or","per","pill","pills","powder","roughly","sublingual",
          "sublingually","take","taken","taking","tablet","the","to","total","twice","up","use",
          "used","using","was","were","with","x","was","been","only","now","started","start",
          "morning","evening","am","pm","currently","usually","typically","about","its","this"}
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]{1,}")


def bind(text: str):
    """Doses in mg that are attributable to a 7,8-DHF alias."""
    out = []
    spans = [(m.start(), m.end()) for m in ALIAS.finditer(text)]
    for m in DOSE.finditer(text):
        for s0, s1 in spans:
            gap = text[s1:m.start()] if m.start() >= s1 else text[m.end():s0]
            if len(gap) > 60:
                continue
            if any(w.lower() not in FILLER for w in WORD.findall(gap)):
                continue
            lo, hi, u = m.group(1), m.group(2), m.group(3).lower()
            v = ((float(lo)+float(hi))/2 if hi else float(lo)) * UNIT[u]
            out.append(v)
            break
    return out


def bin_of(mg):
    if not 0.5 <= mg <= 1000: return None
    return ("<10 mg" if mg < 10 else "10-24 mg" if mg < 25 else
            "25-49 mg" if mg < 50 else "50+ mg")


ORDER = ["<10 mg","10-24 mg","25-49 mg","50+ mg"]
c = sqlite3.connect("file:noots.db?mode=ro", uri=True); c.row_factory = sqlite3.Row
rows = list(c.execute("""SELECT r.user_id,r.sentiment,r.signal_strength,r.side_effects,r.post_date_x,r.txt FROM (
      SELECT r.user_id,r.sentiment,r.signal_strength,r.side_effects,p.post_date post_date_x,
             REPLACE(COALESCE(p.title,'')||' '||COALESCE(p.body_text,''),CHAR(10),' ') txt
      FROM treatment_reports r JOIN posts p ON p.post_id=r.post_id) r"""))

recs, quotes = [], []
for r in rows:
    t = re.sub(r"\s+", " ", r["txt"])
    ds = [b for b in (bin_of(x) for x in bind(t)) if b]
    if not ds: continue
    b = min(set(ds), key=ORDER.index)
    recs.append((r["user_id"], b, r["sentiment"], r["signal_strength"], r["side_effects"], r["post_date_x"]))
    if len(quotes) < 14:
        m = ALIAS.search(t); quotes.append((b, t[max(0,m.start()-40):m.start()+90]))

print(f"{len(rows):,} reports -> {len(recs):,} with a dose bound to the alias "
      f"({100*len(recs)/len(rows):.1f}%)\n")
print("sample of what now binds:")
for b, q in quotes[:8]: print(f"  [{b:<9}] ...{q.strip()}...")

best = {}
for u,b,s,g,se,pd_ in sorted(recs, key=lambda x:(x[5] or 0, SIG.get(x[3],0)), reverse=True):
    best.setdefault(u,(b,s,se))
by = collections.defaultdict(list)
for b,s,se in best.values(): by[b].append((s,se))


def wilson(k,n,z=1.96):
    if not n: return (0.,0.)
    p=k/n; d=1+z*z/n
    ctr=(p+z*z/(2*n))/d; hw=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (100*(ctr-hw),100*(ctr+hw))

print(f"\n{'dose':<11}{'users':>6}{'positive':>10}{'  95% CI':>17}{'  neg':>7}{'  any SE':>9}")
print("-"*62)
for b in ORDER:
    v=by.get(b,[]); n=len(v)
    if not n: continue
    pos=sum(1 for s,_ in v if s=="positive"); neg=sum(1 for s,_ in v if s=="negative")
    se=sum(1 for _,x in v if x and x not in ("[]","none",""))
    lo,hi=wilson(pos,n)
    print(f"{b:<11}{n:>6}{100*pos/n:>9.1f}%   [{lo:>5.1f},{hi:>6.1f}]{100*neg/n:>6.1f}%{100*se/n:>8.1f}%")
tn=sum(len(v) for v in by.values()); tp=sum(1 for v in by.values() for s,_ in v if s=="positive")
ts=sum(1 for v in by.values() for _,x in v if x and x not in ("[]","none",""))
print("-"*62)
print(f"{'all dosed':<11}{tn:>6}{100*tp/tn:>9.1f}%{'':>17}{'':>6}{100*ts/tn:>8.1f}%")

print("\nside effects named, by bin")
for b in ORDER:
    v=by.get(b,[]);  cnt=collections.Counter(); w=0
    for _,x in v:
        if not x or x in ("[]","none",""): continue
        try: items=json.loads(x)
        except Exception: continue
        if items: w+=1
        for i in items: cnt[str(i).strip().lower()]+=1
    if v: print(f"  {b:<9} {w}/{len(v)} users: " + (", ".join(f"{k}({n})" for k,n in cnt.most_common(5)) or "—"))
