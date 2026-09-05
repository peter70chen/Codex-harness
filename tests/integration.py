"""Isolated native Codex + patched CPA + fault-injecting upstream; no real credentials."""
import http.server, threading, socket, tempfile, pathlib, json, os, subprocess, queue, time, shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
BINARY = pathlib.Path(os.getenv('HARNESS_BINARY', str(ROOT/'build/cliproxyapi-desktopfix1')))
RESULTS = ROOT/'build/test-results'
RESULTS.mkdir(parents=True, exist_ok=True)
PRIVATE = pathlib.Path.home()/'.codex/cliproxyapi'
directory = pathlib.Path(tempfile.mkdtemp(prefix='harness-integration-', dir=PRIVATE))
state = {'muse_attempts': 0, 'muse_tool_output': False, 'grok_attempts': 0}
lock = threading.Lock()

class Upstream(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        model = body['model']; inp = body.get('input', [])
        with lock:
            field = 'muse_attempts' if model.startswith('muse') else 'grok_attempts'
            state[field] += 1; attempt = state[field]
        if model.startswith('muse') and attempt == 1:
            if os.getenv('INJECT_FAILURE') == 'sse':
                events=[{'type':'response.created','response':{'id':'injected','object':'response','status':'in_progress','output':[]}}, {'type':'response.failed','response':{'id':'injected','status':'failed','error':{'type':'server_error','code':'server_error','message':'injected temporary failure'}}}]
                data=''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            data = b'{"error":{"type":"server_error","message":"injected temporary failure"}}'
            self.send_response(500); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data); return
        if model.startswith('muse'):
            received = any(x.get('type') == 'function_call_output' for x in inp)
            if received:
                state['muse_tool_output'] = True
                output = [{'type':'message','id':'msg_muse','role':'assistant','status':'completed','content':[{'type':'output_text','text':'HARNESS_OK','annotations':[]}]}]
            else:
                output = [{'type':'function_call','id':'fc_muse','status':'completed','name':'verification_tools.lookup','call_id':'call_lookup','arguments':'{"value":"safe"}'}]
            usage = {'input_tokens':200,'output_tokens':20,'total_tokens':220}
        else:
            output = [{'type':'web_search_call','id':'web_'+str(attempt),'status':'completed','action':{'type':'search','query':'synthetic test'}},
                {'type':'message','id':'msg_grok_'+str(attempt),'role':'assistant','status':'completed','content':[{'type':'output_text','text':'HARNESS_OK','annotations':[]}]}]
            usage = {'input_tokens':800000,'output_tokens':200,'total_tokens':800200,'input_tokens_details':{'cached_tokens':790000}}
        response = {'id':'resp_'+model+'_'+str(attempt),'object':'response','model':model,'status':'completed','output':output,'usage':usage}
        events = [{'type':'response.created','response':{**response,'status':'in_progress','output':[],'usage':None}}]
        for idx,item in enumerate(output):
            events.append({'type':'response.output_item.added','output_index':idx,'item':item})
            if item['type']=='message':
                events.append({'type':'response.output_text.delta','output_index':idx,'item_id':item['id'],'content_index':0,'delta':'HARNESS_OK'})
            events.append({'type':'response.output_item.done','output_index':idx,'item':item})
        events.append({'type':'response.completed','response':response})
        data = ''.join('event: '+e['type']+'\ndata: '+json.dumps({**e,'sequence_number':i})+'\n\n' for i,e in enumerate(events)).encode()
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)

server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Upstream)
threading.Thread(target=server.serve_forever,daemon=True).start()
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
(directory/'auth').mkdir(mode=0o700)
config=directory/'proxy.conf'
config.write_text(f'''host: "127.0.0.1"
port: {port}
auth-dir: "{directory}/auth"
api-keys: ["local-test-key"]
disable-image-generation: "passthrough"
request-retry: 3
max-retry-interval: 30
transient-error-cooldown-seconds: 5
codex-api-key:
  - api-key: "synthetic-upstream-key"
    base-url: "http://127.0.0.1:{server.server_port}/v1"
    models:
      - name: "muse-spark-1.3-contributor"
        alias: "muse-spark-1.3-contributor"
        is-compat: true
        thinking:
          levels: ["high"]
      - name: "grok-4.6"
        alias: "grok-4.6"
        is-compat: true
        thinking:
          levels: ["high"]
''');config.chmod(0o600)
proxylog=(directory/'proxy.log').open('w')
proxy=subprocess.Popen([str(BINARY),'--config',str(config)],stdout=proxylog,stderr=subprocess.STDOUT,
    env={**os.environ,'CODEX_DESKTOP_COMPAT':'1','CODEX_HARNESS_DIAGNOSTICS':str(directory/'diagnostics.jsonl')})
