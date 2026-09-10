# Deploying WordDunk to a free host

WordDunk is plain Python 3 (stdlib only — no pip installs needed) plus static
HTML/JS/CSS. It can be hosted for free in two easy ways. Pick one:

| | Option A: Render | Option B: PythonAnywhere |
|---|---|---|
| Needs GitHub? | Yes (free account + one public repo) | No — upload files directly |
| Runs the code as | `python3 server.py` (exact same code) | WSGI app (`wsgi_app.py`, included) |
| Sleeps when idle? | Free tier: after ~15 min with no visits | No |
| HTTPS | Yes (automatic) | Yes (automatic) |

**Before you start, know this:** rooms and results live in the app's memory.
Free hosts may restart the app (Render's free tier sleeps when idle, and any
host reboots its containers occasionally). When that happens rooms simply
disappear — the teacher just opens the dashboard and creates a fresh room
(new join code) for the next class. Finished-round CSVs should be downloaded
at the end of the session if you need the data later.

---

## Option A — Render (recommended if you can use GitHub)

1. **Put the code on GitHub**
   - Create a free account at github.com, then create a **new repository**
     (Public is fine).
   - Upload the contents of the `worddunk/` folder into the repo root —
     easiest way without git on your computer: GitHub web UI → **Add file →
     Upload files** → drag in the 9 files:
     `server.py`, `wsgi_app.py`, `Procfile` and the `static/` folder
     (inside it: `play.html`, `play.js`, `host.html`, `host.js`,
     `common.js`, `style.css`).
   - (Do NOT upload `server.py.bak`.)

2. **Create the web service on Render**
   - Create a free account at render.com → **New → Web Service**.
   - Connect GitHub and pick your repo.
   - Render auto-detects; set:
     - **Name**: `worddunk`
     - **Region**: nearest to you
     - **Runtime**: `Python 3`
     - **Build command**: *(leave empty)*
     - **Start command**: `python3 server.py`
     - **Instance type**: Free
   - Click **Create Web Service**. In ~2 minutes it deploys and gives you a
     URL like `https://worddunk.onrender.com`.

3. **Use it**
   - Teacher dashboard: `https://worddunk.onrender.com/host`
   - Students: `https://worddunk.onrender.com` (enter the join code + name)

> Free-tier note: Render puts the app to sleep after ~15 minutes with no
> visits. The teacher should open the dashboard first thing; the first load
> can take ~30–60s to wake. Keep the dashboard open on a classroom computer
> during play — polling from players keeps it awake too.

---

## Option B — PythonAnywhere (no GitHub needed)

1. Create a free account at pythonanywhere.com (username becomes part of the
   URL: `https://YOURUSERNAME.pythonanywhere.com`).

2. **Upload the code**
   - Web → **Files** tab → navigate to `/home/YOURUSERNAME/`.
   - Create folder `worddunk`, open it, and upload these files (Upload button
     supports one at a time; alternatively zip them on your computer and use
     the Bash console below to unzip):
     - `server.py`, `wsgi_app.py`
     - folder `static/` → upload the 6 files inside (`play.html`, `play.js`,
       `host.html`, `host.js`, `common.js`, `style.css`)

3. **Create the web app**
   - Web tab → **Add a new web app** → Next → choose **Manual configuration**
     → **Python 3.12** → Next.
   - In the web app panel set:
     - **Code**: Working directory → `/home/YOURUSERNAME/worddunk`
     - **Code**: WSGI configuration file → click it, replace its contents with
       just one line:
       `from wsgi_app import application`  (the file path will show
       `/home/YOURUSERNAME/worddunk/wsgi_app.py` is where `wsgi_app` lives)
       — safest: copy the full sample WSGI file content but change the import
       line to `from wsgi_app import application` and delete the rest, or use
       the simpler one-liner file.
     - Click **Reload** (green button top right).

4. **Use it**
   - Teacher dashboard: `https://YOURUSERNAME.pythonanywhere.com/host`
   - Students: `https://YOURUSERNAME.pythonanywhere.com`

> Free-tier note: your account must be logged into at least every ~3 months
> or it is disabled (PythonAnywhere emails you). Web app stays on 24/7.

---

## Quick sanity checklist after deploying

1. Open `/host` — page loads with the "Start a game" card.
2. Create a room — a 4-letter code appears.
3. Open the site in a second tab, join with the code + a name — the name
   appears on the dashboard roster within a second.
4. Start a round on the dashboard — the player screen counts down 3-2-1 and
   shows a word to type.
5. Type a word on the player tab → ball swishes, score appears on the
   dashboard.
6. Let the timer end → "Round results" appears on the dashboard; test
   **Download all results (CSV)**.

If step 3–5 fail, the most common cause is **two app processes sharing the
visits** (multi-worker hosting). PythonAnywhere and Render's single
`python3 server.py` setup above run one process, which is what WordDunk needs
(rooms are in-memory). If you switch to a host that load-balances across
multiple processes, rooms would be inconsistent — don't scale this app out.

## Files to deploy (9)

```
server.py          (entry point for Render / standalone)
wsgi_app.py        (entry point for PythonAnywhere / WSGI hosts)
Procfile           (Render: web: python3 server.py)
static/play.html   static/play.js
static/host.html   static/host.js
static/common.js   static/style.css
```
