# WordDunk! — hoops typing game (multiplayer, classroom)

An original, no-copyright typing game: students type sight words and each correct
word sends a ball through the hoop. Rooms, join codes, and live leaderboards run
in-memory on a tiny Python stdlib server (no dependencies).

## How to run

    cd worddunk
    python3 server.py          # listens on 0.0.0.0:8000 (override with PORT=9999)

Then:
- Teacher opens the host dashboard at  http://HOST:8000/host
- Students open the game at         http://HOST:8000
  and enter the 4-letter JOIN CODE + their name.
- Teacher watches names appear live in the roster, presses **Start round**,
  sees scores stream in, and starts the next round when the timer hits 0.

**Want it on a free public host (students can reach it from any device)?**
See DEPLOY.md — two ready-made paths: Render (needs a GitHub account) or
PythonAnywhere (no GitHub; direct file upload; WSGI entry included).

## Game modes (pick when creating the room)

- **Normal words** — type the word shown.
- **Backward words** — word is displayed reversed; students must read it and
  type it forward to score. Progress dots show how much of the word is typed.
- **Speed timer** — every word has a countdown bar (scaled to word length);
  if the bar empties the word counts as a miss and auto-skips.

## Word lists

Grades 1–8, 50 words each — the same Florida B.E.S.T.-aligned sight-word lists
used in Sight_Words_Checklist_Grades_1-8_Florida_BEST.pdf. The host picks the
grade when creating the room; every player gets a shuffled copy per round and
the list cycles if they finish before time runs out.

## Teacher reports

- **Round results** — each finished round is saved (up to 40) and shown in
  expandable blocks: rank, player, score, words, misses, accuracy.
- **Class accuracy report** — every student aggregated across all rounds
  (rounds played, total words/misses, weighted accuracy, total score).
- **CSV download** — one spreadsheet-ready file (Excel/Sheets compatible) with
  per-round results plus a class summary.

## API (all JSON)

    POST /api/create                 {grade:1-8, duration:15-300, mode:normal|backwards|speed, host?} -> {code}
    POST /api/room/{code}/join       {name}      -> {pid, grade, duration, mode}
    POST /api/room/{code}/leave      {pid}
    POST /api/room/{code}/kick       {pid}       (host dashboard)
    POST /api/room/{code}/start                  -> room status (resets scores)
    POST /api/room/{code}/end                    -> finalizes round into history
    POST /api/room/{code}/beat       {pid, score, words, misses}
    GET  /api/status/{code}                      -> round + sorted leaderboard
    GET  /api/room/{code}/words?pid=             -> shuffled 50-word queue
    GET  /api/history/{code}                     -> finished rounds (results + mode)
    GET  /api/export/{code}.csv                  -> downloadable CSV (all rounds + summary)
    GET  /api/now                                -> server clock (sync)

Rooms and history live in memory only — restarting the server clears them, so
the teacher creates a fresh room (new code) after each restart.

## Files

    server.py            HTTP server + rooms + word lists + history/CSV (stdlib only)
    static/play.html     student page (join -> lobby -> game -> leaderboard)
    static/play.js       game loop, typing engine, modes, canvas hoop, WebAudio sfx
    static/host.html     teacher dashboard (create room, live roster, reports)
    static/host.js       dashboard logic (live + history + class report)
    static/common.js     shared helpers
    static/style.css     shared styles

All art and audio are generated in code (canvas + WebAudio) — nothing copied
from any existing game.
