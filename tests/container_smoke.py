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
names={t['name'] for t in listing['result']['tools']}
assert len(names)==6,names
print('Offline non-root read-only container initialized; six tools listed; no network/payment.')
