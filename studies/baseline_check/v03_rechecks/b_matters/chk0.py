import re,json,collections
t=open('batch_0.txt',encoding='utf8').read()
parts=re.split(r'^===== POST id=(\S+) =====\n',t,flags=re.M)
posts={parts[i]:parts[i+1] for i in range(1,len(parts),2)}
ws=lambda s:re.sub(r'\s+',' ',s).strip()
rows=[json.loads(l) for l in open('coded_0.jsonl')]
ids=[r['id'] for r in rows]
print(len(posts),len(rows),set(posts)==set(ids),len(ids)==len(set(ids)))
for r in rows:
    if ws(r['quote']) not in ws(posts[r['id']]): print('BAD',r['id'],r['quote'])
    if len(r['quote'].split())>25: print('LONG',r['id'])
print(collections.Counter(r['category'] for r in rows), sum(r['global_wording'] for r in rows))
