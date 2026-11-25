#!/usr/bin/env python3
"""Tier 1 bot / coordination signals for Twitter report + control authors.
Offline only. Usage:
  python -I tier1/tier1_run.py <author_list.json> <corpus_dir> <out_dir>
"""
import sys, os, json, glob, re, html, csv, math
from collections import defaultdict, Counter
from datetime import datetime, timezone

AUTHOR_LIST, CORPUS_DIR, OUT_DIR = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT_DIR, exist_ok=True)

URL_RE = re.compile(r'https?://\S+')
MENTION_RE = re.compile(r'@\w+')
HASHTAG_RE = re.compile(r'#\w+')
LEAD_MENTION_RE = re.compile(r'^(?:\s*@\w+\s*)+')
NONALNUM_RE = re.compile(r'[^a-z0-9 ]+')
MIN_KEY_CHARS = 10          # exact-key clusters below this length are ignored (trivial "thank you"-type text)
SHINGLE_K = 5
SHINGLE_JACCARD = 0.6
SHINGLE_POSTING_CAP = 300   # shingles occurring in more tweets than this are skipped as candidates (exact key catches those)

def parse_ts(s):
    return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).timestamp()

def norm_key(text):
    t = html.unescape(text)
    t = URL_RE.sub(' ', t)
    t = MENTION_RE.sub(' ', t)
    t = t.lower()
    t = NONALNUM_RE.sub(' ', t)
    return ' '.join(t.split())

def longform_key(text):
    t = html.unescape(text)
    t = URL_RE.sub(' ', t); t = HASHTAG_RE.sub(' ', t); t = MENTION_RE.sub(' ', t)
    return ' '.join(t.split())

# ---------------- load corpus ----------------
tweets = {}                 # tweet_id -> dict
tweet_files = defaultdict(set)
for f in sorted(glob.glob(os.path.join(CORPUS_DIR, '*.json'))):
    with open(f, encoding='utf-8') as fh:
        d = json.load(fh)
    if not isinstance(d, dict) or not isinstance(d.get('tweets'), list):
        continue
    base = os.path.basename(f)
    for t in d['tweets']:
        if not isinstance(t, dict) or 'tweet_id' not in t:
            continue
        tid = str(t['tweet_id'])
        tweet_files[tid].add(base)
        if tid in tweets:
            continue
        txt = t.get('text') or ''
        m = t.get('metrics') or {}
        tweets[tid] = dict(
            id=tid, text=txt, ts=parse_ts(t['created_at']), author=str(t.get('author_id')),
            username=t.get('author_username') or '', name=t.get('author_name') or '',
            verified=bool(t.get('author_verified')), key=norm_key(txt), lkey=longform_key(txt),
            n_hash=len(HASHTAG_RE.findall(txt)), n_ment=len(MENTION_RE.findall(txt)),
            lead_ment=len(MENTION_RE.findall(LEAD_MENTION_RE.match(txt).group(0))) if LEAD_MENTION_RE.match(txt) else 0,
            urls=URL_RE.findall(txt), is_reply=txt.startswith('@'),
            first_handle=(MENTION_RE.match(txt).group(0).lower() if txt.startswith('@') and MENTION_RE.match(txt) else None),
        )
print(f'unique tweets: {len(tweets)}', file=sys.stderr)
by_author = defaultdict(list)
for t in tweets.values():
    by_author[t['author']].append(t)
for v in by_author.values():
    v.sort(key=lambda x: x['ts'])

# ---------------- author sets ----------------
with open(AUTHOR_LIST, encoding='utf-8') as fh:
    AL = json.load(fh)
report_authors = AL['report_authors']
control = AL['control_non_report_authors']
targets = {}  # author_id -> dict(group, drugs, sentiments, reports, username)
for aid, info in report_authors.items():
    targets[str(aid)] = dict(group='report', drugs=sorted(info.get('drugs', [])), sentiments=info.get('sentiments', {}),
                             reports=info.get('reports', 0), username=info.get('username', ''))
for drug, ids in control.items():
    for aid in ids:
        aid = str(aid)
        if aid in targets and targets[aid]['group'] == 'report':
            continue  # a report author for the other drug stays a report author
        if aid in targets:
            targets[aid]['drugs'] = sorted(set(targets[aid]['drugs']) | {drug})
        else:
            targets[aid] = dict(group='control', drugs=[drug], sentiments={}, reports=0, username='')
print(f'targets: {len(targets)} (report {sum(1 for v in targets.values() if v["group"]=="report")})', file=sys.stderr)

