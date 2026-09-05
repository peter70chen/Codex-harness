"""Real provider/native Codex regression, ephemeral tasks and allowlisted mock tool."""
from pathlib import Path
import datetime,json,os,queue,re,shutil,subprocess,tempfile,threading,time,sys

model=sys.argv[1];port=int(os.getenv('TEST_PROXY_PORT','8317'))
private=Path.home()/'.codex/cliproxyapi';root=Path(__file__).resolve().parents[1]/'build/test-results';root.mkdir(parents=True,exist_ok=True)
fixture=json.loads((private/'desktop-tools-schema.json').read_text())
dynamic=[{'type':'namespace','name':'verification_'+ns['name'],'description':ns.get('description','')[:1024],'tools':[{'type':'function','name':f['name'],'description':f.get('description',''),'inputSchema':f['parameters']} for f in ns['tools']]} for ns in fixture if ns.get('type')=='namespace']
dynamic.append({'type':'namespace','name':'verification_probe','description':'Harmless diagnostic lookup; returns supplied text.','tools':[{'type':'function','name':'lookup','description':'Echo the supplied diagnostic value','inputSchema':{'type':'object','properties':{'value':{'type':'string'}},'required':['value'],'additionalProperties':False}}]})
conf=Path('/opt/homebrew/etc/cliproxyapi.conf').read_text();key=re.search(r'api-keys:\s*\n\s*- "([^"]+)"',conf).group(1)
d=Path(tempfile.mkdtemp(prefix='desktopfix-native-',dir=private));p=d/'config.toml';p.touch(mode=0o600)
p.write_text('model_provider="cliproxyapi"\nmodel_reasoning_effort="high"\nweb_search="live"\nmodel_catalog_json='+json.dumps(str(private/'models.json'))+'\n[model_providers.cliproxyapi]\nname="Native live regression"\nbase_url="http://127.0.0.1:'+str(port)+'/v1"\nwire_api="responses"\nrequires_openai_auth=false\nsupports_websockets=false\nexperimental_bearer_token='+json.dumps(key)+'\n')
proc=subprocess.Popen([os.getenv('CODEX_APP_BINARY','/Applications/ChatGPT.app/Contents/Resources/codex'),'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env={**os.environ,'CODEX_HOME':str(d)},bufsize=1)
q=queue.Queue();pending=[];number=0;tool_calls=0;invalid_calls=0
def reader():
 for line in proc.stdout:
  try:q.put(json.loads(line))
  except ValueError:pass
threading.Thread(target=reader,daemon=True).start()
def send(obj):proc.stdin.write(json.dumps(obj)+'\n');proc.stdin.flush()
def get(timeout=180):
 global tool_calls,invalid_calls
 data=q.get(timeout=timeout)
 if 'method' in data and 'id' in data:
  p=data.get('params',{})
  if data['method']!='item/tool/call' or p.get('namespace')!='verification_probe' or p.get('tool')!='lookup':
   send({'id':data['id'],'error':{'code':-32601,'message':'Only the synthetic lookup is permitted'}})
   raise RuntimeError('Unexpected tool request; no action executed: '+str(data['method']))
  v=p.get('arguments',{}).get('value','')
  if not re.fullmatch(r'PROBE_[123]_OK',v):
   invalid_calls+=1
   send({'id':data['id'],'result':{'contentItems':[{'type':'inputText','text':'Validation error: value is required. Retry with the exact PROBE marker specified in the current user request.'}],'success':False}})
   assert invalid_calls<=3,'Model repeatedly omitted the required argument'
   return data
  tool_calls+=1;send({'id':data['id'],'result':{'contentItems':[{'type':'inputText','text':v}],'success':True}})
 return data
def rpc(method,params):
 global number
 number+=1;n=number;send({'id':n,'method':method,'params':params})
 while True:
  data=get()
  if data.get('id')==n and 'method' not in data:
   assert 'result' in data,json.dumps(data).replace(key,'[redacted]')[:500]
   return data['result']
  pending.append(data)
report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model':model,'thinking':'high','rounds':[]}
try:
 rpc('initialize',{'clientInfo':{'name':'desktop-live-regression','version':'1.0'},'capabilities':{'experimentalApi':True}})
 started=rpc('thread/start',{'model':model,'cwd':str(d),'ephemeral':True,'approvalPolicy':'never','sandbox':'read-only','dynamicTools':dynamic,'baseInstructions':'You are testing model integration. Follow the requested diagnostic task.','developerInstructions':'For lookup tasks use only verification_probe.lookup. For web tasks use only the built-in web_search search/open tools. Never call any other tool, execute commands, or access local files. End the final reply with the marker requested by the user.'})
 tid=started['thread']['id'];compactions=0;web_actions=0
 for step in range(1,4 if model.startswith('muse') else 3):
  expected='PROBE_'+str(step)+'_OK' if model.startswith('muse') else 'SEARCH_'+str(step)+'_OK'
  prompt='Call verification_probe.lookup once with value '+expected+'. After receiving its result reply exactly '+expected+'.'
  if model.startswith('grok'):
   topic='itertools.batched and its strict parameter' if step==1 else 'pathlib.Path.walk and its follow_symlinks parameter'
   prompt='Use web search to find official Python documentation for '+topic+'. Open the relevant official documentation page and answer in one short sentence with a citation. Finish with '+expected+'.'
  start=time.monotonic();result=rpc('turn/start',{'threadId':tid,'effort':'high','input':[{'type':'text','text':prompt,'text_elements':[]}]})
  turnid=result['turn']['id'];usage=None;replies=[];deadline=time.monotonic()+210
  while time.monotonic()<deadline:
   e=pending.pop(0) if pending else get(timeout=max(1,deadline-time.monotonic()))
   method=e.get('method','');p=e.get('params',{})
   if p.get('threadId')!=tid:continue
   if method=='thread/tokenUsage/updated':usage=p.get('tokenUsage')
   if method=='item/completed':
    item=p.get('item',{});kind=item.get('type','').lower()
    if 'compact' in kind:compactions+=1
    if 'websearch' in kind:web_actions+=1
    if item.get('type')=='agentMessage':replies.append(item.get('text',''))
   if 'compact' in method.lower():compactions+=1
   if method=='turn/completed' and p['turn']['id']==turnid:
    assert p['turn']['status']=='completed',json.dumps(p).replace(key,'[redacted]')[:600]
    break
  else:raise RuntimeError('Turn timeout')
  assert any(expected in r for r in replies),'Missing expected final marker'
  assert usage is not None,'Missing native usage'
  assert compactions==0,'Unexpected compaction'
  row={'round':step,'seconds':round(time.monotonic()-start,2),'final_marker':expected,'usage':usage,'web_actions':web_actions,'tool_calls':tool_calls,'invalid_tool_calls_rejected':invalid_calls,'compactions':compactions}
  report['rounds'].append(row);print(json.dumps({'model':model,**row}),flush=True)
 if model.startswith('muse'):assert tool_calls==3,tool_calls
 else:assert web_actions>=2,web_actions
 report['pass']=True
 (root/('native-live-'+model+'.json')).write_text(json.dumps(report,indent=2))
finally:
 proc.terminate()
 try:proc.wait(timeout=5)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 shutil.rmtree(d,ignore_errors=True)
