import json,sys
rec=sys.argv[1]
for line in open(rec+'/report.jsonl'):
    d=json.loads(line)
    if d.get('$report_type')!='TestReport': continue
    for name,text in d.get('sections',[]):
        if name in('Captured stdout setup','Captured stderr setup'):
            fn=('stdout' if 'stdout' in name else 'stderr')+'-'+d['nodeid'].split('::')[-1][:40].replace('/','_')+'.txt'
            open(fn,'w').write(text)
            print(d['nodeid'],d['when'],d['outcome'],name,len(text),fn)