proc=None
try:
    for _ in range(100):
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.1):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('isolated proxy did not start')
    (directory/'config.toml').write_text(f'''model_provider="cliproxyapi"
model_catalog_json="{PRIVATE}/models.json"
model_reasoning_effort="high"
[model_providers.cliproxyapi]
name="Isolated regression"
base_url="http://127.0.0.1:{port}/v1"
wire_api="responses"
requires_openai_auth=false
supports_websockets=false
experimental_bearer_token="local-test-key"
''')
    proc=subprocess.Popen([os.getenv('CODEX_APP_BINARY','/Applications/ChatGPT.app/Contents/Resources/codex'),'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,env={**os.environ,'CODEX_HOME':str(directory)})
    q=queue.Queue();pending=[];number=0
    def reader():
        for line in proc.stdout:
            try:q.put(json.loads(line))
            except ValueError:pass
    threading.Thread(target=reader,daemon=True).start()
    def send(obj):proc.stdin.write(json.dumps(obj)+'\n');proc.stdin.flush()
    def rpc(method,params):
        global number
        number+=1;n=number;send({'id':n,'method':method,'params':params})
        while True:
            d=q.get(timeout=40)
            if d.get('id')==n and 'method' not in d:
                assert 'result' in d,d
                return d['result']
            pending.append(d)
    rpc('initialize',{'clientInfo':{'name':'harness-regression','version':'1.0'},'capabilities':{'experimentalApi':True}})
    fixture=json.loads((PRIVATE/'desktop-tools-schema.json').read_text())
    dynamic=[{'type':'namespace','name':'verification_tools','description':'Synthetic harmless lookup','tools':[{'type':'function','name':'lookup','description':'Return synthetic data','inputSchema':{'type':'object','properties':{'value':{'type':'string'}},'required':['value'],'additionalProperties':False}}]}]
    report={'models':[]}
    for model in ['muse-spark-1.3-contributor','grok-4.6']:
        tools=dynamic if model.startswith('muse') else [{'type':'namespace','name':'verification_'+ns['name'],'description':ns.get('description','')[:1024],'tools':[{'type':'function','name':f['name'],'description':f.get('description',''),'inputSchema':f['parameters']} for f in ns['tools']]} for ns in fixture if ns.get('type')=='namespace']
        started=rpc('thread/start',{'model':model,'cwd':str(directory),'ephemeral':True,'approvalPolicy':'never','sandbox':'read-only','dynamicTools':tools,'baseInstructions':'Synthetic regression test.','developerInstructions':'Follow the requested harmless test.'})
        tid=started['thread']['id'];begin=time.monotonic()
        r=rpc('turn/start',{'threadId':tid,'effort':'high','input':[{'type':'text','text':'Run the synthetic check','text_elements':[]}]})
        turnid=r['turn']['id'];calls=0;compactions=0;usage=None
        while True:
            d=pending.pop(0) if pending else q.get(timeout=40)
            method=d.get('method','');p=d.get('params',{})
            if 'id' in d and method:
                assert method=='item/tool/call',method
                assert p.get('namespace')=='verification_tools' and p.get('tool')=='lookup',p
                assert p.get('arguments')=={'value':'safe'},p
                calls+=1
                send({'id':d['id'],'result':{'contentItems':[{'type':'inputText','text':'SAFE_LOOKUP_OK'}],'success':True}})
            if p.get('threadId')!=tid:continue
            if 'compact' in method.lower():compactions+=1
            if method=='item/completed' and 'compact' in p.get('item',{}).get('type','').lower():compactions+=1
            if method=='thread/tokenUsage/updated':usage=p['tokenUsage']
            if method=='turn/completed' and p['turn']['id']==turnid:
                assert p['turn']['status']=='completed',p
                break
        assert compactions==0,compactions
        if model.startswith('muse'):assert calls==1 and state['muse_tool_output'] and state['muse_attempts']==3,state
        else:assert usage['last']['totalTokens']<450000,usage
        row={'model':model,'seconds':round(time.monotonic()-begin,2),'tool_calls':calls,'compactions':compactions,'usage':usage}
        report['models'].append(row);print(json.dumps(row),flush=True)
    report['mock_upstream']=state
    report['diagnostics']=[json.loads(x) for x in (directory/'diagnostics.jsonl').read_text().splitlines()]
    assert any(x.get('status') in (500,502,503,504) and x.get('phase')==('stream_terminal' if os.getenv('INJECT_FAILURE')=='sse' else 'http_response') for x in report['diagnostics'])
    (RESULTS/('integration-results-'+os.getenv('INJECT_FAILURE','http')+'.json')).write_text(json.dumps(report,indent=2))
    print('PASS: native namespace dispatch, tool return, 500 recovery and hosted-search compaction regression',flush=True)
finally:
    if proc:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    proxy.terminate()
    try:proxy.wait(timeout=5)
    except subprocess.TimeoutExpired:proxy.kill();proxy.wait()
    proxylog.close();server.shutdown()
    shutil.rmtree(directory,ignore_errors=True)
