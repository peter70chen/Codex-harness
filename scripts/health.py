from pathlib import Path
import concurrent.futures,datetime,json,re,time,urllib.request,urllib.error,uuid
p=Path.home()/'.codex/cliproxyapi';s=Path('/opt/homebrew/etc/cliproxyapi.conf').read_text();key=re.search(r'api-keys:\s*\n\s*- "([^"]+)"',s).group(1)
def check(model):
 b={'model':model,'input':'Reply exactly HEALTH_OK.','reasoning':{'effort':'high'},'stream':True}
 r=urllib.request.Request('http://127.0.0.1:8317/v1/responses',data=json.dumps(b).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','session-id':str(uuid.uuid4()),'User-Agent':'Codex-Desktop-harness-health'})
 start=time.monotonic();events=[]
 try:
  with urllib.request.urlopen(r,timeout=90) as response:
   status=response.status
   for line in response:
    if line.startswith(b'data:'):
     try:events.append(json.loads(line[5:]))
     except ValueError:pass
 except urllib.error.HTTPError as e:return {'model':model,'status':e.code,'pass':False}
 except Exception as e:return {'model':model,'error_type':type(e).__name__,'pass':False}
 text=''.join(e.get('delta','') for e in events if e.get('type')=='response.output_text.delta')
 complete=any(e.get('type')=='response.completed' for e in events)
 return {'model':model,'thinking':'high','http_status':status,'completed':complete,'reply':text,'seconds':round(time.monotonic()-start,2),'pass':complete and text.strip()=='HEALTH_OK'}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(check,['grok-4.6','muse-spark-1.3-contributor','glm-5.3-flash','gemini-3.8-flash-high']))
report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':rows,'pass':all(r['pass'] for r in rows)}
out=p/'harness-health.json';out.write_text(json.dumps(report,indent=2));out.chmod(0o600);print(json.dumps(report),flush=True)
assert report['pass']
