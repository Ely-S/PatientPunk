"""Finish the 2026-11-18 reverse-route LDN pull: authors the post cap never reached.

Reuses the qualifying_authors.json already paid for, so no sampling is repeated.
Starts at author index START (batch 19, the one the old cap cut mid-pagination) and
runs to the end of the list under a larger cap. Writes to its own run dir.
"""
import sys, json, os, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # step1_search.py
import step1_search as s

# The first pass's run folder (qualifying_authors.json): $REVERSE_ROUTE_PRIOR, else the one beside this script.
PRIOR = pathlib.Path(os.environ.get("REVERSE_ROUTE_PRIOR", HERE / "run_reverse_route_20261118T030628Z"))
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
START = int(sys.argv[2]) if len(sys.argv) > 2 else 450      # batch 19 begins here
CAP = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
s.REQUEST_CAP = 400
tok = s.token(); clog = []

qual = json.load(open(PRIOR/"qualifying_authors.json"))
ids = list(qual)[START:]
alias = '(LDN OR naltrexone OR naltrexon OR naltrexona)'
fields = {'max_results': 100, 'tweet.fields': s.FIELDS + ',note_tweet,text',
          'expansions': 'author_id',
          'user.fields': 'created_at,description,public_metrics,username,name,verified'}
print(f"resuming at author {START} of {len(qual)}; {len(ids)} to cover; post cap {CAP}", flush=True)

ldn, lusers, total, cut = [], {}, 0, None
for i in range(0, len(ids), 25):
    if total >= CAP:
        cut = START + i; print('post cap', flush=True); break
    batch = ids[i:i+25]
    q = f"{alias} ({' OR '.join('from:'+x for x in batch)}) -is:retweet"
    nt, pg = None, 0
    while True:
        body = s.get('/tweets/search/all',
                     dict(fields, query=q, start_time='2020-01-01T00:00:00Z',
                          end_time='2025-11-16T00:00:00Z', **({'next_token': nt} if nt else {})),
                     tok, clog)
        pg += 1
        (out/f'ldn_r{START+i:04d}_p{pg}.json').write_text(json.dumps(body, ensure_ascii=False))
        d = body.get('data', []); ldn += d; total += len(d)
        for u in body.get('includes', {}).get('users', []): lusers[u['id']] = u
        nt = body.get('meta', {}).get('next_token')
        if not nt or total >= CAP: break
        time.sleep(1.1)
    print(f"  authors {START+i}-{START+i+len(batch)-1}: running total {total}", flush=True)
    time.sleep(1.1)

json.dump({'posts': ldn, 'users': lusers, 'start': START, 'cap': CAP,
           'cut_at_author': cut, 'requests': len(clog)},
          open(out/'ldn_posts_resume.json', 'w'), ensure_ascii=False)
print(f"\nposts {total} | authors with posts {len({p['author_id'] for p in ldn})} | "
      f"requests {len(clog)} | cost ${total*0.005:.2f}")
if cut: print(f"cap hit again at author {cut}; {len(qual)-cut} still uncovered")
else:   print("every remaining author covered")
