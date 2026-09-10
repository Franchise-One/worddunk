#!/usr/bin/env python3
"""
WordDunk! — a hoops typing game (original code & art)
Host dashboard: /host   Players: /
Rooms are in-memory; join codes are 4 chars. Stdlib only.

Modes: normal | backwards | speed
Round history + CSV export for gradebooks.

Deployable anywhere Python runs. Two interfaces:
  * standalone HTTP server (python3 server.py)  -> PORT env or 8000
  * WSGI application (wsgi_app)                 -> free hosts like PythonAnywhere
Request handling lives in handle_request() so both interfaces share it.
"""
import csv, io, json, os, random, re, string, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer
from socketserver import ThreadingMixIn

PORT = int(os.environ.get("PORT", "8000"))
BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")

# ----------------------------------------------------------------------
# Word lists — same 50-per-grade B.E.S.T.-aligned lists as the PDFs
# ----------------------------------------------------------------------
WORDLISTS = {
    1: ["after","again","am","an","any","as","ask","be","because","before","by",
        "came","could","down","every","first","fly","from","give","going","had",
        "has","her","him","his","how","just","know","let","live","may","old",
        "once","open","over","put","right","round","some","stop","take","thank",
        "them","then","think","walk","were","when","would","your"],
    2: ["also","always","another","around","been","best","both","buy","call",
        "cold","does","eat","fast","found","gave","goes","great","green","help",
        "home","its","line","made","many","means","much","off","pull","read",
        "say","sing","sit","sleep","tell","their","these","those","through",
        "turned","under","upon","us","use","very","wash","which","why","wish",
        "work","write"],
    3: ["about","across","almost","among","answer","begin","behind","better",
        "bring","carry","certain","children","clean","cut","done","draw",
        "drink","eight","enough","fall","far","full","got","grow","hold","hot",
        "hurt","if","keep","kind","laugh","light","long","myself","never",
        "only","own","pick","seven","shall","show","six","small","start","ten",
        "today","together","try","warm","whole"],
    4: ["achieve","advantage","affect","attempt","cause","century","challenge",
        "character","consider","courage","curious","distance","effort",
        "imagine","increase","instead","measure","observe","pattern",
        "possible","process","result","specific","support","system","accurate",
        "area","average","behavior","energy","equal","experience","figure",
        "force","improve","include","material","motion","natural","notice",
        "object","opinion","prepare","protect","region","require","separate",
        "solution","surface","temperature"],
    5: ["accomplish","although","analyze","ancient","appropriate","attitude",
        "compare","conclusion","consequence","contrast","describe",
        "determine","develop","effect","evidence","explain","government",
        "identify","infer","muscle","necessary","purpose","recognize",
        "summarize","technology","adapt","anticipate","aspect","assumption",
        "atmosphere","capable","category","climate","combine","communicate",
        "component","construct","contribute","data","debate","decade",
        "demonstrate","device","dimension","distinct","distribute",
        "eliminate","encounter","establish","estimate"],
    6: ["alternative","argument","authentic","bias","characteristic",
        "circumstance","cite","claim","clarify","community","conflict",
        "criteria","crucial","evaluate","explicit","genre","justify",
        "logical","perspective","protagonist","relevant","resource","theme",
        "valid","verify","accumulate","adjacent","adjust","assume","aware",
        "benefit","concept","consist","convey","diverse","document","dynamic",
        "evident","feature","focus","illustrate","impact","imply","indicate",
        "individual","interpret","involve","maintain","method","modify"],
    7: ["advocate","appeal","assertion","audience","coherent","credible",
        "counterclaim","deduce","deliberate","discipline","emphasize",
        "environment","especially","ethical","fallacy","foreign",
        "guarantee","hierarchy","incorporate","legitimate","notion",
        "rebuttal","significant","sufficient","tone","acquire","apparent",
        "capacity","competent","comprehensive","confirm","consensus",
        "consistent","constitute","controversy","coordinate","diminish",
        "enhance","ensure","equitable","facilitate","fluctuate",
        "hypothesis","integrate","plausible","qualify","recommend","refute",
        "reluctant","synthesize"],
    8: ["abstract","acknowledge","ambiguous","arbitrary","assert","assess",
        "authoritative","beneficial","chronological","compel","concise",
        "concrete","connotation","context","correlate","cultivate",
        "denotation","designate","discern","elaborate","endorse","excerpt",
        "feasible","formulate","fundamental","implicit","incentive",
        "inference","innovation","integrity","intervene","irony",
        "meticulous","nuance","objective","paradox","paraphrase","portray",
        "precedent","precise","profound","propaganda","provoke","rationale",
        "resilient","scrutiny","skeptical","subtle","unanimous","vulnerable"],
}

