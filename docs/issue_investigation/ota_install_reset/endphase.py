import json,re,sys,datetime as dt
S='/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/bench/loop4/summary.txt'
ts=lambda l: dt.datetime.fromisoformat(l.split()[0])
want=set(sys.argv[1:])
for s in open(S):
    run,rec,reset=re.search(r'run=(\d+).*record=(\S+) reset=(\S+)',s).groups()
    if run not in want: continue
    for line in open('/home/tjwise/meta-wisekiosk/'+rec+'/report.jsonl'):
        d=json.loads(line)
        if d.get('$report_type')=='TestReport' and d['when']=='setup':
            sec=dict(d['sections']); out=sec['Captured stdout setup']; err=sec['Captured stderr setup']; break
    c0=ts([l for l in err.splitlines() if 'capture started' in l][0])
    L=out.splitlines(); prev=None; print('== run',run)
    for i,l in enumerate(L):
        m=re.match(r'\s*(\d+)% ',l)
        if m and int(m.group(1))>=96: print('   ',l.strip())
        if ' [stats] MemFree' in l:
            t=(ts(l)-c0).total_seconds(); f=list(map(int,re.search(r'mmc=(.*?) uv',l).group(1).split()))
            if prev and t>=170:
                dr=f[0]-prev[0]; dtk=f[3]-prev[3]; dw=f[6]-prev[6]
                g=re.search(r'Dirty:(\d+) Writeback:(\d+) load=(\S+)',l).groups()
                print(f"  +{t:6.1f} reads+{dr:3d} rsect+{f[2]-prev[2]:5d} rticks+{dtk:6d} wsect+{dw:6d} dirty={g[0]:>6} wb={g[1]:>6} load={g[2]} wticks+{f[7]-prev[7]}")
            prev=f
