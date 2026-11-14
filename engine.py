"""MatchPulse: deterministic synthetic football-game quality analytics.

All gameplay sessions and defects are generated for this independent portfolio demo.
No EA data, game client integration, or production telemetry is involved.
"""
from __future__ import annotations

import csv
import io
import math
import random
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

FEATURES = ["Match Flow", "Online Play", "Ultimate Team", "Career Mode", "Menus & UI", "Audio & Visuals"]
PLATFORMS = ["PC", "PlayStation", "Xbox"]
SUITES = {
    "Full Regression": ["Match Flow", "Online Play", "Ultimate Team", "Career Mode", "Menus & UI", "Audio & Visuals"],
    "Gameplay Smoke": ["Match Flow", "Online Play"],
    "Online Reliability": ["Online Play", "Ultimate Team"],
    "Interface & Accessibility": ["Menus & UI", "Audio & Visuals"],
    "Career Persistence": ["Career Mode", "Match Flow"],
}
TEST_NAMES = {
    "Match Flow": ["Halftime resume after substitution", "Penalty shootout persistence", "Goal replay → kickoff transition", "Offside decision UI synchronization", "Extra-time match completion"],
    "Online Play": ["Cross-platform lobby invitation", "Reconnect during second half", "High latency match state recovery", "Ranked matchmaking timeout", "Opponent disconnect handling"],
    "Ultimate Team": ["Squad save after formation swap", "Transfer market filtering", "Card selection state persistence", "Squad chemistry calculation", "Pack opening animation completion"],
    "Career Mode": ["Career autosave recovery", "Player transfer confirmation", "Season advancement simulation", "Training plan persistence", "Manager objective progression"],
    "Menus & UI": ["Controller navigation focus order", "Localization overflow detection", "Settings persistence after restart", "Menu transition latency", "High contrast control labels"],
    "Audio & Visuals": ["Stadium crowd audio fade", "Replay camera clipping check", "Jersey texture streaming", "Commentary subtitle synchronization", "Goal celebration animation"],
}
ISSUE_TEMPLATES = [
    ("Match Flow", "Goal replay freezes after overtime equalizer", "Replay overlay remains active while match simulation resumes.", "Reproduction: Start a match, reach extra time, score an equalizer, then select instant replay.", "Replay exits and gameplay resumes within 2 seconds.", "Camera remains locked on the replay and controls become unresponsive."),
    ("Match Flow", "Scoreboard updates one tick late after penalty", "Match HUD briefly displays stale score after the goal event.", "Reproduction: Start a cup match, reach penalty shootout, score the fifth penalty.", "HUD updates on the same event as the score change.", "Scoreboard lags one state transition."),
    ("Match Flow", "Halftime substitution resets stamina indicator", "Player stamina HUD resets when halftime menu closes.", "Reproduction: Run to halftime, change lineup, resume play.", "Stamina reflects actual player state after substitution.", "Selected player's stamina displays 100% unexpectedly."),
    ("Online Play", "Ranked match desync following network reconnect", "Client match state diverges when the network reconnects during a live fixture.", "Reproduction: Begin ranked match, interrupt connection for 5 seconds, reconnect.", "Client restores synchronized ball and score state.", "Ball and score disagree between clients for several seconds."),
    ("Online Play", "Lobby invite fails after cross-platform party join", "Party invite disappears after a cross-platform join operation.", "Reproduction: Create a party on PC, join using a console user, send an invite.", "Invite reaches the recipient and appears in their inbox.", "Invite silently disappears without a notification."),
    ("Online Play", "Opponent disconnect leads to indefinite loading", "Match completion loading indicator never resolves on opponent exit.", "Reproduction: Enter online fixture, request opponent to leave after 70th minute.", "Result persists and player returns to lobby.", "Spinner remains visible indefinitely."),
    ("Ultimate Team", "Squad formation not persisted after rapid edits", "Back-to-back squad changes leave an outdated formation in local view.", "Reproduction: Open squad builder, change formation twice quickly, save squad.", "Last saved formation appears on reload.", "Previously selected formation is restored."),
    ("Ultimate Team", "Transfer filter produces stale market count", "Transfer market count fails to refresh after clearing rare-player filters.", "Reproduction: Apply rare filter, clear all filters, change page.", "Result count reflects current filters.", "Result count remains from preceding selection."),
    ("Ultimate Team", "Pack animation audio persists into next screen", "Pack opening audio loop does not terminate on skip.", "Reproduction: Open demo pack, skip animation, enter squad screen.", "Audio stops when view exits.", "Pack audio continues over squad controls."),
    ("Career Mode", "Autosave race condition on season transition", "Autosave operation occasionally logs old season metadata.", "Reproduction: Advance career season while triggering a second save event.", "Save snapshot uses latest season state.", "Save metadata retains previous season."),
    ("Career Mode", "Training plan selection reverts after restart", "Training plan selection fails persistence validation.", "Reproduction: Change plan for two players, leave Career screen, restart session.", "Selections persist across restarts.", "Default plans reappear after launch."),
    ("Career Mode", "Manager objective progress clipped in summary", "Long objective labels truncate beyond container bounds.", "Reproduction: Enter end-of-month objective summary with a long objective name.", "Objectives wrap or scroll and remain legible.", "Text extends outside summary panel."),
    ("Menus & UI", "Controller focus skips accessibility settings", "Keyboard and controller focus order omits accessibility entry on rapid navigation.", "Reproduction: Open settings, navigate using D-pad with quick repeated input.", "Every focusable element receives predictable focus.", "Accessibility settings tile is skipped."),
    ("Menus & UI", "Localized menu label overflows at 200% scaling", "Long localized string intersects adjacent input at larger text scales.", "Reproduction: Select German, increase text scaling to 200%, open settings.", "Controls stay readable and avoid overlap.", "Label clips into adjacent selection field."),
    ("Menus & UI", "Filter selections reset after back navigation", "Current filter is lost when leaving and returning to a menu.", "Reproduction: Set menu filters, open details, press back.", "Previously selected filters are preserved.", "Filter list resets to defaults."),
    ("Audio & Visuals", "Crowd ambience loops after pause transition", "Crowd ambience continues at full volume after pausing the match.", "Reproduction: Enter stadium fixture, pause during goal replay.", "Audio ducking applies during pause overlay.", "Crowd volume remains at match level."),
    ("Audio & Visuals", "Goal replay camera clips through advertising boards", "Replay camera passes through geometry near the touchline.", "Reproduction: Score from sideline at the edge of the box, trigger replay.", "Camera remains outside static geometry.", "Camera intersects advertisement geometry."),
    ("Audio & Visuals", "Subtitle timing drifts during commentary overlap", "Subtitles appear late when two voice events play in sequence.", "Reproduction: Score during an injury-time commentary event.", "Subtitles remain synchronized with speech.", "Subtitles display after the corresponding voice line."),
]
OWNERS = ["Unassigned", "A. Singh", "M. Chen", "J. Patel", "K. Wilson", "S. Park"]
STATES = ["Open", "In Progress", "Ready to Verify", "Resolved"]
SEVERITIES = ["Blocker", "Critical", "Major", "Minor"]