for _g, _wl in WORDLISTS.items():
    assert len(_wl) == 50, f"grade {_g} has {len(_wl)} words"
    assert len(set(_wl)) == 50, f"grade {_g} has duplicates"

MODES = ("normal", "backwards", "speed")

# ----------------------------------------------------------------------
# Room model
# ----------------------------------------------------------------------
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O/1/I
LOCK = threading.RLock()
ROOMS = {}
MAX_ROOMS = 400
HISTORY_CAP = 40


def new_code():
    while True:
        code = "".join(random.choices(CODE_CHARS, k=4))
        if code not in ROOMS:
            return code


def new_pid():
    return "".join(random.choices(string.hexdigits.upper(), k=8))


class Player:
    def __init__(self, pid, name):
        self.pid = pid
        self.name = name
        self.joined = time.time()
        self.last = time.time()
        self.score = 0
        self.words = 0
        self.misses = 0
        self.playing = False
        self.round_stats = {}

    def snap(self):
        acc = round(self.words / (self.words + self.misses) * 100) if (self.words + self.misses) else None
        return {"pid": self.pid, "name": self.name, "joined": self.joined,
                "score": self.score, "words": self.words, "misses": self.misses,
                "acc": acc, "playing": self.playing}


class Room:
    def __init__(self, grade, host, duration, mode):
        self.code = new_code()
        self.grade = grade
        self.host = host or "Teacher"
        self.duration = duration
        self.mode = mode
        self.created = time.time()
        self.last = time.time()
        self.players = {}
        self.round = None
        self.wordq = {}
        self.history = []

    def status(self):
        with LOCK:
            players = sorted((p.snap() for p in self.players.values()),
                             key=lambda p: (-p["score"], -p["words"], p["joined"]))
            r = None
            if self.round:
                r = {"active": time.time() < self.round["end"],
                     "start": self.round["start"], "end": self.round["end"],
                     "n": self.round["n"]}
            return {"ok": True, "code": self.code, "grade": self.grade,
                    "host": self.host, "duration": self.duration,
                    "mode": self.mode, "created": self.created, "now": time.time(),
                    "round": r, "players": players}


# ----------------------------------------------------------------------
# Round lifecycle
# ----------------------------------------------------------------------
def finalize_round(room):
    r = room.round
    if not r:
        return
    n = r["n"]
    if any(h["n"] == n for h in room.history):
        return
    entries = []
    for p in room.players.values():
        d = p.round_stats.get(n)
        if not d or (d["words"] + d["misses"]) == 0:
            continue
        acc = round(d["words"] / (d["words"] + d["misses"]) * 100, 1)
        entries.append({"pid": p.pid, "name": p.name, "score": d["score"],
                        "words": d["words"], "misses": d["misses"], "acc": acc})
    entries.sort(key=lambda e: (-e["score"], -e["words"], e["name"]))
    room.history.append({"n": n, "mode": room.mode, "duration": room.duration,
                         "start": r["start"], "end": r["end"], "entries": entries})
    if len(room.history) > HISTORY_CAP:
        room.history = room.history[-HISTORY_CAP:]


def start_round(room):
    with LOCK:
        now = time.time()
        finalize_round(room)
        n = (room.round["n"] + 1) if room.round else 1
        room.round = {"start": now, "end": now + room.duration, "n": n}
        room.wordq.clear()
        for p in room.players.values():
            p.score = 0; p.words = 0; p.misses = 0; p.playing = False
            p.round_stats = {}
        return room.status()


def end_round(room):
    with LOCK:
        if room.round and room.round["end"] > time.time():
            room.round["end"] = time.time()
        finalize_round(room)
        return room.status()


def words_for(room, pid):
    with LOCK:
        if not room.round or pid not in room.players:
            return None
        key = (pid, room.round["n"])
        if key not in room.wordq:
            room.wordq[key] = random.sample(WORDLISTS[room.grade], 50)
        return {"words": room.wordq[key], "round": room.round["n"],
                "mode": room.mode, "duration": room.duration}


def beat(room, pid, payload):
    with LOCK:
        p = room.players.get(pid)
        if not p:
            return {"ok": False, "error": "not joined"}
        if room.round and time.time() < room.round["end"]:
            p.last = time.time()
            p.playing = True
            p.score = max(p.score, int(payload.get("score", 0)))
            p.words = max(p.words, int(payload.get("words", 0)))
            p.misses = max(p.misses, int(payload.get("misses", 0)))
            d = p.round_stats.setdefault(room.round["n"],
                                         {"score": 0, "words": 0, "misses": 0})
            d["score"] = max(d["score"], p.score)
            d["words"] = max(d["words"], p.words)
            d["misses"] = max(d["misses"], p.misses)
        return {"ok": True}


