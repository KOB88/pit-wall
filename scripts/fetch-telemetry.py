#!/usr/bin/env python3
"""Export fastest-lap telemetry for the latest completed race into telemetry/latest.json,
which the Pit Wall app reads same-origin. Powered by FastF1 (runs server-side; can't run
in a browser). Run locally (`python scripts/fetch-telemetry.py`) or via the GitHub Action.
"""
import json, os, sys
from datetime import datetime, timezone

import fastf1  # pip install fastf1

os.makedirs("telemetry", exist_ok=True)
os.makedirs(".fastf1cache", exist_ok=True)
fastf1.Cache.enable_cache(".fastf1cache")

YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(timezone.utc).year

# pick the most recent race whose session has already happened
sched = fastf1.get_event_schedule(YEAR, include_testing=False)
now = datetime.now(timezone.utc).replace(tzinfo=None)
done = sched[sched["Session5DateUtc"] < now]
if done.empty:
    print("No completed race this season yet — nothing to export.")
    sys.exit(0)
event = done.iloc[-1]

session = fastf1.get_session(YEAR, int(event["RoundNumber"]), "R")
session.load(telemetry=True, laps=True, weather=False, messages=False)


def downsample(series, n=320):
    vals = list(series)
    if len(vals) <= n:
        return [round(float(v), 1) for v in vals]
    step = len(vals) / n
    return [round(float(vals[int(i * step)]), 1) for i in range(n)]


drivers = []
for drv in session.drivers:
    laps = session.laps.pick_drivers(drv)
    if laps.empty:
        continue
    fl = laps.pick_fastest()
    if fl is None or fl.empty:
        continue
    try:
        tel = fl.get_car_data().add_distance()
        pos = fl.get_pos_data()
    except Exception as e:
        print(f"  skip {drv}: {e}")
        continue
    info = session.get_driver(drv)
    lt = fl["LapTime"]
    drivers.append({
        "code": info["Abbreviation"],
        "name": info["LastName"],
        "team": info["TeamName"],
        "colour": str(info["TeamColor"]).lstrip("#"),
        "lap_time": lt.total_seconds() if lt is not None and not fastf1.utils.pd.isnull(lt) else None,
        "dist": downsample(tel["Distance"]),
        "speed": downsample(tel["Speed"]),
        "throttle": downsample(tel["Throttle"]),
        "brake": downsample(tel["Brake"].astype(float) * 100),
        "gear": downsample(tel["nGear"]),
        "x": downsample(pos["X"]) if "X" in pos else [],
        "y": downsample(pos["Y"]) if "Y" in pos else [],
    })

drivers.sort(key=lambda d: d["lap_time"] if d["lap_time"] is not None else 9e9)
out = {
    "session": f"{event['EventName']} — Race",
    "updated": datetime.now(timezone.utc).isoformat(),
    "drivers": drivers,
}
with open("telemetry/latest.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))
print(f"Wrote telemetry/latest.json: {len(drivers)} drivers from {event['EventName']}.")
