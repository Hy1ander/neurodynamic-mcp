"""Offline container MCP handshake; no wallet, payment, or network."""
import json, subprocess
messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'container-smoke','version':'1'}}},
          {'jsonrpc':'2.0','method':'notifications/initialized'},
          {'jsonrpc':'2.0','id':2,'method':'tools/list'}]
r=subprocess.run(['docker','run','--rm','-i','--network','none','--read-only',
    '--tmpfs','/data:rw,uid=10001,gid=10001,mode=0700','neurodynamic-mcp:test'],
    input=''.join(json.dumps(m)+'\n' for m in messages),capture_output=True,text=True,timeout=30)
assert r.returncode==0,r.stderr
responses=[json.loads(line) for line in r.stdout.splitlines() if line.strip()]
listing=next(x for x in responses if x.get('id')==2)
assert 'error' not in listing,listing
tools=listing['result']['tools']
names={t['name'] for t in tools}
expected={'catalogue','quote','budget_status','payment_status','purchase_json',
          'transcribe_file','transcript_package_file','extract_pdf_file','ocr_image_file'}
assert names==expected,{'missing':sorted(expected-names),'unexpected':sorted(names-expected)}
assert len(tools)==len(expected),'Duplicate tool names returned'
print('Offline non-root read-only container initialized; all nine expected tools listed; no network/payment.')
