import sys,json,pathlib,time,calendar,collections,re,html
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))  # step1_search.py
import step1_search as s
out=pathlib.Path(sys.argv[1]); s.REQUEST_CAP=200; tok=s.token(); clog=[]
Q='("my long covid" OR "I have long covid" OR "I\'ve had long covid" OR "I got long covid" OR "living with long covid" OR "long covid since" OR "months of long covid" OR "years of long covid" OR "I\'m a long hauler" OR "long hauler here" OR "fellow long hauler" OR "my long hauler") -is:retweet'
fields={'max_results':100,'tweet.fields':s.FIELDS+',note_tweet,text','expansions':'author_id','user.fields':'created_at,description,public_metrics,username,name,verified'}
windows=[(2021,3),(2021,9),(2022,2),(2022,6),(2022,10),(2023,2),(2023,6),(2023,10),(2024,3),(2024,9),(2025,3),(2025,9)]
posts=[]; users={}
for Y,M in windows:
    last=calendar.monthrange(Y,M)[1]
    body=s.get('/tweets/search/all',dict(fields,query=Q,start_time=f'{Y}-{M:02d}-01T00:00:00Z',end_time=f'{Y}-{M:02d}-{last}T23:59:59Z'),tok,clog)
    (out/f'sample_{Y}_{M:02d}.json').write_text(json.dumps(body,ensure_ascii=False))
    posts+=body.get('data',[])
    for u in body.get('includes',{}).get('users',[]): users[u['id']]=u
    time.sleep(1.1)
print('sample posts',len(posts),'authors',len({p['author_id'] for p in posts}),'cost $%.2f'%(len(posts)*0.005),flush=True)
json.dump({'posts':posts,'users':users},open(out/'sample_posts.json','w'),ensure_ascii=False)
org=re.compile(r'pharmac|clinic|\bapp\b|company|society|foundation|charity|nonprofit|non-profit|institute|journal|news|magazine|podcast|we are|our (team|mission|patients)|official',re.I)
selfp=re.compile(r"\b(my|I have|I've had|I got|living with|I'm a|here|fellow)\b.{0,30}(long covid|long hauler)|long covid since|(months|years) of long covid",re.I)
clin=re.compile(r"my (long covid )?(patients|clinic|study|research|paper|article|book|podcast|story about)|patients with",re.I)
bioLC=re.compile(r'long[ -]?covid|longcovid|#LC\b|PASC|long[ -]?haul|ME/?CFS|MECFS|pwME|myalgic',re.I)
qual={}
for p in posts:
    a=p['author_id']; u=users.get(a,{}); bio=u.get('description','') or ''; t=html.unescape((p.get('note_tweet') or {}).get('text') or p['text'])
    if org.search(bio): continue
    ok_post=bool(selfp.search(t)) and not clin.search(t); ok_bio=bool(bioLC.search(bio))
    if ok_post or ok_bio: qual[a]={'username':u.get('username'),'bio':bio[:120],'post_self':ok_post,'bio_lc':ok_bio}
print('qualifying patient authors',len(qual),flush=True)
json.dump(qual,open(out/'qualifying_authors.json','w'),indent=1)
ids=list(qual); alias='(LDN OR naltrexone OR naltrexon OR naltrexona)'; ldn=[]; lusers={}; total=0; CAP=800
for i in range(0,len(ids),25):
    if total>=CAP: print('post cap'); break
    q=f"{alias} ({' OR '.join('from:'+x for x in ids[i:i+25])}) -is:retweet"; nt=None; pg=0
    while True:
        body=s.get('/tweets/search/all',dict(fields,query=q,start_time='2020-01-01T00:00:00Z',end_time='2025-11-16T00:00:00Z',**({'next_token':nt} if nt else {})),tok,clog); pg+=1
        (out/f'ldn_batch{i//25+1:03d}_p{pg}.json').write_text(json.dumps(body,ensure_ascii=False))
        d=body.get('data',[]); ldn+=d; total+=len(d)
        for u in body.get('includes',{}).get('users',[]): lusers[u['id']]=u
        nt=body.get('meta',{}).get('next_token')
        if not nt or total>=CAP: break
        time.sleep(1.1)
    time.sleep(1.1)
json.dump({'posts':ldn,'users':lusers},open(out/'ldn_posts.json','w'),ensure_ascii=False)
print('LDN posts',total,'LDN authors',len({p['author_id'] for p in ldn}),'requests',len(clog),'TOTAL est. cost $%.2f'%((len(posts)+total)*0.005))
