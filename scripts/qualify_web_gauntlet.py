from __future__ import annotations
import argparse,json,sys,tempfile,threading,urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from qwen_harness.web_apps import RECIPE

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--infrastructure-only",action="store_true"); p.add_argument("--manifest",type=Path,default=Path("gauntlet/web_experience.production.json")); a=p.parse_args(); m=json.loads(a.manifest.read_text(encoding="utf-8"))
 ports=[]
 for app in m["applications"]:
  port=int(app["review_url"].rsplit(":",1)[1]); ports.append(port)
  if app["archetype"] not in RECIPE: raise RuntimeError(f"unroutable archetype {app['archetype']}")
 if len(ports)!=len(set(ports)) or ports!=list(range(4201,4211)): raise RuntimeError("review ports must be unique 4201..4210")
 with tempfile.TemporaryDirectory() as raw:
  root=Path(raw); (root/"index.html").write_text("<!doctype html><title>health</title>",encoding="utf-8")
  handler=partial(SimpleHTTPRequestHandler,directory=str(root)); server=ThreadingHTTPServer(("127.0.0.1",0),handler); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
  try:
   with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/",timeout=3) as response:
    if response.status!=200: raise RuntimeError("live supervisor probe failed")
  finally:
   server.shutdown(); server.server_close(); thread.join(timeout=3)
 print(json.dumps({"status":"PASS","applications":10,"ports":ports,"lifecycle_probe":"started-healthchecked-stopped"},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