# ---------------- exact-key clusters (whole corpus) ----------------
key_members = defaultdict(list)
for t in tweets.values():
    if len(t['key']) >= MIN_KEY_CHARS:
        key_members[t['key']].append(t)
key_stats = {k: (len(v), len({x['author'] for x in v})) for k, v in key_members.items()}

# ---------------- long-form identical (NCRI) ----------------
lkey_authors = defaultdict(set)
for t in tweets.values():
    if len(t['lkey']) >= 20:
        lkey_authors[t['lkey']].add(t['author'])

# ---------------- shingle clusters (inverted index + union-find) ----------------
shingles = {}
index = defaultdict(list)
for t in tweets.values():
    w = t['key'].split()
    if len(w) < SHINGLE_K:
        continue
    s = {' '.join(w[i:i+SHINGLE_K]) for i in range(len(w)-SHINGLE_K+1)}
    shingles[t['id']] = s
    for sh in s:
        index[sh].append(t['id'])
parent = {}
def find(x):
    while parent.get(x, x) != x:
        parent[x] = parent.get(parent[x], parent[x]); x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb
n_pairs = 0
for tid, s in shingles.items():
    cand = Counter()
    for sh in s:
        post = index[sh]
        if len(post) > SHINGLE_POSTING_CAP:
            continue
        for o in post:
            if o > tid: cand[o] += 1   # each pair once
    a = len(s)
    for o, shared in cand.items():
        b = len(shingles[o])
        if shared / (a + b - shared) >= SHINGLE_JACCARD:
            union(tid, o); n_pairs += 1
sh_cluster = defaultdict(list)
for tid in shingles:
    sh_cluster[find(tid)].append(tid)
sh_cluster = {r: v for r, v in sh_cluster.items() if len(v) >= 2}
tid_to_shc = {tid: r for r, v in sh_cluster.items() for tid in v}
sh_stats = {r: (len(v), len({tweets[x]['author'] for x in v})) for r, v in sh_cluster.items()}
print(f'shingle pairs {n_pairs}, clusters>=2: {len(sh_cluster)}', file=sys.stderr)