def connect(path: str | Path):
    db = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def init(db: sqlite3.Connection, seed=2718, reset=False):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY, at TEXT NOT NULL, platform TEXT NOT NULL,
      feature TEXT NOT NULL, mode TEXT NOT NULL, build TEXT NOT NULL,
      fps REAL NOT NULL, latency_ms INTEGER NOT NULL, crashed INTEGER NOT NULL,
      desync INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS sessions_at ON sessions(at);
    CREATE INDEX IF NOT EXISTS sessions_platform ON sessions(platform);
    CREATE TABLE IF NOT EXISTS issues (
      id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
      feature TEXT NOT NULL, platform TEXT NOT NULL, severity TEXT NOT NULL,
      status TEXT NOT NULL, owner TEXT NOT NULL, created_at TEXT NOT NULL,
      occurrences INTEGER NOT NULL, repro TEXT NOT NULL, expected TEXT NOT NULL,
      actual TEXT NOT NULL, build TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS issues_status ON issues(status);
    CREATE TABLE IF NOT EXISTS qa_runs (
      id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, suite TEXT NOT NULL,
      platform TEXT NOT NULL, seed INTEGER NOT NULL, passed INTEGER NOT NULL,
      failed INTEGER NOT NULL, duration_ms INTEGER NOT NULL, source TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS test_results (
      id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES qa_runs(id),
      name TEXT NOT NULL, feature TEXT NOT NULL, outcome TEXT NOT NULL,
      duration_ms INTEGER NOT NULL, note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit (
      id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES issues(id),
      at TEXT NOT NULL, action TEXT NOT NULL, before TEXT, after TEXT);
    """)
    if reset:
        for table in ("audit", "test_results", "qa_runs", "issues", "sessions"):
            db.execute(f"DELETE FROM {table}")
    exists = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if exists:
        db.commit()
        return
    rng = random.Random(seed)
    # Dates are pegged to a fixed demo clock, so screenshots and analytics are reproducible.
    now = datetime(2027, 4, 28, 18, 0, 0, tzinfo=timezone.utc)
    session_rows = []
    mode_map = {"Match Flow":"Kickoff", "Online Play":"Rivals", "Ultimate Team":"Ultimate Team",
                "Career Mode":"Career", "Menus & UI":"Front End", "Audio & Visuals":"Kickoff"}
    for day in range(30):
        reference = now - timedelta(days=29-day)
        for slot in range(82 + (day % 5)*9):
            feature = rng.choices(FEATURES,weights=[29,23,17,13,10,8])[0]
            platform = rng.choices(PLATFORMS,weights=[34,36,30])[0]
            hour = rng.randrange(24)
            minute = rng.randrange(60)
            minute_at = reference.replace(hour=hour,minute=minute,second=rng.randrange(60))
            # Deliberately inject an elevated crash band for Online Play around days 24-26.
            cluster_spike = day in (23,24,25) and feature == "Online Play" and platform == "PC"
            probability = 0.008 + (0.022 if feature == "Online Play" else 0) + (0.14 if cluster_spike else 0)
            crashed = int(rng.random() < probability)
            desync = int(feature == "Online Play" and rng.random() < (0.10 if cluster_spike else 0.024))
            fps = max(18, rng.gauss(72 if platform == "PC" else 59, 10))
            if crashed: fps *= 0.67
            latency = max(8,int(rng.gauss(54 if feature == "Online Play" else 27, 21)))
            if desync: latency += 120
            session_rows.append((minute_at.isoformat(),platform,feature,mode_map[feature],
                                 "27.4.18",round(fps,1),latency,crashed,desync))
    db.executemany("INSERT INTO sessions(at,platform,feature,mode,build,fps,latency_ms,crashed,desync) VALUES (?,?,?,?,?,?,?,?,?)",session_rows)
    issue_rows=[]
    for i in range(104):
        feature,title,description,repro,expected,actual=ISSUE_TEMPLATES[i%len(ISSUE_TEMPLATES)]
        platform=rng.choice(PLATFORMS)
        severity = rng.choices(SEVERITIES,weights=[7,20,45,28])[0]
        status = rng.choices(STATES,weights=[37,23,15,25])[0]
        variant = ["", " — intermittent", " on resume", " after rapid input", " in build 27.4.18", " on high latency"][i//len(ISSUE_TEMPLATES)%6]
        # Preserve near-duplicate descriptions for meaningful NLP similarity rankings.
        desc = description + (" Observed during exploratory regression." if i%3 else "")
        at=(now-timedelta(days=rng.randrange(0,29),hours=rng.randrange(0,18))).isoformat()
        issue_rows.append((title+variant,desc,feature,platform,severity,status,
                           rng.choice(OWNERS),at,rng.randrange(1,51),repro,expected,actual,"27.4.18"))
    db.executemany("""INSERT INTO issues(title,description,feature,platform,severity,status,owner,created_at,
                   occurrences,repro,expected,actual,build) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",issue_rows)
    for idx in range(10):
        suite=list(SUITES)[idx%len(SUITES)]
        generate_run(db,suite,PLATFORMS[idx%3],seed+idx,now-timedelta(days=10-idx),source="Seeded")
    db.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def generate_run(db, suite, platform, seed, at=None, source="Manual simulation"):
    if suite not in SUITES or platform not in PLATFORMS:
        raise ValueError("Invalid suite or platform")
    if not isinstance(seed,int) or seed<0 or seed>999999999:
        raise ValueError("Seed must be an integer between 0 and 999999999")
    rng=random.Random(seed + sum(ord(c) for c in suite+platform))
    rows=[]
    for feature in SUITES[suite]:
        for name in TEST_NAMES[feature]:
            p=0.10 + (0.06 if feature=="Online Play" else 0) + (0.025 if platform=="PC" else 0)
            passed=rng.random()>=p
            duration=rng.randrange(420,2600)
            note=("Assertion succeeded; synthetic fixture matched expected output" if passed else
                  rng.choice(["Expected state mismatch on scenario replay", "State transition timeout in simulated fixture", "Visual snapshot threshold exceeded", "Simulated event payload did not match contract"]))
            rows.append((name,feature,"Passed" if passed else "Failed",duration,note))
    passed=sum(x[2]=="Passed" for x in rows)
    failed=len(rows)-passed
    result=db.execute("INSERT INTO qa_runs(created_at,suite,platform,seed,passed,failed,duration_ms,source) VALUES (?,?,?,?,?,?,?,?)",
                      ((at.isoformat() if at else now_iso()),suite,platform,seed,passed,failed,sum(x[3] for x in rows),source))
    run_id=result.lastrowid
    db.executemany("INSERT INTO test_results(run_id,name,feature,outcome,duration_ms,note) VALUES (?,?,?,?,?,?)",
                   [(run_id,*x) for x in rows])
    db.commit()
    return run_id


def period_where(days=14,platform="All", field="at"):
    if days not in (7,14,30): raise ValueError("Days must be 7, 14 or 30")
    if platform not in ("All",*PLATFORMS): raise ValueError("Invalid platform")
    reference=datetime(2027,4,29,0,0,tzinfo=timezone.utc)-timedelta(days=days)
    where=f"{field} >= ?"+(" AND platform = ?" if platform!="All" else "")
    args=[reference.isoformat()]
    if platform!="All":args.append(platform)
    return where,args


def overview(db,days=14,platform="All"):
    where,args=period_where(days,platform)
    rows=[dict(r) for r in db.execute(f"SELECT at,platform,feature,mode,crashed,desync,fps,latency_ms FROM sessions WHERE {where}",args)]
    n=len(rows)
    crash=sum(x["crashed"] for x in rows)
    avg_fps=sum(x["fps"] for x in rows)/max(n,1)
    ds=sum(x["desync"] for x in rows)
    # Issues intentionally represent historical backlog, not just selected sessions.
    issue_extra = (" AND platform = ?" if platform!="All" else "")
    issue_args=([platform] if platform!="All" else [])
    open_blockers=db.execute("SELECT COUNT(*) FROM issues WHERE severity IN ('Blocker','Critical') AND status != 'Resolved'"+issue_extra,issue_args).fetchone()[0]
    statuses=[dict(r) for r in db.execute("SELECT severity,COUNT(*) AS total FROM issues WHERE status != 'Resolved'"+issue_extra+" GROUP BY severity",issue_args)]
    last=db.execute("SELECT * FROM qa_runs ORDER BY id DESC LIMIT 1").fetchone()
    passrate=round(100*last["passed"]/(last["passed"]+last["failed"]),1) if last else 0
    daily=defaultdict(lambda:{"sessions":0,"crashes":0,"desync":0})
    features=defaultdict(lambda:{"sessions":0,"crashes":0,"desync":0,"fps":0})
    modes=defaultdict(lambda:{"sessions":0,"crashes":0})
    platforms=defaultdict(lambda:{"sessions":0,"crashes":0,"fps":0})
    for r in rows:
        key=r["at"][:10]
        for bucket in [daily[key],features[r["feature"]],modes[r["mode"]],platforms[r["platform"]]]:
            bucket["sessions"]+=1
            bucket["crashes"]+=r["crashed"]
        daily[key]["desync"]+=r["desync"]
        features[r["feature"]]["desync"]+=r["desync"]
        features[r["feature"]]["fps"]+=r["fps"]
        platforms[r["platform"]]["fps"]+=r["fps"]
    for offset in range(days):
        key=(datetime(2027,4,28,tzinfo=timezone.utc)-timedelta(days=days-1-offset)).strftime("%Y-%m-%d")
        daily[key] # pad missing dates for sparkline stability
    feature_data=[{"name":name,"sessions":features[name]["sessions"],"crash_rate":round(100*features[name]["crashes"]/max(1,features[name]["sessions"]),2),"desync_rate":round(100*features[name]["desync"]/max(1,features[name]["sessions"]),2),"avg_fps":round(features[name]["fps"]/max(1,features[name]["sessions"]),1)} for name in FEATURES]
    platform_data=[{"name":p,"sessions":platforms[p]["sessions"],"crash_rate":round(100*platforms[p]["crashes"]/max(1,platforms[p]["sessions"]),2),"avg_fps":round(platforms[p]["fps"]/max(1,platforms[p]["sessions"]),1)} for p in PLATFORMS]
    daily_series=[{"day":key,"sessions":v["sessions"],"crashes":v["crashes"],"desync":v["desync"],"crash_rate":round(100*v["crashes"]/max(v["sessions"],1),2)} for key,v in sorted(daily.items())]
    crash_pct=100*crash/max(n,1)
    stability=max(0,min(100,100-crash_pct*7-ds/max(n,1)*65))
    return {
        "meta":{"product":"Stadium FC (fictional)","build":"27.4.18","synthetic":True,"date_label":"Apr 28, 2027","days":days,"platform":platform},
        "kpis":{"sessions":n,"crashes":crash,"crash_rate":round(crash_pct,2),"stability":round(stability,1),"avg_fps":round(avg_fps,1),"desync":ds,"open_high_priority":open_blockers,"test_pass_rate":passrate},
        "daily":daily_series,"features":feature_data,"platforms":platform_data,"modes":[{"name":k,"sessions":v["sessions"],"crash_rate":round(100*v["crashes"]/max(v["sessions"],1),2)} for k,v in modes.items()],
        "severity":{x["severity"]:x["total"] for x in statuses},
        "last_run":dict(last) if last else None,
        "recent_issues":[dict(r) for r in db.execute("SELECT id,title,severity,feature,platform,status,occurrences FROM issues ORDER BY created_at DESC,id DESC LIMIT 6")],
        "signals":risk_signals(rows,feature_data,daily_series),
    }


def risk_signals(rows,features,daily):
    messages=[]
    # Anomaly heuristic: recent 3-day crash rate vs previous 7 days using a transparent ratio.
    if len(daily)>=10:
        recent=daily[-3:]
        baseline=daily[-10:-3]
        a=sum(x["crashes"] for x in recent)/max(1,sum(x["sessions"] for x in recent))
        b=sum(x["crashes"] for x in baseline)/max(1,sum(x["sessions"] for x in baseline))
        if a > b*1.35 and a-b>=0.004:
            messages.append({"level":"High","category":"Anomaly signal","title":"Crash rate above recent baseline","detail":f"Recent 3-day crash rate {a*100:.2f}% vs previous 7-day {b*100:.2f}%.","evidence":"Rule: 3-day rate > 1.35x 7-day baseline and at least +0.4 percentage points."})
    critical=sorted(features,key=lambda f:f["crash_rate"],reverse=True)
    for f in critical[:2]:
        if f["sessions"]>=20 and f["crash_rate"]>=1:
            messages.append({"level":"Medium","category":"Feature hotspot","title":f["name"]+" needs focused regression", "detail":f"{f['crash_rate']:.2f}% crash rate across {f['sessions']:,} synthetic sessions.","evidence":"Feature ranked by observed crash frequency; not a causal diagnosis."})
    if not messages:
        messages.append({"level":"Low","category":"Watchlist","title":"No elevated signals detected","detail":"Selected session range is within configured rule thresholds.","evidence":"Simple deterministic threshold monitoring."})
    return messages[:3]


def issues(db,search="",severity="All",status="All",feature="All",platform="All",limit=150):
    query="SELECT id,title,description,feature,platform,severity,status,owner,created_at,occurrences,build FROM issues WHERE 1=1"
    args=[]
    if search.strip():
        query+=" AND (lower(title) LIKE ? OR lower(description) LIKE ? OR CAST(id AS TEXT) LIKE ?)"
        args.extend(["%"+search.strip().lower()+"%"]*3)
    for column,value,allowed in [("severity",severity,SEVERITIES),("status",status,STATES),("feature",feature,FEATURES),("platform",platform,PLATFORMS)]:
        if value!="All":
            if value not in allowed:raise ValueError("Invalid filter: "+column)
            query+=f" AND {column} = ?"
            args.append(value)
    query+=" ORDER BY CASE severity WHEN 'Blocker' THEN 0 WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 ELSE 3 END, created_at DESC LIMIT ?"
    args.append(max(1,min(limit,500)))
    return [dict(r) for r in db.execute(query,args)]


def issue_detail(db,issue_id):
    item=db.execute("SELECT * FROM issues WHERE id=?",(issue_id,)).fetchone()
    if not item:return None
    return dict(item)


def update_issue(db,issue_id,field,value):
    allowed={"status":STATES,"owner":OWNERS,"severity":SEVERITIES}
    if field not in allowed or value not in allowed[field]: raise ValueError("Invalid issue update")
    item=issue_detail(db,issue_id)
    if not item: return None
    db.execute(f"UPDATE issues SET {field} = ? WHERE id = ?",(value,issue_id))
    db.execute("INSERT INTO audit(issue_id,at,action,before,after) VALUES (?,?,?,?,?)",
               (issue_id,now_iso(),field,str(item[field]),value))
    db.commit()
    return issue_detail(db,issue_id)


def recent_runs(db,limit=15):
    return [dict(r) for r in db.execute("SELECT * FROM qa_runs ORDER BY id DESC LIMIT ?",(limit,))]


def run_detail(db,run_id):
    item=db.execute("SELECT * FROM qa_runs WHERE id=?",(run_id,)).fetchone()
    if not item:return None
    result=dict(item)
    result["results"]=[dict(r) for r in db.execute("SELECT name,feature,outcome,duration_ms,note FROM test_results WHERE run_id=? ORDER BY id",(run_id,))]
    return result


STOPWORDS={"the","and","or","after","from","when","with","into","while","for","an","in","on","a","to","is","at","of","during","then","not","does","remains","state","match","player","game","screen","menu","reproduction","expected","actual","observed","ui"}

def tokens(text):
    return [x for x in re.findall(r"[a-z0-9]+",text.lower()) if x not in STOPWORDS and len(x)>2]


def issue_similarity(db,issue_id,limit=4):
    """Explainable IDF-weighted cosine on title+description+feature text.

    This is a retrieval heuristic, not a trained neural model or a confidence estimate.
    """
    all_items=[dict(r) for r in db.execute("SELECT id,title,description,feature,platform,status,severity FROM issues")]
    target=next((x for x in all_items if x["id"]==issue_id),None)
    if not target:return []
    document_tokens=[tokens(x["title"]+" "+x["title"]+" "+x["description"]+" "+x["feature"]) for x in all_items]
    df=Counter(term for ts in document_tokens for term in set(ts))
    n=len(all_items)
    def vector(ts):
        terms=Counter(ts)
        return {term:(1+math.log(count))*(math.log((1+n)/(1+df[term]))+1) for term,count in terms.items()}
    vectors=[vector(ts) for ts in document_tokens]
    target_idx=next(i for i,x in enumerate(all_items) if x["id"]==issue_id)
    a=vectors[target_idx]
    norm_a=math.sqrt(sum(v*v for v in a.values()))
    pairs=[]
    for i,x in enumerate(all_items):
        if i==target_idx:continue
        b=vectors[i]
        norm_b=math.sqrt(sum(v*v for v in b.values()))
        similarity=sum(value*b.get(key,0) for key,value in a.items())/max(norm_a*norm_b,1e-12)
        if similarity<0.12:continue
        overlap=sorted(set(document_tokens[target_idx])&set(document_tokens[i]),key=lambda term:a.get(term,0)*b.get(term,0),reverse=True)
        pairs.append({"id":x["id"],"title":x["title"],"severity":x["severity"],"status":x["status"],"similarity":round(similarity*100,1),"shared_terms":overlap[:4],"same_feature":x["feature"]==target["feature"]})
    return sorted(pairs,key=lambda x:x["similarity"],reverse=True)[:limit]


def release_report(db,days=14,platform="All"):
    summary=overview(db,days,platform)
    k=summary["kpis"]
    high=issues(db, severity="Critical",limit=10)+issues(db,severity="Blocker",limit=10)
    high=[r for r in high if r["status"]!="Resolved" and (platform=="All" or r["platform"]==platform)]
    lines=["# MATCHPULSE — QUALITY RELEASE BRIEF", "","> Fictional title, synthetic QA data. Independent portfolio project; not affiliated with Electronic Arts.","",
           "**Build:** 27.4.18  |  **Demo reference date:** April 28, 2027",f"**Scope:** Last {days} days, {platform} | **Sessions:** {k['sessions']:,}","",
           "## Executive snapshot", "",f"- Crash rate: **{k['crash_rate']}%** across {k['sessions']:,} sessions",
           f"- Stability index (synthetic): **{k['stability']}/100**",f"- Latest simulated test pass rate: **{k['test_pass_rate']}%**",f"- High-priority open issues: **{k['open_high_priority']}**", "",
           "## Priority risk signals", ""]
    for x in summary["signals"]:
        lines.append(f"- **{x['level']}: {x['title']}** — {x['detail']} ({x['evidence']})")
    lines.extend(["","## High-priority defect backlog",""])
    for x in sorted(high,key=lambda t:(0 if t["severity"]=="Blocker" else 1,t["id"]))[:8]:
        lines.append(f"- **MP-{x['id']:04d}** [{x['severity']}] {x['title']} — {x['platform']}, {x['status']}")
    lines.extend(["", "## Recommended next actions", "", "1. Triage high-priority open defects with QE and engineering partners.",
                  "2. Re-run Online Reliability and Gameplay Smoke simulations on the impacted platform.",
                  "3. Review repeat defect clusters using IDF-weighted text similarity as candidate duplicates; confirm manually.",
                  "4. Validate risk signals against real instrumentation before making any release decision.","",
                  "---", "Report generated from simulated data for portfolio demonstration. No game-client testing or actual production release decision."])
    return "\n".join(lines)+"\n"


def export_issues_csv(db):
    output=io.StringIO()
    fields=["id","title","feature","platform","severity","status","owner","created_at","occurrences"]
    writer=csv.DictWriter(output,fieldnames=fields)
    writer.writeheader()
    for item in issues(db,limit=500): writer.writerow({key:item[key] for key in fields})
    return output.getvalue()
