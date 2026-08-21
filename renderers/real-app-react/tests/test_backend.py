from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import serve_in_thread


def call(base:str,method:str,path:str,body:dict|None=None,token:str|None=None)->tuple[int,dict]:
    headers={"Content-Type":"application/json"}
    if token:headers["Authorization"]="Bearer "+token
    request=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
    try:
        with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as exc:return exc.code,json.load(exc)


def test_social_runtime_authorization_invariants_and_restart_persistence()->None:
    with tempfile.TemporaryDirectory() as temp:
        db=Path(temp)/"app.sqlite3";server,thread=serve_in_thread(db,Path(temp));base=f"http://127.0.0.1:{server.server_port}"
        try:
            _,member=call(base,"POST","/api/login",{"username":"mara","password":"member-pass"});mt=member["token"]
            status,_=call(base,"GET","/api/moderation",token=mt);assert status==403
            status,match=call(base,"POST","/api/matches/interest",{},mt);assert status==201 and match["status"]=="mutual"
            status,message=call(base,"POST","/api/messages",{"match_id":match["id"],"body":"Hello with consent"},mt);assert status==201 and message["delivered"]
            status,plan=call(base,"POST","/api/plans",{"venue":"Reading Room","starts_at":"Saturday 16:00"},mt);assert status==201
            assert call(base,"POST",f"/api/plans/{plan['id']}/checkin",{},mt)[0]==200
            assert call(base,"POST",f"/api/plans/{plan['id']}/confirm",{},mt)[1]["status"]=="confirmed"
            assert call(base,"POST","/api/verification",{},mt)[1]["status"]=="approved"
            status,report=call(base,"POST","/api/reports",{"summary":"Unwanted contact"},mt);assert status==201
            assert call(base,"POST","/api/blocks",{},mt)[1]["blocked"]
            assert call(base,"POST","/api/messages",{"match_id":match["id"],"body":"must fail"},mt)[0]==409
            _,moderator=call(base,"POST","/api/login",{"username":"moderator","password":"moderator-pass"});mod=moderator["token"]
            assert call(base,"POST",f"/api/reports/{report['id']}/decision",{"decision":"warn_and_restrict"},mod)[1]["status"]=="resolved"
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
        server,thread=serve_in_thread(db,Path(temp));base=f"http://127.0.0.1:{server.server_port}"
        try:
            _,member=call(base,"POST","/api/login",{"username":"mara","password":"member-pass"});state=call(base,"GET","/api/bootstrap",token=member["token"])[1]
            assert state["verified"] and state["blocked"] and state["plans"][0]["status"]=="confirmed" and state["reports"][0]["status"]=="resolved"
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
