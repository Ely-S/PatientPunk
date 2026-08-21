"""Parse pipeline B records.csv: per-compound outcomes, fill rates, doses."""
import csv, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rows = list(csv.DictReader(open("source_B/records.csv", encoding="utf-8")))
META = {"author_hash","source","text_count","schema_id","extraction_method","extracted_at"}
fields = [k for k in rows[0] if k not in META]
print(f"{len(rows):,} records | {len(fields)} clinical fields\n")

fill = collections.Counter()
for r in rows:
    for k in fields:
        if (r.get(k) or "").strip():
            fill[k] += 1
print("FIELD FILL RATES (top 12)")
for k, v in fill.most_common(12):
    print(f"  {k:26s} {v:4,}  {100*v/len(rows):5.1f}%")

# treatment_outcome format: "drug: outcome[: detail] | drug: outcome..."
DMA   = re.compile(r"(?i)\b4[ '’]?-?\s?dma|eutropoflav")
PLAIN = re.compile(r"(?i)tropoflavin|dihydroxyflavone|\b7[ .,'-]{0,2}8[ .,'-]{0,2}dhf\b|\bdhf\b")
per = {"7,8-DHF": collections.Counter(), "4'-DMA": collections.Counter()}
users = {"7,8-DHF": set(), "4'-DMA": set()}
detail = {"7,8-DHF": collections.Counter(), "4'-DMA": collections.Counter()}

for r in rows:
    for entry in (r.get("treatment_outcome") or "").split("|"):
        e = entry.strip()
        if not e: continue
        parts = [p.strip() for p in e.split(":")]
        drug = parts[0]
        outcome = parts[1] if len(parts) > 1 else ""
        rest = ": ".join(parts[2:]) if len(parts) > 2 else ""
        which = "4'-DMA" if DMA.search(drug) else ("7,8-DHF" if PLAIN.search(drug) else None)
        if not which or not outcome: continue
        per[which][outcome.lower()] += 1
        users[which].add(r["author_hash"])
        if rest: detail[which][rest.lower()] += 1

print("\nOUTCOMES BY COMPOUND  (pipeline B separates these; pipeline A cannot)")
for k in ("7,8-DHF", "4'-DMA"):
    tot = sum(per[k].values())
    if not tot: continue
    print(f"\n  {k}  —  {tot} outcome entries from {len(users[k])} authors")
    for o, n in per[k].most_common():
        print(f"     {o:16s} {n:4,}  {100*n/tot:5.1f}%")
    if detail[k]:
        print(f"     what it helped/affected: {', '.join(d for d,_ in detail[k].most_common(6))}")

doses = collections.Counter()
for r in rows:
    for d in (r.get("dosage") or "").split("|"):
        d = d.strip().lower()
        if d: doses[d] += 1
print(f"\nDOSAGES RECORDED ({sum(doses.values())} entries, top 12)")
for d, n in doses.most_common(12):
    print(f"  {d:22s} {n:3,}")
