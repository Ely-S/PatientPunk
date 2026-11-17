import re,json,collections
t=open('batch_1.txt').read()
parts=re.split(r'^===== POST id=(\S+) =====$',t,flags=re.M)
posts={parts[i]:re.sub(r'\s+',' ',parts[i+1]) for i in range(1,len(parts),2)}
rows=[json.loads(l) for l in open('coded_1.jsonl')]
ids=[r['id'] for r in rows]
print(len(posts),len(rows),set(posts)-set(ids),[i for i,c in collections.Counter(ids).items() if c>1],set(ids)-set(posts))
for r in rows:
    if re.sub(r'\s+',' ',r['quote']).strip() not in posts[r['id']]: print('BAD',r['id'],r['quote'])
print(collections.Counter(r['category'] for r in rows),sum(r['global_wording'] for r in rows))