def export_csv(room):
    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out)
    w.writerow(["WordDunk results", "room", room.code, "grade", room.grade,
                "mode", room.mode, "host", room.host])
    if not room.history:
        w.writerow(["No rounds finished yet"])
    for h in room.history:
        w.writerow([])
        w.writerow(["Round", h["n"], "Mode", h["mode"], "Seconds", h["duration"],
                    "Started", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(h["start"]))])
        w.writerow(["Rank", "Player", "Score", "Words", "Misses", "Accuracy %"])
        for i, e in enumerate(h["entries"], start=1):
            w.writerow([i, e["name"], e["score"], e["words"], e["misses"], e["acc"]])
    w.writerow([])
    w.writerow(["Class summary"])
    agg = {}
    for h in room.history:
        for e in h["entries"]:
            a = agg.setdefault(e["name"], {"rounds": 0, "words": 0, "misses": 0, "score": 0})
            a["rounds"] += 1
            a["words"] += e["words"]
            a["misses"] += e["misses"]
            a["score"] += e["score"]

    def _acc(a):
        denom = a["words"] + a["misses"]
        return round(a["words"] / denom * 100, 1) if denom else 0.0

    w.writerow(["Player", "Rounds", "Words", "Misses", "Accuracy %"])
    for name, a in sorted(agg.items(), key=lambda kv: (-_acc(kv[1]), kv[0])):
        w.writerow([name, a["rounds"], a["words"], a["misses"], _acc(a)])
    return out.getvalue().encode("utf-8")


def purge_loop():
    while True:
        time.sleep(90)
        now = time.time()
        with LOCK:
            dead = [c for c, r in ROOMS.items()
                    if (len(r.players) == 0 and now - r.created > 30 * 60)
                    or now - r.last > 3 * 3600]
            for c in dead:
                del ROOMS[c]


def get_room(code):
    with LOCK:
        r = ROOMS.get(code)
        if r:
            r.last = time.time()
        return r


# ----------------------------------------------------------------------
# Shared request handler (pure) — used by both the HTTP server and WSGI
# ----------------------------------------------------------------------
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
        ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json",
        ".csv": "text/csv; charset=utf-8"}


def _json_bytes(obj, status=200):
    body = json.dumps(obj).encode("utf-8")
    return (status, [("Content-Type", "application/json; charset=utf-8"),
                     ("Cache-Control", "no-store")], body)


def _static_file(path):
    rel = path.lstrip("/")
    if rel in ("", "index.html"):
        rel = "static/play.html"
    elif rel == "host":
        rel = "static/host.html"
    elif rel.startswith("static/"):
        pass
    else:
        return _json_bytes({"ok": False, "error": "not found"}, 404)
    full = os.path.normpath(os.path.join(BASE, rel))
    if not full.startswith(BASE) or not os.path.isfile(full):
        return _json_bytes({"ok": False, "error": "not found"}, 404)
    ext = os.path.splitext(full)[1]
    with open(full, "rb") as f:
        data = f.read()
    return (200, [("Content-Type", MIME.get(ext, "application/octet-stream")),
                  ("Cache-Control", "no-store")], data)


