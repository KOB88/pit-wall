#!/usr/bin/env python3
"""Export static FastF1 telemetry for the Pit Wall deployed site (no running server needed).

Pulls from a running FastF1 server (default http://localhost:8000 — the F1 project's server.py),
and for each completed race in the requested years writes:
  telemetry/<year>/<round>.json   — drivers[] fastest-lap traces (speed/throttle/brake/gear + x/y) + track outline
  telemetry/index.json            — the list of available sessions the frontend picks from

Usage:  python scripts/export-static.py 2025 2026    (defaults to current + previous year)
The animated all-cars replay map is NOT exported (too large for static hosting); it stays a
live-server feature. The fastest-lap x/y here still drives a static racing-line track map.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = os.environ.get("FF1_URL", "http://localhost:8000").rstrip("/")
OUT = "telemetry"
STEP = 3  # keep every 3rd telemetry sample (~230 pts/lap) to keep files small


def get(path, tries=90):
    for _ in range(tries):
        req = urllib.request.Request(BASE + path, headers={"Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status == 202:
                    time.sleep(1.5); continue
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip; data = gzip.decompress(data)
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code in (404, 500):
                return None  # no data for this driver/session
            raise
    raise RuntimeError(f"timed out loading {path}")


def ds(arr):
    return arr[::STEP] if arr else arr


def export_session(year, rnd, name):
    # wait for load
    for _ in range(120):
        st = get(f"/api/session/{year}/{rnd}/R/status")
        if st.get("status") == "ready":
            break
        if st.get("status") == "error":
            print(f"  {year} R{rnd}: load error — skip"); return None
        time.sleep(1.5)
    summ = get(f"/api/session/{year}/{rnd}/R/summary")
    if not summ or not summ.get("drivers"):
        print(f"  {year} R{rnd}: no drivers — skip"); return None
    drivers = []
    for d in summ["drivers"]:
        t = get(f"/api/session/{year}/{rnd}/R/telemetry/{d['abbr']}")
        if not t or not t.get("speed"):
            continue
        drivers.append({
            "code": d["abbr"], "name": d.get("lastName") or d["abbr"], "team": d.get("team"),
            "colour": (d.get("teamColor") or "").lstrip("#") or "888", "lap_time": t.get("lapTime"),
            "dist": ds(t["dist"]), "speed": ds(t["speed"]), "throttle": ds(t["throttle"]),
            "brake": [b * 100 for b in ds(t["brake"])], "gear": ds(t["gear"]),
            "x": ds(t["x"]), "y": ds(t["y"]),
        })
    if not drivers:
        print(f"  {year} R{rnd}: no telemetry — skip"); return None
    trk = get(f"/api/session/{year}/{rnd}/R/track") or {}
    drivers.sort(key=lambda d: d["lap_time"] if d["lap_time"] is not None else 9e9)
    out = {
        "session": f"{year} · {name}", "year": year, "round": rnd,
        "track": {"x": ds(trk.get("x", [])), "y": ds(trk.get("y", [])), "rotation": trk.get("rotation", 0)},
        "drivers": drivers,
    }
    os.makedirs(f"{OUT}/{year}", exist_ok=True)
    with open(f"{OUT}/{year}/{rnd}.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"  {year} R{rnd} {name}: {len(drivers)} drivers")
    return {"year": year, "round": rnd, "name": name, "drivers": len(drivers)}


def main():
    now = datetime.now(timezone.utc).year
    years = [int(a) for a in sys.argv[1:]] or [now, now - 1]
    index = []
    for year in years:
        sch = get(f"/api/schedule/{year}")
        today = datetime.now(timezone.utc).isoformat()
        for ev in sch["events"]:
            race = next((s for s in ev["sessions"] if s["abbr"] == "R" and s["completed"]), None)
            if not race:
                continue
            try:
                got = export_session(year, ev["round"], ev["name"])
                if got:
                    index.append(got)
            except Exception as e:
                print(f"  {year} R{ev['round']}: ERROR {e} — skip")
    index.sort(key=lambda e: (e["year"], e["round"]), reverse=True)
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/index.json", "w") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "sessions": index}, f, indent=0)
    print(f"Wrote {OUT}/index.json: {len(index)} sessions")


if __name__ == "__main__":
    main()
