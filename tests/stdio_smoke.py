import asyncio,json,sys
from pathlib import Path
from mcp import Client,StdioServerParameters
async def main():
 server=StdioServerParameters(command=sys.executable,args=["-m", "neurodynamic_mcp"])
 async with Client(server) as c:
  tools=await c.list_tools()
  print('tools',','.join(t.name for t in tools.tools))
  for name,args in [('budget_status',{}),('catalogue',{'kind':'voices'}),('quote',{'service':'narration'}),('quote',{'service':'transcription'}),('quote',{'service':'abliterated'}),('quote',{'service':'abliterated-large'})]:
   r=await c.call_tool(name,args)
   if r.is_error:raise RuntimeError(str(r.content))
   if not isinstance(r.structured_content,dict):raise RuntimeError('Missing structured output')
   print(name,args,'OK')
  r=await c.call_tool('purchase_json',{'service':'narration','body':{'input':'Do not purchase'},'purchase_id':'disabled-test','confirm_purchase':True})
  if not r.is_error:raise RuntimeError('Read-only adapter allowed purchase')
  print('disabled purchase rejected OK')
asyncio.run(main())
