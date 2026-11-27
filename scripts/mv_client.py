import json,sys,urllib.request
def rpc(method,params=None,sid=None,i=1):
    h={"Authorization":"Bearer proxy-injected","Content-Type":"application/json","Accept":"application/json, text/event-stream"}
    if sid: h["mcp-session-id"]=sid
    req=urllib.request.Request("https://mcp.metaview.ai/mcp",data=json.dumps({"jsonrpc":"2.0","id":i,"method":method,"params":params or {}}).encode(),headers=h)
    r=urllib.request.urlopen(req,timeout=120); sid=r.headers.get("mcp-session-id") or sid; body=r.read().decode()
    data=[json.loads(l[5:]) for l in body.splitlines() if l.startswith("data:")] or ([json.loads(body)] if body.strip() else [])
    return (data[-1] if data else {}), sid
_sid=None
def tool(name,args,i=10):
    global _sid
    if not _sid:
        _,_sid=rpc("initialize",{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"gtm-migration","version":"1.0"}})
    res,_=rpc("tools/call",{"name":name,"arguments":{**args,"rationale":"Migrating candidate call notes into the CRM"}},_sid,i)
    c=res.get('result',{}).get('content',[{}])
    return c[0].get('text','') if c else json.dumps(res)[:500]
