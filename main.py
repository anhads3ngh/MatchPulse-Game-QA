"""MatchPulse local HTTP application. Python standard library only.

Launch: python3 main.py
Open:   http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from engine import (FEATURES, PLATFORMS, SEVERITIES, STATES, SUITES, OWNERS,
                    connect, init, overview, issues, issue_detail, update_issue,
                    recent_runs, run_detail, generate_run, issue_similarity,
                    release_report, export_issues_csv)

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DB_PATH = ROOT / "data" / "matchpulse.db"


def prepare(path=DB_PATH, reset=False):
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        init(db,reset=reset)
    return path


def route_api(db,method,path,query=None,payload=None):
    query=query or {}
    payload=payload or {}
    def q(name,default):return query.get(name,[default])[0]
    def parse_int(value,default):
        try:return int(value)
        except (TypeError,ValueError):raise ValueError("Invalid integer value")
    if method=="GET":
        if path=="/api/health":return 200,{"ok":True,"service":"MatchPulse","synthetic":True}
        if path=="/api/config":return 200,{"features":FEATURES,"platforms":PLATFORMS,"severities":SEVERITIES,"statuses":STATES,"owners":OWNERS,"suites":list(SUITES)}
        if path=="/api/overview":return 200,overview(db,parse_int(q("days",14),14),q("platform","All"))
        if path=="/api/issues":return 200,{"issues":issues(db,q("search",""),q("severity","All"),q("status","All"),q("feature","All"),q("platform","All"))}
        if path=="/api/runs":return 200,{"runs":recent_runs(db)}
        if path=="/api/report.md":return 200,release_report(db,parse_int(q("days",14),14),q("platform","All"))
        if path=="/api/issues.csv":return 200,export_issues_csv(db)
        if path.startswith("/api/issues/"):
            ident=parse_int(path.rsplit("/",1)[-1],0)
            item=issue_detail(db,ident)
            if not item:return 404,{"error":"Issue not found"}
            item["similar"] = issue_similarity(db,ident)
            return 200,item
        if path.startswith("/api/runs/"):
            ident=parse_int(path.rsplit("/",1)[-1],0)
            item=run_detail(db,ident)
            return (200,item) if item else (404,{"error":"Run not found"})
    elif method=="POST":
        if path=="/api/runs":
            suite=payload.get("suite","Full Regression")
            platform=payload.get("platform","PC")
            seed=payload.get("seed",2718)
            if type(seed) is not int:raise ValueError("Seed must be an integer")
            ident=generate_run(db,suite,platform,seed)
            return 201,run_detail(db,ident)
        if path=="/api/reset":
            init(db,reset=True)
            return 200,{"ok":True,"message":"Synthetic fixture reset"}
    elif method=="PATCH":
        if path.startswith("/api/issues/"):
            ident=parse_int(path.rsplit("/",1)[-1],0)
            field=payload.get("field")
            value=payload.get("value")
            item=update_issue(db,ident,field,value)
            return (200,item) if item else (404,{"error":"Issue not found"})
    return 404,{"error":"Endpoint not found"}


class Handler(BaseHTTPRequestHandler):
    server_version="MatchPulse/1.0"
    def log_message(self,fmt,*args):
        print("[HTTP] %s - %s"%(self.address_string(),fmt%args))

    def send_body(self,status,body,mime="application/json; charset=utf-8",extra_headers=None):
        if isinstance(body,(dict,list)):
            encoded=json.dumps(body,ensure_ascii=False).encode("utf-8")
        elif isinstance(body,str):encoded=body.encode("utf-8")
        else:encoded=body
        self.send_response(status)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(encoded)))
        self.send_header("Cache-Control","no-store" if mime.startswith("application/json") else "public, max-age=60")
        self.send_header("X-Content-Type-Options","nosniff")
        for key,value in (extra_headers or {}).items():self.send_header(key,value)
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):self.dispatch("GET")
    def do_POST(self):self.dispatch("POST")
    def do_PATCH(self):self.dispatch("PATCH")

    def dispatch(self,method):
        parts=urlsplit(self.path)
        if not parts.path.startswith("/api/"):
            if method!="GET":return self.send_body(405,{"error":"Method not allowed"})
            path=parts.path.strip("/") or "index.html"
            target=(WEB/path).resolve()
            if not target.is_relative_to(WEB.resolve()) or not target.is_file():
                return self.send_body(404,{"error":"File not found"})
            mime=mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if mime in ("text/html","text/css","application/javascript","image/svg+xml"):
                mime += "; charset=utf-8"
            return self.send_body(200,target.read_bytes(),mime)
        try:
            payload=None
            if method in ("POST","PATCH"):
                length=int(self.headers.get("Content-Length","0"))
                if length>65536:return self.send_body(413,{"error":"Request too large"})
                try:payload=json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                except (ValueError,UnicodeDecodeError):return self.send_body(400,{"error":"Invalid JSON body"})
                if not isinstance(payload,dict):return self.send_body(400,{"error":"Expected JSON object"})
            with connect(self.server.database) as db:
                status,body=route_api(db,method,parts.path,parse_qs(parts.query),payload)
            if parts.path=="/api/report.md" and isinstance(body,str):
                return self.send_body(status,body,"text/markdown; charset=utf-8")
            if parts.path=="/api/issues.csv" and isinstance(body,str):
                return self.send_body(status,body,"text/csv; charset=utf-8")
            self.send_body(status,body)
        except (ValueError,OverflowError) as e:
            self.send_body(400,{"error":str(e)})
        except sqlite3.Error as e:
            print("[DATABASE]",str(e))
            self.send_body(500,{"error":"Database operation failed"})


def main():
    ap=argparse.ArgumentParser(description="MatchPulse: fictional football-game QA analytics dashboard")
    ap.add_argument("--port",type=int,default=8765)
    ap.add_argument("--reset",action="store_true",help="Regenerate synthetic demo data")
    ap.add_argument("--db",type=Path,default=DB_PATH)
    args=ap.parse_args()
    database=prepare(args.db,reset=args.reset)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    server.database=database
    print("\n  MATCHPULSE  /  GAME QUALITY INTELLIGENCE")
    print("  --------------------------------------")
    print(f"  Local dashboard  http://127.0.0.1:{args.port}")
    print(f"  Demo database    {database}")
    print("  Synthetic data only. Press Ctrl+C to stop.\n",flush=True)
    try:server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=="__main__":main()
