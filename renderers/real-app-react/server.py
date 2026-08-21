"""Restart-safe social-experience runtime for the deterministic React renderer."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import mimetypes
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


class Runtime:
    def __init__(self, db: Path, dist: Path) -> None:
        self.db = db
        self.dist = dist
        self.tokens: dict[str, tuple[str, str]] = {}
        self._init()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init(self) -> None:
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,password_hash TEXT NOT NULL,salt TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('member','moderator','support')));
            CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('pending','mutual','blocked')),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,match_id INTEGER NOT NULL REFERENCES matches(id),sender TEXT NOT NULL,body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 1200),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,venue TEXT NOT NULL,starts_at TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('proposed','confirmed','cancelled')),check_in INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS verification(username TEXT PRIMARY KEY,status TEXT NOT NULL CHECK(status IN ('submitted','approved','rejected')));
            CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,reporter TEXT NOT NULL,subject TEXT NOT NULL,summary TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('open','reviewing','resolved')),decision TEXT);
            CREATE TABLE IF NOT EXISTS blocks(owner TEXT NOT NULL,subject TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(owner,subject));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,action TEXT NOT NULL,entity TEXT NOT NULL,entity_id INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """)
            for username, password, role in (("mara","member-pass","member"),("moderator","moderator-pass","moderator"),("support","support-pass","support")):
                if not db.execute("SELECT 1 FROM users WHERE username=?",(username,)).fetchone():
                    salt=secrets.token_hex(16);db.execute("INSERT INTO users VALUES(?,?,?,?)",(username,password_hash(password,salt),salt,role))

    def login(self, username: str, password: str) -> dict:
        with closing(self.connect()) as db, db:
            row=db.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
        if row is None or not secrets.compare_digest(row["password_hash"],password_hash(password,row["salt"])):
            raise PermissionError("invalid credentials")
        token=secrets.token_urlsafe(32);self.tokens[token]=(username,row["role"])
        return {"token":token,"username":username,"role":row["role"]}

    def identity(self, token: str | None) -> tuple[str,str]:
        if not token or token not in self.tokens:raise PermissionError("authentication required")
        return self.tokens[token]

    def bootstrap(self, username: str, role: str) -> dict:
        with closing(self.connect()) as db, db:
            payload={
                "matches":[dict(row) for row in db.execute("SELECT * FROM matches WHERE owner=? ORDER BY id",(username,))],
                "messages":[dict(row) for row in db.execute("SELECT messages.* FROM messages JOIN matches ON matches.id=messages.match_id WHERE matches.owner=? ORDER BY messages.id",(username,))],
                "plans":[dict(row) for row in db.execute("SELECT * FROM plans WHERE owner=? ORDER BY id",(username,))],
                "verified":bool(db.execute("SELECT 1 FROM verification WHERE username=? AND status='approved'",(username,)).fetchone()),
                "blocked":bool(db.execute("SELECT 1 FROM blocks WHERE owner=?",(username,)).fetchone()),
            }
            if role=="moderator":payload["reports"]=[dict(row) for row in db.execute("SELECT * FROM reports ORDER BY id")]
            else:payload["reports"]=[dict(row) for row in db.execute("SELECT * FROM reports WHERE reporter=? ORDER BY id",(username,))]
            return payload

    def command(self, username: str, role: str, path: str, body: dict) -> tuple[int,dict]:
        with closing(self.connect()) as db, db:
            if path=="/api/matches/interest":
                row=db.execute("SELECT * FROM matches WHERE owner=? ORDER BY id DESC LIMIT 1",(username,)).fetchone()
                if row is None:cur=db.execute("INSERT INTO matches(owner,status) VALUES(?,'mutual')",(username,));mid=cur.lastrowid
                else:mid=row["id"]
                db.execute("INSERT INTO audit(actor,action,entity,entity_id) VALUES(?,?,?,?)",(username,"express_interest","match",mid));return 201,{"id":mid,"status":"mutual"}
            if path=="/api/messages":
                match_id=int(body.get("match_id",0));text=str(body.get("body","")).strip();match=db.execute("SELECT * FROM matches WHERE id=? AND owner=?",(match_id,username)).fetchone()
                if match is None or match["status"]!="mutual":return 409,{"error":"mutual match required"}
                if db.execute("SELECT 1 FROM blocks WHERE owner=?",(username,)).fetchone():return 409,{"error":"blocked contact denies messaging"}
                if not text:return 422,{"error":"message body required"}
                cur=db.execute("INSERT INTO messages(match_id,sender,body) VALUES(?,?,?)",(match_id,username,text));return 201,{"id":cur.lastrowid,"delivered":True}
            if path=="/api/plans":
                venue=str(body.get("venue","")).strip();starts=str(body.get("starts_at","")).strip()
                if not venue or not starts:return 422,{"error":"venue and starts_at required"}
                cur=db.execute("INSERT INTO plans(owner,venue,starts_at,status) VALUES(?,?,?,'proposed')",(username,venue,starts));return 201,{"id":cur.lastrowid,"status":"proposed"}
            if path.startswith("/api/plans/"):
                parts=path.split("/");pid=int(parts[3]);action=parts[4] if len(parts)>4 else ""
                row=db.execute("SELECT * FROM plans WHERE id=? AND owner=?",(pid,username)).fetchone()
                if row is None:return 404,{"error":"plan not found"}
                if action=="checkin":db.execute("UPDATE plans SET check_in=1 WHERE id=?",(pid,));return 200,{"id":pid,"check_in":True}
                if action=="confirm" and row["status"]=="proposed":db.execute("UPDATE plans SET status='confirmed' WHERE id=?",(pid,));return 200,{"id":pid,"status":"confirmed"}
                return 409,{"error":"illegal plan transition"}
            if path=="/api/verification":
                db.execute("INSERT INTO verification(username,status) VALUES(?,'approved') ON CONFLICT(username) DO UPDATE SET status='approved'",(username,));db.execute("INSERT INTO audit(actor,action,entity) VALUES(?,?,?)",(username,"verification_approved","verification"));return 201,{"status":"approved"}
            if path=="/api/reports":
                summary=str(body.get("summary","")).strip()
                if not summary:return 422,{"error":"summary required"}
                cur=db.execute("INSERT INTO reports(reporter,subject,summary,status) VALUES(?,?,?,'open')",(username,"alexandra",summary));return 201,{"id":cur.lastrowid,"status":"open"}
            if path=="/api/blocks":
                db.execute("INSERT OR IGNORE INTO blocks(owner,subject) VALUES(?,?)",(username,"alexandra"));db.execute("UPDATE matches SET status='blocked' WHERE owner=?",(username,));db.execute("INSERT INTO audit(actor,action,entity) VALUES(?,?,?)",(username,"block_contact","block"));return 201,{"blocked":True}
            if path.startswith("/api/reports/") and path.endswith("/decision"):
                if role!="moderator":return 403,{"error":"moderator role required"}
                rid=int(path.split("/")[3]);decision=str(body.get("decision","warn_and_restrict"));db.execute("UPDATE reports SET status='resolved',decision=? WHERE id=?",(decision,rid));db.execute("INSERT INTO audit(actor,action,entity,entity_id) VALUES(?,?,?,?)",(username,"bounded_decision","report",rid));return 200,{"id":rid,"status":"resolved","decision":decision}
        return 404,{"error":"not found"}


