from __future__ import annotations
import json
from pathlib import Path
from qwen_harness.web_apps import RECIPE

ROOT=Path(__file__).resolve().parents[2]
def test_all_ten_apps_have_unique_ports_projects_and_renderer_routes()->None:
 m=json.loads((ROOT/"gauntlet/web_experience.production.json").read_text(encoding="utf-8")); assert len(m["applications"])==10
 ports=[]
 for app in m["applications"]:
  assert app["archetype"] in RECIPE; assert (ROOT.parent/app["project"]).exists()
  ports.append(int(app["review_url"].rsplit(":",1)[1]))
 assert sorted(ports)==list(range(4201,4211))