def handle_request(method, target, body=b""):
    """Return (status:int, headers:[(k,v)], body:bytes)."""
    u = urlparse(target)
    parts = [s for s in u.path.split("/") if s]
    base_headers = [("Access-Control-Allow-Origin", "*")]
    if method == "OPTIONS":
        return (204, [("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
                      ("Access-Control-Allow-Headers", "Content-Type"),
                      ("Content-Length", "0")], b"")
    if not parts or parts[0] != "api":
        if method != "GET":
            return _json_bytes({"ok": False, "error": "not found"}, 404)
        return _static_file(u.path)
    # ---------------- POST ----------------
    if method == "POST":
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            return _json_bytes({"ok": False, "error": "bad body"}, 400)
        if len(parts) == 2 and parts[1] == "create":
            grade = int(payload.get("grade", 5) or 5)
            duration = int(payload.get("duration", 60) or 60)
            mode = str(payload.get("mode", "normal") or "normal")
            host = str(payload.get("host", "")).strip()[:24]
            if grade not in WORDLISTS:
                return _json_bytes({"ok": False, "error": "grade must be 1-8"}, 400)
            if mode not in MODES:
                return _json_bytes({"ok": False, "error": "mode must be normal/backwards/speed"}, 400)
            if not (15 <= duration <= 300):
                return _json_bytes({"ok": False, "error": "duration 15-300s"}, 400)
            with LOCK:
                if len(ROOMS) >= MAX_ROOMS:
                    return _json_bytes({"ok": False, "error": "too many rooms"}, 503)
                room = Room(grade, host, duration, mode)
                ROOMS[room.code] = room
            return _json_bytes({"ok": True, "code": room.code, "status": room.status()})
        if len(parts) == 4 and parts[1] == "room":
            code, act = parts[2], parts[3]
            room = get_room(code)
            if not room:
                return _json_bytes({"ok": False, "error": "room not found"}, 404)
            if act == "join":
                name = re.sub(r"<[^>]*>", "", str(payload.get("name", "")).strip())
                name = re.sub(r"\s+", " ", name).strip()[:24] or "Player"
                with LOCK:
                    pid = new_pid()
                    room.players[pid] = Player(pid, name)
                    room.last = time.time()
                return _json_bytes({"ok": True, "pid": pid, "name": name, "code": code,
                                    "grade": room.grade, "duration": room.duration,
                                    "mode": room.mode})
            if act in ("leave", "kick"):
                with LOCK:
                    room.players.pop(str(payload.get("pid", "")), None)
                return _json_bytes({"ok": True})
            if act == "start":
                return _json_bytes(start_round(room))
            if act == "end":
                return _json_bytes(end_round(room))
            if act == "beat":
                pid = str(payload.get("pid", ""))
                if not pid or pid not in room.players:
                    return _json_bytes({"ok": False, "error": "not joined"}, 400)
                return _json_bytes(beat(room, pid, payload))
            return _json_bytes({"ok": False, "error": "unknown action"}, 404)
        return _json_bytes({"ok": False, "error": "not found"}, 404)
    # ---------------- GET ----------------
    if method == "GET":
        if len(parts) >= 2 and parts[1] == "now":
            return _json_bytes({"ok": True, "now": time.time()})
        if len(parts) >= 3 and parts[1] == "status":
            room = get_room(parts[2])
            if not room:
                return _json_bytes({"ok": False, "error": "room not found"}, 404)
            return _json_bytes(room.status())
        if len(parts) >= 3 and parts[1] == "history":
            room = get_room(parts[2])
            if not room:
                return _json_bytes({"ok": False, "error": "room not found"}, 404)
            return _json_bytes({"ok": True, "code": room.code, "rounds": room.history})
        if len(parts) >= 3 and parts[1] == "export":
            code = parts[2].split(".")[0]
            room = get_room(code)
            if not room:
                return _json_bytes({"ok": False, "error": "room not found"}, 404)
            data = export_csv(room)
            headers = [("Content-Type", MIME[".csv"]), ("Content-Length", str(len(data))),
                       ("Content-Disposition",
                        f'attachment; filename="worddunk_{room.code}_results.csv"')]
            return (200, headers, data)
        if len(parts) == 4 and parts[1] == "room" and parts[3] == "words":
            room = get_room(parts[2])
            if not room:
                return _json_bytes({"ok": False, "error": "room not found"}, 404)
            q = parse_qs(u.query)
            pid = (q.get("pid") or [""])[0]
            out = words_for(room, pid)
            if out is None:
                return _json_bytes({"ok": False, "error": "not in room or no active round"})
            return _json_bytes(out)
    return _json_bytes({"ok": False, "error": "not found"}, 404)


# ----------------------------------------------------------------------
# Interface 1 — standalone HTTP server (single process, keeps rooms)
# ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "WordDunk/1.0"

    def log_message(self, *a):
        pass

    def _run(self, method):
        n = 0
        if method == "POST":
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = 0
            if n > 131072:
                return self._respond(400, b'{"ok":false,"error":"too large"}',
                                     "application/json; charset=utf-8")
            body = self.rfile.read(n)
        else:
            body = b""
        status, headers, data = handle_request(method, self.path, body)
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_GET(self):
        self._run("GET")

    def do_POST(self):
        self._run("POST")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()


# ----------------------------------------------------------------------
# Interface 2 — WSGI (for free hosts such as PythonAnywhere)
# ----------------------------------------------------------------------
def wsgi_app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    qs = environ.get("QUERY_STRING", "")
    target = path + ("?" + qs if qs else "")
    body = b""
    if method == "POST":
        try:
            n = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            n = 0
        if n > 131072:
            status, headers, data = 400, [], b'{"ok":false,"error":"too large"}'
            headers.append(("Content-Type", "application/json; charset=utf-8"))
        else:
            body = environ["wsgi.input"].read(n) if n else b""
            status, headers, data = handle_request(method, target, body)
    else:
        status, headers, data = handle_request(method, target, body)
    start_response(f"{status} {'OK' if status < 400 else 'Error'}",
                   [(k, v) for k, v in headers if k.lower() != "content-length"] +
                   [("Content-Length", str(len(data)))])
    return [data]


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


# ----------------------------------------------------------------------
def main():
    threading.Thread(target=purge_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    print(f"[WordDunk] listening on 0.0.0.0:{PORT}  (host dashboard at /host)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
