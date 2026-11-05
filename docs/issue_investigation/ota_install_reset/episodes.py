import json,re
S='/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/bench/loop3/summary.txt'
eps=[];inflight=set()
for s in open(S):
    run,rec,reset=re.search(r'run=(\d+).*record=(\S+) reset=(\S+)',s).groups()
    if reset=='yes': continue
    for line in open('/home/tjwise/meta-wisekiosk/'+rec+'/report.jsonl'):
        d=json.loads(line)
        if d.get('$report_type')=='TestReport' and d['when']=='setup':
            out=dict(d['sections']).get('Captured stdout setup',''); break
    cur=None
    for l in out.splitlines():
        m=re.search(r'\[kernel\].*task (\S+) blocked for more than (\d+)',l)
        if m:
            k,n=m.group(1),int(m.group(2))
            if cur and cur[0]==k and n>cur[1]: cur[1]=n
            else:
                if cur: eps.append((run,*cur))
                cur=[k,n]
        m=re.search(r'\[stats\].*mmc=(.*) uv',l)
        if m: inflight.add(m.group(1).split()[8])
    if cur: eps.append((run,*cur))
print("healthy episodes",len(eps))
r18=[e for e in eps if e[2]>=18]; r20=[e for e in r18 if e[2]>=20]
print("reached>=18:",len(r18)," of those reached>=20:",len(r20)," ended exactly at 18:",sum(1 for e in r18 if e[2]==18))
from collections import Counter
print("max-N distribution",sorted(Counter(e[2] for e in eps).items()))
print("in_flight values seen in healthy [stats]",inflight)
