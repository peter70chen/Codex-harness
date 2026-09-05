from pathlib import Path
import json,datetime,os
p=Path.home()/'.codex/cliproxyapi/models.json';old=p.read_text();j=json.loads(old)
limits={'grok-4.6':(500000,450000),'gemini-3.8-flash-high':(1048576,900000),'glm-5.3-flash':(1000000,850000),'muse-spark-1.3-contributor':(1048576,900000)}
for m in j['models']:
 if m['slug'] in limits:
  window,threshold=limits[m['slug']]
  m.update(context_window=window,max_context_window=window,auto_compact_token_limit=threshold)
  assert m['default_reasoning_level']=='high'
  print(json.dumps({'model':m['slug'],'context_window':window,'auto_compact_token_limit':threshold}))
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S');b=p.parent/('models.before-context-fix.'+stamp+'.json')
fd=os.open(b,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write(old)
p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
