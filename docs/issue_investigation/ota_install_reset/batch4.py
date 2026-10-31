import json,re,datetime as dt
S='/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/bench/loop4/summary.txt'
ts=lambda l: dt.datetime.fromisoformat(l.split()[0])
def sections(rec):
    out=err=''
    for line in open('/home/tjwise/meta-wisekiosk/'+rec+'/report.jsonl'):
        d=json.loads(line)
        if d.get('$report_type')=='TestReport' and d['when']=='setup':
            for n,t in d.get('sections',[]):
                if n=='Captured stdout setup': out=t
                if n=='Captured stderr setup': err=t
            break
    return out,err
for s in open(S):
    run,rec,reset=re.search(r'run=(\d+).*record=(\S+) reset=(\S+)',s).groups()
    out,err=sections(rec); L=out.splitlines()
    c0=ts([l for l in err.splitlines() if 'capture started' in l][0])
    st=[l for l in L if ' [stats] MemFree' in l]
    f=lambda l: list(map(int,re.search(r'mmc=(.*?) uv',l).group(1).split()))
    # progress line -> next stamped line time
    prog={}
    for i,l in enumerate(L):
        m=re.match(r'\s*(\d+)% ',l)
        if m:
            for k in L[i+1:]:
                if re.match(r'\d{4}-',k): prog[int(m.group(1))]=(ts(k)-c0).total_seconds(); break
    freqs=set(re.findall(r'freq=(\S+)',out))
    hung=[int(x) for x in re.findall(r'\[kernel\].*blocked for more than (\d+)',out)]
    # stats at/after 95%
    t95=prog.get(95); w=[l for l in st if t95 and (ts(l)-c0).total_seconds()>=t95-0.5]
    rd=(f(w[-1])[0]-f(w[0])[0], f(w[-1])[3]-f(w[0])[3]) if len(w)>1 else None
    # first stats with Dirty:0 after 95%
    d0=[(ts(l)-c0).total_seconds() for l in w if ' Dirty:0 ' in l]
    load99=None
    if 99 in prog:
        c=[l for l in st if (ts(l)-c0).total_seconds()>=prog[99]]
        if c: load99=re.search(r'load=(\S+)',c[0]).group(1)
    wtot=f(st[-1])[6]-f(st[0])[6]
    lastst=(ts(st[-1])-c0).total_seconds()
    print(f"run={run:>2} reset={reset:3} t99={prog.get(99,'-')} t100={prog.get(100,'-')} last_stats=+{lastst:.1f} reads95+={rd} dirty0@={['%.1f'%x for x in d0[:3]]} load@99={load99} wsect_cap={wtot} hung_max={max(hung or [0])} hung_n={len(hung)} freqs={sorted(freqs)}")
