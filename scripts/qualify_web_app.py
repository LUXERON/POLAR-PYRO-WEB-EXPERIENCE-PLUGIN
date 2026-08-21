from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from polar_pyro_web_experience.web_apps import qualify_application,start_review_service

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--app",required=True); p.add_argument("--manifest",type=Path,default=Path("gauntlet/web_experience.production.json")); a=p.parse_args()
 manifest_path=a.manifest.resolve(); manifest=json.loads(manifest_path.read_text(encoding="utf-8")); workspace=(manifest_path.parent/manifest["workspace_root"]).resolve(); harness=Path(__file__).resolve().parents[1]
 receipt=qualify_application(workspace=workspace,harness=harness,manifest=manifest,app_id=a.app)
 app=next(item for item in manifest["applications"] if item["id"]==a.app); port=int(app["review_url"].rsplit(":",1)[1])
 pid=start_review_service(dist=harness/"runtime/web-experience-gauntlet/applications"/a.app/"review-app/dist",port=port,pid_file=harness/"runtime/web-experience-gauntlet/applications"/a.app/"service.pid")
 print(json.dumps({"receipt":receipt,"review_service_pid":pid},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
