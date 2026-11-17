import json, sys
# usage: python3 add.py <<< "id|dc(1/0)|change|captured|captured_by(comma)|missing|severity"
strata = {r["id"]: r["stratum"] for r in json.load(open("sample.json"))}
with open("coded.jsonl", "a") as f:
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        i, dc, ch, cap, by, miss, sev = [x.strip() for x in line.split("|")]
        f.write(json.dumps({"id": i, "stratum": strata[i], "describes_change": dc == "1", "change": ch or None,
            "captured": cap or None, "captured_by": [x.strip() for x in by.split(",") if x.strip()],
            "missing": miss or None, "severity": sev or "unstated"}) + "\n")
