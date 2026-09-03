"""Purpose/context breakdown for 7,8-DHF mentions. See NOTES.md."""
import json, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PAT = re.compile(r"(?i)(tropoflavin|hydroxyflavone|\b7[ .,'-]{0,2}8[ .,'-]{0,2}dhf\b|\bdhf\b)")
corpus = json.load(open("studies/tropoflavin_nootropics/source/subreddit_posts.json", encoding="utf-8"))

items = []
for p in corpus:
    t = ((p.get("title") or "") + " " + (p.get("body") or "")).strip()
    if PAT.search(t):
        items.append(("post", t))
    for c in p["comments"]:
        b = (c.get("body") or "").strip()
        if PAT.search(b):
            items.append(("comment", b))
print(f"{len(items):,} items mention it\n")

PURPOSE = {
 "depression / mood":      r"\bdepress|\bantidepress|\bmood\b|\bsad\b|\bmdd\b|\bdysthym|anhedoni",
 "anxiety":                r"\banxiet|\banxious\b|\bpanic\b|\bsocial anxiety\b",
 "memory / learning":      r"\bmemory\b|\brecall\b|\blearning\b|\bmemoriz|\bretention\b",
 "focus / cognition":      r"\bfocus\b|\bconcentrat|\bcognit|\bbrain fog\b|\bclarity\b|\bproductiv",
 "neurogenesis / BDNF":    r"\bbdnf\b|\btrkb\b|neurogenes|neuroplastic|\bsynaptogenes|\brewir",
 "neuroprotection / repair": r"neuroprotect|\brepair\b|\brecover\w* (from|my) brain|\bregenerat|\bheal\w* (my |the )?brain",
 "TBI / concussion":       r"\btbi\b|concussion|\bhead injury\b|traumatic brain",
 "drug damage / PSSD":     r"\bpssd\b|\bpfs\b|post.?ssri|\bhppd\b|\bneurotox|damage from|\bexcitotox|\bpost.?fin",
 "ADHD":                   r"\badhd\b|\badd\b(?!ed)|\battention deficit",
 "Alzheimer / dementia":   r"\balzheim|\bdementia\b|cognitive decline|\bmci\b",
 "exercise mimetic / fat loss": r"exercise mimetic|\bfat loss\b|\bweight loss\b|\bmetabol|\bobes|\bglucose\b|\binsulin\b",
 "neuropathy / nerve":     r"\bneuropath|\bnerve (damage|pain|regen)|\btinnitus\b|\bhearing\b",
 "autism / Rett":          r"\bautis|\brett\b|\bfragile x\b",
 "sleep":                  r"\bsleep\b|\binsomnia\b|\bdream",
 "libido / sexual":        r"\blibido\b|\bsexual\b|\berectile\b|\borgasm",
 "stimulant recovery":     r"\bstimulant\b.{0,30}(recover|damage|crash)|amphetamine.{0,30}(damage|recover)|\btolerance\b",
}
counts = {k: 0 for k in PURPOSE}
for _, t in items:
    for k, p in PURPOSE.items():
        if re.search(p, t, re.I):
            counts[k] += 1
print("STATED CONTEXT (share of the %d mentioning items)" % len(items))
for k, v in sorted(counts.items(), key=lambda x: -x[1]):
    bar = "#" * int(40 * v / max(counts.values()))
    print(f"  {k:30s} {v:5,}  {100*v/len(items):5.1f}%  {bar}")

CO = {
 "4'-DMA-7,8-DHF": r"4[ '’]?-?\s?dma|eutropoflavin",
 "noopept": r"\bnoopept\b", "semax": r"\bsemax\b", "selank": r"\bselank\b",
 "lion's mane": r"lion'?s? mane|hericium", "cerebrolysin": r"\bcerebrolysin\b",
 "dihexa": r"\bdihexa\b", "NSI-189": r"\bnsi[- ]?189\b", "9-MBC": r"\b9[- ]?mbc\b",
 "racetams": r"\bpiracetam\b|\baniracetam\b|\boxiracetam\b|\bphenylpiracetam\b|\bpramiracetam\b",
 "psilocybin/LSD": r"\bpsilocybin\b|\blsd\b|microdos", "ketamine": r"\bketamine\b",
 "uridine": r"\buridine\b", "agmatine": r"\bagmatine\b", "bromantane": r"\bbromantane\b",
 "creatine": r"\bcreatine\b", "magnesium": r"\bmagnesium\b", "curcumin": r"\bcurcumin\b|turmeric",
}
cc = collections.Counter()
for _, t in items:
    for k, p in CO.items():
        if re.search(p, t, re.I):
            cc[k] += 1
print("\nMOST CO-MENTIONED SUBSTANCES")
for k, v in cc.most_common(12):
    print(f"  {k:22s} {v:5,}  {100*v/len(items):5.1f}%")

DOSE = collections.Counter(re.findall(r"(?i)(\d+\.?\d*)\s?(mg|g|gram)s?\b", " ".join(t for _, t in items)))
print("\nMOST-CITED DOSES (any substance in these items — indicative only)")
for (n, u), v in DOSE.most_common(10):
    print(f"  {n}{u:5s} {v:4,}")
