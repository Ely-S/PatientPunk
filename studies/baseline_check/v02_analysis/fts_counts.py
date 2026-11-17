import sqlite3, sys
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
terms = {
 "crash": '"crash" OR "crashed" OR "crashes" OR "crashing"',
 "PEM": '"pem" OR "post exertional" OR "post-exertional"',
 "baseline": '"baseline"',
 "pacing": '"pacing" OR "pace myself"',
 "push-crash": '"push crash" OR "boom bust" OR "push and crash"',
 "energy envelope": '"energy envelope" OR "envelope"',
 "spoons": '"spoons" OR "spoon theory"',
 "good days/bad days": '"good days" OR "bad days" OR "good day" OR "bad day"',
 "percent of normal": '"percent" OR "per cent"',  # refined below via regex
 "housebound": '"housebound"',
 "bedbound": '"bedbound" OR "bed bound" OR "bedridden"',
 "upright time": '"upright"',
 "steps": '"steps a day" OR "steps per day" OR "step count" OR "steps"',
 "heart rate": '"heart rate" OR "hr" OR "bpm"',
 "HRV": '"hrv"',
 "visible app": '"visible app" OR "visible plus" OR "welltory" OR "garmin" OR "oura" OR "fitbit" OR "whoop"',
 "shower": '"shower" OR "showering"',
 "cook": '"cook" OR "cooking"',
 "work": '"work full time" OR "back to work" OR "return to work" OR "working again"',
 "remission": '"remission" OR "recovered" OR "recovery"',
 "flare": '"flare" OR "flare up" OR "relapse"',
 "brain fog": '"brain fog" OR "fog"',
 "SF-36": '"sf36" OR "sf 36" OR "sf-36"',
 "PROMIS": '"promis"',
 "Chalder": '"chalder"',
 "questionnaire/survey": '"questionnaire" OR "questionnaires"',
 "DSQ": '"depaul"',
 "FUNCAP": '"funcap"',
 "Bell scale": '"bell scale" OR "bell disability" OR "bell score"',
 "symptom diary/tracking": '"symptom diary" OR "symptom tracker" OR "symptom tracking" OR "track my symptoms" OR "tracking symptoms"',
}
print(f"{'concept':28s} {'posts':>8s} {'comments':>9s}")
for k, q in terms.items():
    p = db.execute("select count(*) from posts_fts where posts_fts match ?", (q,)).fetchone()[0]
    c = db.execute("select count(*) from comments_fts where comments_fts match ?", (q,)).fetchone()[0]
    print(f"{k:28s} {p:8d} {c:9d}", flush=True)
