import re,sys,datetime as dt
lines=open('stdout.txt').read().splitlines()
def ts(l): return dt.datetime.fromisoformat(l.split()[0])
st=[l for l in lines if ' [stats] MemFree' in l]
last=ts(st[-1])
print("stats samples total",len(st),"first",st[0][:32],"last",st[-1][:32])
gaps=[(ts(b)-ts(a)).total_seconds() for a,b in zip(st,st[1:])]
print("stats gap max %.3f mean %.3f"%(max(gaps),sum(gaps)/len(gaps)))
prev=None
for l in st:
    t=ts(l)
    if (last-t).total_seconds()<=30:
        m=re.search(r'MemFree:(\d+) Dirty:(\d+) Writeback:(\d+) load=(\S+ \S+ \S+) mmc=(.*) uv=(\d)',l)
        f=list(map(int,m.group(5).split()))
        d=''
        if prev: d=' dWsect=%d dt=%.2f MB/s=%.1f'%(f[6]-prev[1][6],(t-prev[0]).total_seconds(),(f[6]-prev[1][6])*512/1e6/(t-prev[0]).total_seconds())
        print(l.split()[0][11:26],'MemFree',m.group(1),'Dirty',m.group(2),'WB',m.group(3),'load',m.group(4),'wr',f[4],'wsect',f[6],'inflight',f[8],'uv',m.group(6)+d)
        prev=(t,f)
# hb gaps in pstore
P=open(sys.argv[1]).read().splitlines()
hb=[float(re.match(r'\[\s*([\d.]+)\]',l).group(1)) for l in P if 'hb245' in l]
g=[b-a for a,b in zip(hb,hb[1:])]
print("hb n",len(hb),"gap max %.3f mean %.3f"%(max(g),sum(g)/len(g)))
