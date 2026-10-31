import sqlite3, pathlib, hashlib, json, datetime, collections, re, gzip

ROOT = pathlib.Path('E:/Sea_openai/sea-openai/data')
OUT = pathlib.Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def qi(s): return '"'+s.replace('"','""')+'"'
def rows(c, sql, args=()): return [dict(r) for r in c.execute(sql,args)]

result={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'inventory':[], 'databases':{}}
for p in sorted(ROOT.rglob('*')):
    if p.is_file():
        result['inventory'].append({'path':str(p.relative_to(ROOT)), 'bytes':p.stat().st_size,'sha256':sha(p)})
for p in sorted(ROOT.rglob('*.sqlite')):
    print('AUDIT', p.relative_to(ROOT), flush=True)
    before=sha(p)
    c=sqlite3.connect(p.as_uri()+'?mode=ro', uri=True)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    data={'sha256_before':before,'query_only':c.execute('pragma query_only').fetchone()[0], 'quick_check':rows(c,'pragma quick_check'), 'foreign_key_check':rows(c,'pragma foreign_key_check'), 'objects':rows(c,"select type,name,tbl_name,sql from sqlite_master where name not like 'sqlite_%' order by type,name"), 'tables':{},'views':{}}
    for obj in data['objects']:
        if obj['type']=='view':
            data['views'][obj['name']]={'count':c.execute('select count(*) from '+qi(obj['name'])).fetchone()[0]}
        if obj['type']!='table': continue
        name=obj['name']; cols=rows(c,'pragma table_info('+qi(name)+')')
        n=c.execute('select count(*) from '+qi(name)).fetchone()[0]
        t={'count':n,'columns':cols,'foreign_keys':rows(c,'pragma foreign_key_list('+qi(name)+')'),'column_profile':{}}
        for col in cols:
            colname=col['name']; q=qi(colname)
            profile=dict(c.execute('select sum('+q+' is null) nulls, sum(typeof('+q+")='text' and "+q+"='') empty_strings, count(distinct "+q+') distinct_values from '+qi(name)).fetchone())
            if colname.endswith(('_at','_date')) or colname in ('now','ts','timestamp','date','start_at','end_at'):
                profile.update(dict(c.execute('select min('+q+') min, max('+q+') max from '+qi(name)).fetchone()))
            if colname in ('kind','channel','status','reason_code','outcome','reported_by','service_level','payment_method','actor','event_type','severity','level','metric','name','source','type') and profile['distinct_values']<=100 and colname!='name':
                profile['distribution']=rows(c,'select '+q+' value,count(*) n from '+qi(name)+' group by '+q+' order by n desc')
            t['column_profile'][colname]=profile
        data['tables'][name]=t
        print(' ', name, n, flush=True)
    c.close(); data['sha256_after']=sha(p); data['unchanged']=before==data['sha256_after']
    result['databases'][str(p.relative_to(ROOT))]=data
for p in ROOT.rglob('*.gz'):
    h=hashlib.sha256()
    with gzip.open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    result.setdefault('gzip_payload_hashes',{})[str(p.relative_to(ROOT))]=h.hexdigest()
(OUT/'inventory-schema-profile.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('WROTE',OUT/'inventory-schema-profile.json')
