from pathlib import Path
import datetime,json,os,re
p=Path('/opt/homebrew/etc/cliproxyapi.conf');s=p.read_text()
assert '# BEGIN MUSE SCHEMA COMPATIBILITY' not in s,'Already applied'
assert not re.search(r'^payload:',s,re.M),'Existing payload rules require merge'
# The recursive MIME-part edge is described as an open object. The original
# tool still validates the complete payload; this changes only the model schema.
replacement={'type':'object','description':'Nested Gmail MIME part. Uses the same fields as the enclosing part: mime_type (required), body (content or base64_url_content), charset, filename, content_disposition, content_id, and parts (an array of further MIME parts). A multipart container uses parts; a leaf uses body. Follow the enclosing MIME-part schema at every depth.','properties':{'mime_type':{'type':'string'}},'required':['mime_type'],'additionalProperties':True}
suffix='.parameters.$defs.GmailMessagePartRequest.properties.parts.anyOf.0.items'
paths=['tools.#(type=="namespace")#.tools.#(parameters.$defs.GmailMessagePartRequest)#'+suffix,'tools.#(parameters.$defs.GmailMessagePartRequest)#'+suffix]
block='\n# BEGIN MUSE SCHEMA COMPATIBILITY\n# Break the Gmail MIME-part schema cycle only for Muse; retain all tools.\npayload:\n  override:\n    - models:\n        - name: "muse-spark-1.3-contributor"\n          protocol: "codex"\n      params:\n'
for path in paths:block+='        '+json.dumps(path)+': '+json.dumps(replacement)+'\n'
block+='# END MUSE SCHEMA COMPATIBILITY\n'
private=Path.home()/'.codex/cliproxyapi';stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
b=private/('proxy.before-muse-schema.'+stamp+'.conf')
fd=os.open(b,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write(s)
p.write_text(s+block);p.chmod(0o600)
print('Muse-only Gmail schema compatibility rule installed; original config backed up.')
