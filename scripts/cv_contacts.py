#!/usr/bin/env python3
"""For Spott candidates missing LinkedIn or email: download their CV from Spott and pull LinkedIn URLs, emails and
phones from the PDF's text and link annotations (no AI). Writes state/cv_contacts.jsonl. Usage: cv_contacts.py [N]"""
import json, os, re, sys, time, urllib.request, io
from pypdf import PdfReader
S = os.path.join(os.path.dirname(__file__), "..", "state")
def api(path, raw=False):
    r = urllib.request.urlopen(urllib.request.Request("https://api.gospott.com" + path, headers={"x-api-key": "proxy-injected"}), timeout=90).read()
    time.sleep(0.3); return r if raw else json.loads(r)
gaps = json.load(open(os.path.join(S, "contact_gaps.json")))
ids = list(dict.fromkeys(gaps["noli"] + gaps["noem"]))
N = int(sys.argv[1]) if len(sys.argv) > 1 else len(ids)
outp = os.path.join(S, "cv_contacts.jsonl")
done = {json.loads(l)["id"] for l in open(outp)} if os.path.exists(outp) else set()
out = open(outp, "a")
LI = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+", re.I)
EM = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PH = re.compile(r"\+\d[\d\s().\-]{7,16}\d")
for cid in ids[:N]:
    if cid in done: continue
    rec = {"id": cid, "has_cv": False, "linkedin": [], "emails": [], "phones": [], "err": None}
    try:
        att = [a for a in api(f"/attachments?candidateId={cid}").get("items", []) if a.get("type") == "CV"]
        if att:
            rec["has_cv"] = True
            info = api(f"/attachments/{att[0]['attachmentId']}/_download")
            url = info.get("url") or info.get("downloadUrl") or info.get("signedUrl")
            blob = urllib.request.urlopen(url, timeout=120).read()
            txt, links = "", []
            if blob[:4] == b"%PDF":
                pdf = PdfReader(io.BytesIO(blob))
                for pg in pdf.pages[:6]:
                    try: txt += (pg.extract_text() or "") + "\n"
                    except Exception: pass
                    for a in (pg.get("/Annots") or []):
                        try:
                            u = a.get_object().get("/A", {}).get("/URI")
                            if u: links.append(str(u))
                        except Exception: pass
            hay = txt + "\n" + "\n".join(links)
            rec["linkedin"] = sorted({m.group(0).rstrip("/").lower() for m in LI.finditer(hay)})
            rec["emails"] = sorted({m.group(0).lower().rstrip(".") for m in EM.finditer(hay.replace("mailto:", " "))})
            rec["phones"] = sorted({re.sub(r"[^\d+]", "", m.group(0)) for m in PH.finditer(txt)})
    except Exception as e:
        rec["err"] = str(e)[:150]
    out.write(json.dumps(rec) + "\n"); out.flush()
print("done")
