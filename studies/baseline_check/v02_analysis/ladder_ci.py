import json, csv, sys, collections, re, statistics as st
csv.field_size_limit(sys.maxsize)
score = {"bedbound":1,"housebound":2,"severe":3,"moderate":4,"mild":5,"mostly_functional":6}
tier = {}
for r in csv.DictReader(open(sys.argv[1])):
    xs = [x.strip().lower() for x in r["functional_status_tier"].split("|") if x.strip()]
    if len(xs) == 1: tier[r["author_hash"]] = score[xs[0]]
RUNGS = {
 "sit up / sit upright": r"^(?:even )?sit (?:up|upright)",
 "eat / feed myself": r"^(?:even )?(?:feed myself|eat (?:a meal|by myself|on my own|solid))",
 "talk / have a conversation": r"^(?:even )?(?:talk|speak|have a conversation|hold a conversation)",
 "listen to music / audio": r"^(?:even )?listen to (?:music|audiobooks?|podcasts?)",
 "look at a screen / phone": r"^(?:even )?(?:look at (?:a |my )?(?:screen|phone)|use (?:my|a) phone|text)",
 "watch TV": r"^(?:even )?watch (?:tv|television|a show|shows|movies?|a movie)",
 "get out of bed": r"^(?:even )?(?:get out of bed|leave (?:my )?bed|get up)",
 "shower / wash hair": r"^(?:even )?(?:shower|take a shower|wash my hair|bathe)",
 "read": r"^(?:even )?read(?: a book| books)?\b",
 "cook a meal": r"^(?:even )?(?:cook|make (?:a meal|dinner|food))",
 "stand for long": r"^(?:even )?stand (?:for|long|up for)",
 "leave the house": r"^(?:even )?(?:leave (?:the|my) house|go outside|leave home)",
 "grocery shop": r"^(?:even )?(?:go (?:grocery )?shopping|do (?:the |my )?grocer|go to the (?:store|grocery))",
 "drive": r"^(?:even )?drive",
 "walk around the block": r"^(?:even )?(?:walk (?:around|to|a block|down)|go (?:for )?(?:a )?walks?)",
 "socialise / see friends": r"^(?:even )?(?:see (?:my )?friends|socialize|socialise|go out with)",
 "work part time": r"^(?:even )?work part",
 "work full time": r"^(?:even )?(?:work full|go back to work full)",
 "exercise / gym": r"^(?:even )?(?:exercise|work ?out|go to the gym|lift weights)",
 "run / hike": r"^(?:even )?(?:run|jog|hike|go running|go hiking)",
}
R = {k: re.compile(v) for k, v in RUNGS.items()}
neg, pos = collections.defaultdict(set), collections.defaultdict(set)
for line in open("milestones.jsonl"):
    r = json.loads(line)
    for k, rx in R.items():
        if rx.search(r["ph"]):
            (neg if r["s"] < 0 else pos)[k].add(r["a"])
rows = []
for k in RUNGS:
    sn = [tier[a] for a in neg[k] if a in tier]; sp = [tier[a] for a in pos[k] if a in tier]
    if len(sn) >= 15:
        rows.append((st.mean(sn), k, len(neg[k]), len(sn), 1.96*st.stdev(sn)/len(sn)**0.5, len(sp)))
print("Mean severity tier (1=bedbound .. 6=mostly functional) of authors who say they CAN'T do it — lower = a lower rung")
print(f"{'activity':28s} {'cant_tier':>9s} {'n_cant':>7s} {'can_now_tier':>12s} {'n_can':>6s}")
for m, k, n, nt, mp, np_ in sorted(rows):
    print(f"{k:28s} {m:9.2f} {nt:7d} ±{mp:.2f}       {np_:6d}")
