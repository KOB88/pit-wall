// Fetches current F1 Fantasy prices and writes prices.json for the app to read (same-origin).
// Runs inside GitHub Actions (server-side, no CORS wall). Configure the feed via repo settings:
//   Variable  FEED_URL     — the prices endpoint (from DevTools on the fantasy site)
//   Secret    FEED_AUTH    — optional "Bearer <token>" if the feed needs auth
//   Secret    FEED_COOKIE  — optional session cookie if the feed needs login
// Without FEED_URL it no-ops (so scheduled runs don't fail before it's configured).
import { writeFileSync } from "node:fs";

const FEED_URL = process.env.FEED_URL;
if (!FEED_URL) {
  console.log("FEED_URL not set — skipping. Add it as a repo variable to enable price updates.");
  process.exit(0);
}

const headers = { "user-agent": "pit-wall-price-bot" };
if (process.env.FEED_AUTH) headers.Authorization = process.env.FEED_AUTH;
if (process.env.FEED_COOKIE) headers.Cookie = process.env.FEED_COOKIE;

const res = await fetch(FEED_URL, { headers });
if (!res.ok) { console.error("Feed fetch failed:", res.status, res.statusText); process.exit(1); }
const data = await res.json();

// ---- PARSE ----  adjust these field names to the real feed once its shape is known.
// Defaults cover the common F1-Fantasy shapes: an array of players, or {Data:{Value:[...]}}.
const rows = Array.isArray(data) ? data : (data.players || data.Data?.Value || data.Value || []);
const drivers = {}, constructors = {};
for (const p of rows) {
  const name = p.DisplayName || p.display_name || p.FullName || p.WebName || p.PlayerName || p.name;
  const price = Number(p.Value ?? p.Price ?? p.price ?? p.cost);
  const isConstructor = p.Skill === 2 || /constructor|team/i.test(String(p.PositionName || p.position || ""));
  if (!name || !Number.isFinite(price)) continue;
  (isConstructor ? constructors : drivers)[name] = price;
}

if (!Object.keys(drivers).length && !Object.keys(constructors).length) {
  console.error("Parsed 0 prices — the feed shape differs from the defaults; adjust the PARSE block.");
  process.exit(1);
}

const out = { updated: new Date().toISOString(), source: FEED_URL, drivers, constructors };
writeFileSync("prices.json", JSON.stringify(out, null, 2) + "\n");
console.log(`Wrote prices.json: ${Object.keys(drivers).length} drivers, ${Object.keys(constructors).length} constructors.`);
