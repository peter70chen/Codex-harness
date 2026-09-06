"""Bounded native GPT smoke test using an ephemeral task; consumes account quota."""
from pathlib import Path
import json,queue,threading,subprocess,time,tempfile,shutil,sys,os
p=Path.home()/'.codex/cliproxyapi';binary=os.getenv('CODEX_APP_BINARY','/Applications/ChatGPT.app/Contents/Resources/codex')
proc=subprocess.Popen([binary,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
q=queue.Queue();pending=[];counter=0

def read():
 for l in proc.stdout:
  try:q.put(json.loads(l))
  except ValueError:pass
threading.Thread(target=read,daemon=True).start()
def rpc(method,params):
 global counter
 counter+=1;proc.stdin.write(json.dumps({'id':counter,'method':method,'params':params})+'\n');proc.stdin.flush()
 end=time.monotonic()+60
 while time.monotonic()<end:
  d=q.get(timeout=max(1,end-time.monotonic()))
  if d.get('id')==counter:
   assert 'result' in d,'RPC failed: '+method
   return d['result']
  pending.append(d)
 raise RuntimeError('RPC timeout')
d=Path(tempfile.mkdtemp(prefix='native-gpt-check-',dir=p))
try:
 rpc('initialize',{'clientInfo':{'name':'native-gpt-check','version':'1'},'capabilities':{'experimentalApi':True}})
 models=rpc('model/list',{'includeHidden':False,'limit':100})['data'];ids={m['model'] for m in models}
 expected={m['slug'] for m in json.loads((Path.home()/'.codex/models_cache.json').read_text())['models'] if m['slug'].startswith('gpt-') and m.get('visibility')=='list'}
 assert expected <= ids, 'Native GPT models missing from actual desktop list'
 assert {'grok-4.6','gemini-3.8-flash-high','glm-5.3-flash','muse-spark-1.3-contributor'}<=ids
 print('Native desktop model list:',sorted(ids),flush=True)
 started=rpc('thread/start',{'model':sys.argv[1] if len(sys.argv)>1 else 'gpt-6-astra','cwd':str(d),'ephemeral':True,'approvalPolicy':'never','sandbox':'read-only','config':{'web_search':'disabled'},'baseInstructions':'You are performing a harmless connection check. Do not use tools or read files.','developerInstructions':'Reply exactly GPT_OK to the user.'})
 tid=started['thread']['id'];print('Actual provider:',started.get('modelProvider',started['thread'].get('modelProvider')),flush=True)
 result=rpc('turn/start',{'threadId':tid,'effort':'low','input':[{'type':'text','text':'Reply exactly GPT_OK.','text_elements':[]}]})
 end=time.monotonic()+90;got=False
 while time.monotonic()<end:
  e=pending.pop(0) if pending else q.get(timeout=max(1,end-time.monotonic()))
  method=e.get('method');params=e.get('params',{})
  if params.get('threadId')!=tid:continue
  if method=='item/completed' and params.get('item',{}).get('type')=='agentMessage':got='GPT_OK' in params['item'].get('text','')
  if method=='error':print('Native turn error:',json.dumps(params.get('error',{}))[:350],flush=True)
  if method=='turn/completed':
   status=params['turn']['status'];print('GPT native turn:',status,'marker:',got,flush=True)
   assert status=='completed' and got
   break
 else:raise RuntimeError('GPT native turn timed out')
finally:
 proc.terminate()
 try:proc.wait(timeout=5)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 shutil.rmtree(d)
