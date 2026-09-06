"""Install the verified private CPA build without modifying Homebrew binaries."""
from pathlib import Path
import datetime,hashlib,json,os,plistlib,re,shutil,subprocess,sys,time,urllib.request

# Validate the native catalog before touching any running service.
from merge_native_models import merge
catalog_path = Path.home()/'.codex/cliproxyapi/models.json'
native_path = Path.home()/'.codex/models_cache.json'
current_catalog = json.loads(catalog_path.read_text())
merged_catalog = merge(json.loads(native_path.read_text()), current_catalog)
current_ids = {m['slug'] for m in current_catalog['models'] if m.get('visibility') == 'list'}
required_ids = {m['slug'] for m in merged_catalog['models'] if m['slug'].startswith('gpt-') and m.get('visibility') == 'list'}
if not required_ids <= current_ids:
    raise SystemExit('Native GPT models missing. Run scripts/merge_native_models.py before installation.')

source=Path(sys.argv[1]).resolve();private=Path.home()/'.codex/cliproxyapi'
private.mkdir(mode=0o700,exist_ok=True);private.chmod(0o700)
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S');backup=private/('desktopfix-backup-'+stamp);backup.mkdir(mode=0o700)
config=Path('/opt/homebrew/etc/cliproxyapi.conf');original=config.read_text()
(backup/'proxy.conf').touch(mode=0o600);(backup/'proxy.conf').write_text(original)
agents=Path.home()/'Library/LaunchAgents';agents.mkdir(parents=True,exist_ok=True)
brew_plist=agents/'homebrew.mxcl.cliproxyapi.plist';label='com.peter.codex-model-proxy';plist=agents/(label+'.plist')
for p in (brew_plist,plist):
 if p.exists():shutil.copy2(p,backup/p.name)
target=private/'bin/cliproxyapi-desktopfix1';target.parent.mkdir(mode=0o700,exist_ok=True)
if target.exists():shutil.copy2(target,backup/target.name)
stage=target.with_suffix('.new');shutil.copyfile(source,stage);stage.chmod(0o700);os.replace(stage,target)
updated=re.sub(r'^transient-error-cooldown-seconds:.*$', 'transient-error-cooldown-seconds: 5',original,flags=re.M)
assert updated!=original or 'transient-error-cooldown-seconds: 5' in original
config.write_text(updated);config.chmod(0o600)
log=private/'proxy-service.log';log.touch(mode=0o600,exist_ok=True);log.chmod(0o600)
obj={'Label':label,'ProgramArguments':[str(target),'--config',str(config)],'RunAtLoad':True,'KeepAlive':True,
 'WorkingDirectory':str(private),'EnvironmentVariables':{'PATH':'/opt/homebrew/bin:/usr/bin:/bin','CODEX_DESKTOP_COMPAT':'1','CODEX_HARNESS_DIAGNOSTICS':str(private/'harness-diagnostics.jsonl')},
 'StandardOutPath':str(log),'StandardErrorPath':str(log),'ThrottleInterval':5}
uid=os.getuid();domain='gui/'+str(uid)

def run(args,check=True):return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=check)
rollback=backup/'rollback.py'
rollback.write_text('''from pathlib import Path
import subprocess,shutil,os
b=Path(__file__).resolve().parent
subprocess.run(["launchctl","bootout","gui/"+str(os.getuid())+"/com.peter.codex-model-proxy"],check=False)
shutil.copy2(b/"proxy.conf","/opt/homebrew/etc/cliproxyapi.conf")
p=Path.home()/"Library/LaunchAgents/com.peter.codex-model-proxy.plist"
if p.exists():p.unlink()
subprocess.run(["/opt/homebrew/bin/brew","services","start","cliproxyapi"],check=True)
print("Restored the Homebrew proxy and saved configuration.")
''');rollback.chmod(0o600)
run(['/opt/homebrew/bin/brew','services','stop','cliproxyapi'])
run(['launchctl','bootout',domain+'/'+label],check=False)
plist.write_bytes(plistlib.dumps(obj));plist.chmod(0o644)
try:
 run(['launchctl','bootstrap',domain,str(plist)])
 key=re.search(r'api-keys:\s*\n\s*- "([^\"]+)"',updated).group(1)
 for i in range(120):
  try:
   req=urllib.request.Request('http://127.0.0.1:8317/v1/models',headers={'Authorization':'Bearer '+key})
   with urllib.request.urlopen(req,timeout=2) as response:models=json.load(response)
   ids={m['id'] for m in models['data']}
   assert {'grok-4.6','muse-spark-1.3-contributor','glm-5.3-flash','gemini-3.8-flash-high'}<=ids,ids
   break
  except Exception:
   if i==119:raise
   time.sleep(1)
except Exception:
 run([sys.executable,str(rollback)],check=False)
 raise
catalog=json.loads((private/'models.json').read_text())
extra={m['slug']:m for m in catalog['models'] if m['slug'] in ids and m['slug'] in ['grok-4.6','muse-spark-1.3-contributor','glm-5.3-flash','gemini-3.8-flash-high']}
assert len(extra)==4 and all(m['default_reasoning_level']=='high' and [x['effort'] for x in m['supported_reasoning_levels']]==['high'] for m in extra.values())
report={'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'version':'7.2.150-desktopfix1',
 'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'service':label,'listener':'127.0.0.1:8317','models':list(extra),'thinking':'high',
 'transient_cooldown_seconds':5,'rollback':str(rollback),'pass':True}
(private/'harness-installation.json').write_text(json.dumps(report,indent=2));(private/'harness-installation.json').chmod(0o600)
print(json.dumps(report),flush=True)