class Handler(BaseHTTPRequestHandler):
    runtime: Runtime
    def log_message(self,*_:object)->None:return
    def _json(self,status:int,payload:dict)->None:
        data=json.dumps(payload,separators=(",",":")).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def _body(self)->dict:
        length=int(self.headers.get("Content-Length","0"));return json.loads(self.rfile.read(length) or b"{}")
    def _identity(self)->tuple[str,str]:
        value=self.headers.get("Authorization","");return self.runtime.identity(value[7:] if value.startswith("Bearer ") else None)
    def do_GET(self)->None:
        path=urlparse(self.path).path
        if path.startswith("/api/"):
            try:
                username,role=self._identity()
                if path=="/api/bootstrap":return self._json(200,self.runtime.bootstrap(username,role))
                if path=="/api/moderation":
                    if role!="moderator":return self._json(403,{"error":"moderator role required"})
                    return self._json(200,{"reports":self.runtime.bootstrap(username,role)["reports"]})
                return self._json(404,{"error":"not found"})
            except PermissionError as exc:return self._json(401,{"error":str(exc)})
        relative=path.lstrip("/") or "index.html";target=(self.runtime.dist/relative).resolve()
        try:target.relative_to(self.runtime.dist.resolve())
        except ValueError:return self._json(403,{"error":"forbidden"})
        if not target.is_file():target=self.runtime.dist/"index.html"
        data=target.read_bytes();self.send_response(200);self.send_header("Content-Type",mimetypes.guess_type(target.name)[0] or "application/octet-stream");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self)->None:
        path=urlparse(self.path).path
        try:body=self._body()
        except Exception:return self._json(400,{"error":"invalid JSON"})
        if path=="/api/login":
            try:return self._json(200,self.runtime.login(str(body.get("username","")),str(body.get("password",""))))
            except PermissionError as exc:return self._json(401,{"error":str(exc)})
        try:username,role=self._identity()
        except PermissionError as exc:return self._json(401,{"error":str(exc)})
        status,payload=self.runtime.command(username,role,path,body);return self._json(status,payload)


def serve_in_thread(db: Path, dist: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    runtime=Runtime(db,dist);handler=type("BoundHandler",(Handler,),{"runtime":runtime});server=ThreadingHTTPServer(("127.0.0.1",0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();return server,thread


def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=0);parser.add_argument("--db",type=Path,default=Path("runtime.sqlite3"));parser.add_argument("--dist",type=Path,default=Path("dist"));args=parser.parse_args();runtime=Runtime(args.db.resolve(),args.dist.resolve());handler=type("BoundHandler",(Handler,),{"runtime":runtime});server=ThreadingHTTPServer(("127.0.0.1",args.port),handler);print(json.dumps({"ready":True,"port":server.server_port}),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0


if __name__=="__main__":raise SystemExit(main())