# ---------------- same-minute reply coordination ----------------
minute_handle = defaultdict(set)
for t in tweets.values():
    if t['first_handle']:
        minute_handle[(t['first_handle'], int(t['ts'] // 60))].add(t['author'])

# ---------------- shared-link coordination ----------------
url_posts = defaultdict(list)
for t in tweets.values():
    for u in set(t['urls']):
        url_posts[u].append((t['ts'], t['author'], t['id']))
link_groups = {}   # url -> set(authors) in some 24h window with >=3 tweets & >=2 authors
for u, posts in url_posts.items():
    if len(posts) < 3 or len({p[1] for p in posts}) < 2:
        continue
    posts.sort()
    grp = set(); j = 0
    for i in range(len(posts)):
        while posts[i][0] - posts[j][0] > 86400: j += 1
        win = posts[j:i+1]
        if len(win) >= 3 and len({p[1] for p in win}) >= 2:
            grp |= {p[1] for p in win}
    if grp:
        link_groups[u] = grp
author_links = defaultdict(set)
for u, g in link_groups.items():
    for a in g: author_links[a].add(u)

# ---------------- per-author features ----------------
rows = []
for aid, meta in targets.items():
    tw = by_author.get(aid, [])
    n = len(tw)
    r = dict(author_id=aid, username=meta['username'] or (tw[0]['username'] if tw else ''),
             author_name=(tw[0]['name'] if tw else ''), group=meta['group'], drugs='+'.join(meta['drugs']),
             reports=meta['reports'],
             s_pos=meta['sentiments'].get('positive', 0), s_neg=meta['sentiments'].get('negative', 0),
             s_mix=meta['sentiments'].get('mixed', 0), s_neu=meta['sentiments'].get('neutral', 0),
             n_tweets_in_corpus=n)
    files = set()
    for t in tw: files |= tweet_files[t['id']]
    r['n_distinct_keyword_files'] = len(files)
    if n:
        span = (tw[-1]['ts'] - tw[0]['ts']) / 86400
        days = {int(t['ts'] // 86400) for t in tw}
        r['span_days'] = round(span, 2); r['tweets_per_active_day'] = round(n / len(days), 2)
        uname = tw[0]['username']
        r['handle_digit_suffix'] = int(bool(re.search(r'\d{5,}$', uname)))
        r['name_empty'] = int((tw[0]['name'].strip() == '') or (tw[0]['name'].strip().lower() == uname.lower()))
        r['verified'] = int(tw[0]['verified'])
        r['reply_share'] = round(sum(t['is_reply'] for t in tw) / n, 3)
        r['url_share'] = round(sum(bool(t['urls']) for t in tw) / n, 3)
        r['hashtag_heavy'] = round(sum(t['n_hash'] >= 5 for t in tw) / n, 3)
        r['mention_heavy'] = round(sum(t['lead_ment'] >= 5 for t in tw) / n, 3)
    else:
        for k in ('span_days', 'tweets_per_active_day', 'reply_share', 'url_share', 'hashtag_heavy', 'mention_heavy'): r[k] = ''
        r['handle_digit_suffix'] = int(bool(re.search(r'\d{5,}$', r['username'])))
        r['name_empty'] = ''; r['verified'] = ''
    # exact-key clusters
    best = (0, 0); copyp = 0
    own = Counter(t['key'] for t in tw if len(t['key']) >= MIN_KEY_CHARS)
    for t in tw:
        st = key_stats.get(t['key'])
        if st:
            if st > best: best = st
            if st[0] >= 3 and st[1] >= 2: copyp = 1
    r['dup_text_cluster_tweets'], r['dup_text_cluster_authors'] = best
    r['copypasta_author'] = copyp
    r['self_repeat'] = int(any(c >= 3 for c in own.values()))
    # shingle clusters
    sbest = (0, 0); scopy = 0
    for t in tw:
        c = tid_to_shc.get(t['id'])
        if c:
            st = sh_stats[c]
            if st > sbest: sbest = st
            if st[0] >= 3 and st[1] >= 2: scopy = 1
    r['shingle_cluster_tweets'], r['shingle_cluster_authors'] = sbest
    r['shingle_copypasta'] = scopy
    r['shingle_adds_cluster'] = int(scopy and not copyp)
    # burst
    burst = 0; ts = [t['ts'] for t in tw]; j = 0
    for i in range(n):
        while ts[i] - ts[j] > 600: j += 1
        burst = max(burst, i - j + 1)
    r['burst_10min_max'] = burst
    r['same_minute_pairs'] = sum(len(minute_handle[(t['first_handle'], int(t['ts'] // 60))]) - 1 for t in tw if t['first_handle'])
    # shared links
    r['shared_link_coord'] = int(aid in author_links)
    r['shared_link_urls'] = ' '.join(sorted(author_links.get(aid, [])))
    # reply target concentration
    targ = Counter(t['first_handle'] for t in tw if t['first_handle'])
    r['n_replies'] = sum(targ.values())
    if targ:
        top, c = targ.most_common(1)[0]
        r['reply_target_top'] = top; r['reply_target_concentration'] = round(c / sum(targ.values()), 3)
    else:
        r['reply_target_top'] = ''; r['reply_target_concentration'] = ''
    # NCRI rules
    r['identical_longform'] = int(any(len(t['lkey']) >= 20 and len(lkey_authors[t['lkey']] - {aid}) > 0 for t in tw))
    r['promotional'] = int(any(t['n_hash'] >= 10 or t['n_ment'] >= 10 or t['n_hash'] + t['n_ment'] >= 15 for t in tw))
    flags = []
    if r['handle_digit_suffix']: flags.append('digit_suffix')
    if r['name_empty'] == 1: flags.append('name_empty')
    if r['copypasta_author']: flags.append('copypasta')
    if r['self_repeat']: flags.append('self_repeat')
    if r['shared_link_coord']: flags.append('shared_link')
    if r['burst_10min_max'] >= 3: flags.append('burst3')
    if r['promotional']: flags.append('promotional')
    if r['identical_longform']: flags.append('identical_longform')
    if r['n_replies'] >= 3 and r['reply_target_concentration'] != '' and r['reply_target_concentration'] >= 0.8: flags.append('reply_target_conc')
    r['tier1_score'] = len(flags); r['flags'] = ' '.join(flags)
    pos, neg, mn = r['s_pos'], r['s_neg'], r['s_mix'] + r['s_neu']
    r['dominant_sentiment'] = ('positive' if pos > neg and pos > mn else 'negative' if neg > pos and neg > mn else 'mixed+neutral') if meta['group'] == 'report' else ''
    rows.append(r)

cols = list(rows[0].keys())
with open(os.path.join(OUT_DIR, 'tier1_authors.csv'), 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)

# ---------------- summary ----------------
FLAGS = ['handle_digit_suffix', 'name_empty', 'copypasta_author', 'self_repeat', 'shared_link_coord', 'burst3', 'promotional', 'identical_longform', 'reply_target_conc', 'verified']
def flagval(r, f):
    if f == 'burst3': return int(r['burst_10min_max'] >= 3)
    if f == 'reply_target_conc': return int('reply_target_conc' in r['flags'])
    if f == 'in_corpus': return int(r['n_tweets_in_corpus'] > 0)
    v = r[f]; return int(v) if v != '' else 0
def rate_table(groups):
    """groups: list of (label, rows)"""
    hdr = '| flag | ' + ' | '.join(f'{l} (n={len(rs)})' for l, rs in groups) + ' |'
    out = [hdr, '|' + '---|' * (len(groups) + 1)]
    for f in FLAGS:
        out.append(f'| {f} | ' + ' | '.join(f'{100*sum(flagval(r,f) for r in rs)/max(1,len(rs)):.1f}%' for _, rs in groups) + ' |')
    med = lambda rs: (sorted(r['n_tweets_in_corpus'] for r in rs)[len(rs)//2] if rs else 0)
    out.append('| median n_tweets | ' + ' | '.join(str(med(rs)) for _, rs in groups) + ' |')
    out.append('| score>=2 | ' + ' | '.join(f'{100*sum(r["tier1_score"]>=2 for r in rs)/max(1,len(rs)):.1f}%' for _, rs in groups) + ' |')
    return '\n'.join(out)

rep = [r for r in rows if r['group'] == 'report']; con = [r for r in rows if r['group'] == 'control']
has = lambda rs, d: [r for r in rs if d in r['drugs'].split('+')]
L = []
L.append('# Tier 1 bot / coordination signals: Twitter report authors vs controls\n')
L.append(f'Corpus {len(tweets)} unique tweets / {len(by_author)} authors (2020-01 to 2025-11). {len(rep)} report authors, {len(con)} controls '
         f'({600-len(con)} ids are in both control lists). Exact-key clusters ignore keys < {MIN_KEY_CHARS} chars. '
         f'No URL occurs in >=3 tweets from >=2 authors (t.co links are per-tweet; retweets absent), so shared_link_coord is inert here.\n')
L.append('## Flag rates by group and drug\n')
L.append(rate_table([('report ivm', has(rep, 'ivermectin')), ('control ivm', has(con, 'ivermectin')), ('report LDN', has(rep, 'ldn')), ('control LDN', has(con, 'ldn'))]))
L.append('\n## Report authors by dominant sentiment\n')
L.append(rate_table([(s, [r for r in rep if r['dominant_sentiment'] == s]) for s in ('positive', 'negative', 'mixed+neutral')]))
L.append('\n## tier1_score distribution (score 0,1,2,3,4)\n')
mx = max(r['tier1_score'] for r in rows)
L.append('report: ' + ', '.join(str(sum(r["tier1_score"]==s for r in rep)) for s in range(mx+1)) + '; control: ' + ', '.join(str(sum(r["tier1_score"]==s for r in con)) for s in range(mx+1)) + '.')
L.append(f'\nShingle (k={SHINGLE_K}, Jaccard>={SHINGLE_JACCARD}) clusters with >=3 tweets / >=2 authors: {sum(1 for s in sh_stats.values() if s[0]>=3 and s[1]>=2)}; '
         f'authors flagged by shingle but not exact key: report {sum(r["shingle_adds_cluster"] for r in rep)}, control {sum(r["shingle_adds_cluster"] for r in con)}.\n')
L.append('## Top 25 authors by score\n')
L.append('| username | grp | drug | rep | P/N/M/U | sc | flags |\n|---|---|---|---|---|---|---|')
AB = dict(digit_suffix='dig', name_empty='nm', copypasta='cp', self_repeat='sr', shared_link='sl', burst3='b3', promotional='pr', identical_longform='il', reply_target_conc='rt')
for r in sorted(rows, key=lambda r: (-r['tier1_score'], -r['n_tweets_in_corpus']))[:25]:
    L.append(f"| {r['username']} | {r['group'][:3]} | {r['drugs'].replace('ivermectin','ivm')} | {r['reports']} | {r['s_pos']}/{r['s_neg']}/{r['s_mix']}/{r['s_neu']} | {r['tier1_score']} | {' '.join(AB[f] for f in r['flags'].split())} |")
L.append('\nflags: dig=digit_suffix nm=name_empty cp=copypasta sr=self_repeat b3=burst>=3 pr=promotional il=identical_longform rt=reply_target_conc')

# shared-link groups with report authors
rep_ids = {r['author_id'] for r in rep}
L.append('\n## Shared-link groups involving report authors\n')
glist = []
for u, g in link_groups.items():
    ra = g & rep_ids
    if ra: glist.append((len(url_posts[u]), len(g), u, sorted(targets[a]['username'] or a for a in ra), u))
if not glist: L.append('None.')
for ntw, na, u, ras, _ in sorted(glist, reverse=True)[:15]:
    ex = next(tweets[p[2]]['text'] for p in url_posts[u] if p[1] in rep_ids)
    L.append(f'- `{u}`: {ntw} tweets / {na} authors; report: {", ".join(ras[:8])}{"..." if len(ras)>8 else ""}; e.g. "{ex[:100].replace(chr(10)," ")}"')
# copypasta clusters with report authors
L.append('\n## Exact-key copypasta clusters (>=3 tweets, >=2 authors) with report authors, top 10 of %d\n' % sum(1 for k in key_members if key_stats[k][0]>=3 and key_stats[k][1]>=2 and ({m['author'] for m in key_members[k]} & rep_ids)))
clist = []
for k, mem in key_members.items():
    st = key_stats[k]
    if st[0] >= 3 and st[1] >= 2:
        ra = {m['author'] for m in mem} & rep_ids
        if ra: clist.append((st, k, sorted(targets[a]['username'] or a for a in ra), mem[0]['text']))
if not clist: L.append('None.')
for st, k, ras, ex in sorted(clist, key=lambda x: -x[0][0])[:10]:
    L.append(f'- {st[0]} tw / {st[1]} auth; report: {", ".join(ras[:6])}{"..." if len(ras)>6 else ""}; "{ex[:100].replace(chr(10)," ")}"')
# Chloe network
chloe = [t for t in tweets.values() if 'referred me to chloe' in t['text'].lower() or ('chloe' in t['text'].lower() and 'referred' in t['text'].lower())]
ch_auth = {t['author'] for t in chloe}
ch_keys = {t['key'] for t in chloe}
ch_flagged = {t['author'] for t in chloe if key_stats.get(t['key'], (0, 0))[0] >= 3 and key_stats[t['key']][1] >= 2}
ch_sh = {t['author'] for t in chloe if t['id'] in tid_to_shc and sh_stats[tid_to_shc[t['id']]][0] >= 3}
rows_by_id = {r['author_id']: r for r in rows}
vend = [t for t in tweets.values() if re.search(r'referred (me )?to (alexa|chloe)', t['text'].lower())]
v_auth = {t['author'] for t in vend}
L.append(f'\n## "referred me to Chloe" vendor network\n\nRe-found, but small in this corpus: {len(chloe)} tweets from {len(ch_auth)} accounts (not 47) contain "referred me to Chloe"; '
         f'{len(ch_auth & rep_ids)} are report authors ({", ".join(sorted(targets[a]["username"] for a in ch_auth & rep_ids))}), {len(ch_auth & set(targets) - rep_ids)} controls. '
         f'Exact-key copypasta flags {len(ch_flagged)}/{len(ch_auth)} ({len(ch_keys)} distinct key), shingle {len(ch_sh)}/{len(ch_auth)}. '
         f'The same template with "Alexa Reyes"/"Alexa" brings the vendor network to {len(vend)} tweets / {len(v_auth)} accounts, {len(v_auth & rep_ids)} of them report authors '
         f'({", ".join(sorted(set(targets[x]["drugs"][0] + "/" + (rows_by_id[x]["dominant_sentiment"]) for x in v_auth & rep_ids)))}).\n')
json.dump(dict(chloe_accounts=sorted(ch_auth), chloe_report_authors=sorted(ch_auth & rep_ids),
               link_groups={u: sorted(g) for u, g in link_groups.items()},
               copypasta_clusters=[dict(n_tweets=st[0], n_authors=st[1], key=k[:120], authors=sorted({m['author'] for m in key_members[k]})) for k, st in key_stats.items() if st[0] >= 3 and st[1] >= 2]),
          open(os.path.join(OUT_DIR, 'tier1_groups.json'), 'w'), indent=1)
L.append('## What these signals can and cannot see\n')
med_rep = sorted(r['n_tweets_in_corpus'] for r in rep)[len(rep)//2]
L.append(f'The corpus is a keyword sample, not author timelines: the median report author has {med_rep} tweet(s) in it, so burst, self-repeat, '
         'reply-target concentration and tweets-per-day are undefined or trivially zero for most accounts; the score mostly reflects profile features '
         '(digit-suffix handle, empty name) and cross-author text duplication, the only signals that work on one tweet. Copypasta is seen only when several '
         'network members hit the same keyword search; the Chloe/Alexa vendor accounts are caught, a single bot with one tweet is not. Text is the 280-char preview. '
         'Absence of flags is not evidence of authenticity; report and control rates are comparable because both were sampled the same way.\n')
with open(os.path.join(OUT_DIR, 'tier1_summary.md'), 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(L) + '\n')
print('done', file=sys.stderr)
