import json,re,datetime as dt,sys
S='/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/bench/loop3/summary.txt'
ts=lambda l: dt.datetime.fromisoformat(l.split()[0])
for s in open(S):
    m=re.search(r'run=(\d+).*record=(\S+) reset=(\S+)',s); run,rec,reset=m.groups()
    out=err=''
    for line in open('/home/tjwise/meta-wisekiosk/'+rec+'/report.jsonl'):
        d=json.loads(line)
        if d.get('$report_type')=='TestReport' and d['when']=='setup':
            for n,t in d.get('sections',[]):
                if n=='Captured stdout setup': out=t
                if n=='Captured stderr setup': err=t
            break
    L=out.splitlines()
    cs=[l for l in err.splitlines() if 'capture started' in l]
    st=[l for l in L if ' [stats] MemFree' in l]
    gaps=[((ts(b)-ts(a)).total_seconds(),ts(a)) for a,b in zip(st,st[1:])]
    c0=ts(cs[0]) if cs else None
    big=['%.1f@+%.0f'%(g,(t-c0).total_seconds()) for g,t in gaps if g>3]
    hung=[l for l in L if '[kernel]' in l and 'blocked for more than' in l]
    tasks=set(re.search(r'task (\S+) blocked',l).group(1).split(':')[0]+':'+'' for l in hung)
    wq=set(re.search(r'Workqueue: (.*)',l).group(1) for l in L if '[kernel]' in l and 'Workqueue:' in l)
    mx=max([int(re.search(r'more than (\d+)',l).group(1)) for l in hung] or [0])
    prog=[l for l in L if re.match(r'\s*\d+% ',l)]
    lastst=(ts(st[-1])-c0).total_seconds() if st and c0 else None
    # time of first hung msg rel capture
    fh=['%.0f'%((ts(hung[0])-c0).total_seconds())] if hung else []
    print(f"run={run:>2} reset={reset:3} stats_n={len(st):3} last_stats=+{lastst:.0f}s maxgap={max(g for g,_ in gaps):.1f} big={big} hung_n={len(hung)} max_blocked={mx} first_hung=+{fh} wq={sorted(wq)} lastprog={prog[-1].strip() if prog else None}")
