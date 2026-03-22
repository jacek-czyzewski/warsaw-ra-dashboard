#!/usr/bin/env python3
"""
Enrich Warsaw RA dashboard data with artist and venue profiles
fetched from the Resident Advisor GraphQL API.

Usage:
    python enrich.py                  # fetch everything + export JSON
    python enrich.py --venues-only    # venues only
    python enrich.py --artists-only   # artists only
    python enrich.py --export-only    # skip fetching, just re-export JSON
    python enrich.py --batch-size 20 --delay 0.3

Output:
    scripts/ra_enriched.db  — SQLite database (source of truth)
    artists.json            — artist profiles keyed by name (for dashboard)
    venues.json             — venue profiles keyed by venue_id (for dashboard)

NOTE: RA's ToS prohibits automated scraping. Use this script for personal,
non-commercial use only. The script rate-limits requests out of courtesy.
"""

import json
import sqlite3
import time
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────

GRAPHQL_URL  = "https://ra.co/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept":        "application/json",
    "Origin":        "https://ra.co",
    "Referer":       "https://ra.co",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

ROOT         = Path(__file__).parent.parent
DATA_JSON    = ROOT / "data.json"
DB_PATH      = Path(__file__).parent / "ra_enriched.db"
ARTISTS_JSON = ROOT / "artists.json"
VENUES_JSON  = ROOT / "venues.json"

DEFAULT_BATCH = 10
DEFAULT_DELAY = 0.6   # seconds between batch requests

# ── Database schema ───────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS venues (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    address         TEXT,
    capacity        TEXT,
    blurb           TEXT,
    photo           TEXT,
    logo_url        TEXT,
    content_url     TEXT,
    follower_count  INTEGER,
    is_closed       INTEGER DEFAULT 0,
    latitude        REAL,
    longitude       REAL,
    website         TEXT,
    fetched_at      TEXT
);

CREATE TABLE IF NOT EXISTS artists (
    slug            TEXT PRIMARY KEY,
    ra_id           TEXT,
    name            TEXT,
    image           TEXT,
    cover_image     TEXT,
    country         TEXT,
    area            TEXT,
    bio_blurb       TEXT,
    bio_content     TEXT,
    instagram       TEXT,
    soundcloud      TEXT,
    facebook        TEXT,
    website         TEXT,
    follower_count  INTEGER,
    content_url     TEXT,
    not_found       INTEGER DEFAULT 0,
    fetched_at      TEXT
);
"""

# ── GraphQL field fragments ───────────────────────────────────────────────────

VENUE_FIELDS = """
    id name address capacity blurb photo logoUrl contentUrl
    followerCount isClosed website
    location { latitude longitude }
"""

ARTIST_FIELDS = """
    id name urlSafeName image coverImage contentUrl followerCount
    country { name }
    area { name }
    biography { blurb content }
    instagram soundcloud facebook website
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def gql(query: str) -> dict:
    resp = requests.post(GRAPHQL_URL, headers=HEADERS, json={"query": query}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(data["errors"])
    return data["data"]


def to_slug(name: str) -> str:
    """Convert an artist name to an RA URL slug."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def progress(current: int, total: int, label: str = "") -> str:
    pct = current / total * 100 if total else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    return f"  [{bar}] {current}/{total} {label}"

# ── Venue enrichment ──────────────────────────────────────────────────────────

def build_venue_batch_query(ids: list[str]) -> str:
    aliases = "\n".join(
        f'  v{i}: venue(id: "{vid}", ensureLive: false) {{ {VENUE_FIELDS} }}'
        for i, vid in enumerate(ids)
    )
    return f"{{ {aliases} }}"


def enrich_venues(conn: sqlite3.Connection, venue_ids: list[str],
                  batch_size: int, delay: float) -> None:
    cur = conn.cursor()
    existing = {r[0] for r in cur.execute("SELECT id FROM venues")}
    todo = [v for v in venue_ids if v not in existing]
    print(f"\nVenues: {len(existing)} cached, {len(todo)} to fetch")

    fetched = 0
    errors  = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i : i + batch_size]
        print(progress(i, len(todo), f"(errors: {errors})"), end="\r")
        try:
            data = gql(build_venue_batch_query(batch))
        except Exception as e:
            errors += 1
            print(f"\n  Batch error: {e}")
            time.sleep(delay * 4)
            continue

        for j, vid in enumerate(batch):
            v = data.get(f"v{j}")
            if v is None:
                cur.execute(
                    "INSERT OR REPLACE INTO venues (id, fetched_at) VALUES (?, ?)",
                    (vid, now_iso()),
                )
            else:
                loc = v.get("location") or {}
                cur.execute("""
                    INSERT OR REPLACE INTO venues
                        (id, name, address, capacity, blurb, photo, logo_url,
                         content_url, follower_count, is_closed, latitude, longitude,
                         website, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    v["id"], v.get("name"), v.get("address"),
                    v.get("capacity"), v.get("blurb"), v.get("photo"),
                    v.get("logoUrl"), v.get("contentUrl"),
                    v.get("followerCount"), int(bool(v.get("isClosed"))),
                    loc.get("latitude"), loc.get("longitude"),
                    v.get("website"), now_iso(),
                ))
                fetched += 1

        conn.commit()
        time.sleep(delay)

    print(progress(len(todo), len(todo), f"done — {fetched} fetched, {errors} errors"))

# ── Artist enrichment ─────────────────────────────────────────────────────────

def build_artist_batch_query(slugs: list[str]) -> str:
    aliases = "\n".join(
        f'  a{i}: artist(slug: "{slug}") {{ {ARTIST_FIELDS} }}'
        for i, slug in enumerate(slugs)
    )
    return f"{{ {aliases} }}"


def enrich_artists(conn: sqlite3.Connection, artist_names: list[str],
                   batch_size: int, delay: float) -> None:
    cur = conn.cursor()
    existing = {r[0] for r in cur.execute("SELECT slug FROM artists")}

    # Multiple names can map to the same slug — deduplicate
    slug_map: dict[str, list[str]] = {}
    for name in artist_names:
        s = to_slug(name)
        if s and s not in existing:
            slug_map.setdefault(s, []).append(name)

    slugs = list(slug_map.keys())
    print(f"\nArtists: {len(existing)} cached, {len(slugs)} slugs to fetch")

    fetched = 0
    not_found = 0
    errors = 0
    for i in range(0, len(slugs), batch_size):
        batch = slugs[i : i + batch_size]
        print(progress(i, len(slugs), f"(found: {fetched}, not found: {not_found}, errors: {errors})"), end="\r")
        try:
            data = gql(build_artist_batch_query(batch))
        except Exception as e:
            errors += 1
            print(f"\n  Batch error: {e}")
            time.sleep(delay * 4)
            continue

        for j, slug in enumerate(batch):
            a = data.get(f"a{j}")
            if a is None:
                cur.execute(
                    "INSERT OR REPLACE INTO artists (slug, not_found, fetched_at) VALUES (?,1,?)",
                    (slug, now_iso()),
                )
                not_found += 1
            else:
                bio = a.get("biography") or {}
                cur.execute("""
                    INSERT OR REPLACE INTO artists
                        (slug, ra_id, name, image, cover_image, country, area,
                         bio_blurb, bio_content, instagram, soundcloud, facebook,
                         website, follower_count, content_url, not_found, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)
                """, (
                    slug, a.get("id"), a.get("name"),
                    a.get("image"), a.get("coverImage"),
                    (a.get("country") or {}).get("name"),
                    (a.get("area")    or {}).get("name"),
                    bio.get("blurb"), bio.get("content"),
                    a.get("instagram"), a.get("soundcloud"), a.get("facebook"),
                    a.get("website"), a.get("followerCount"),
                    a.get("contentUrl"), now_iso(),
                ))
                fetched += 1

        conn.commit()
        time.sleep(delay)

    print(progress(len(slugs), len(slugs),
                   f"done — {fetched} found, {not_found} not on RA, {errors} errors"))

# ── JSON export ───────────────────────────────────────────────────────────────

def export_json(conn: sqlite3.Connection, artist_names: list[str]) -> None:
    cur = conn.cursor()

    # venues.json — keyed by venue_id, only rows with real data
    rows = cur.execute("""
        SELECT id, name, address, capacity, blurb, photo, logo_url,
               content_url, follower_count, is_closed, latitude, longitude, website
        FROM venues
        WHERE name IS NOT NULL
        ORDER BY id
    """).fetchall()

    venues_out: dict = {}
    for r in rows:
        venues_out[r[0]] = {
            "name":          r[1],
            "address":       r[2],
            "capacity":      r[3],
            "blurb":         r[4],
            "photo":         r[5],
            "logoUrl":       r[6],
            "contentUrl":    r[7],
            "followerCount": r[8],
            "isClosed":      bool(r[9]),
            "latitude":      r[10],
            "longitude":     r[11],
            "website":       r[12],
        }

    VENUES_JSON.write_text(json.dumps(venues_out, ensure_ascii=False, indent=2))
    print(f"\nExported {len(venues_out)} venues → {VENUES_JSON.name}")

    # artists.json — keyed by original name (as it appears in data.json)
    slug_to_row: dict = {}
    rows = cur.execute("""
        SELECT slug, ra_id, name, image, cover_image, country, area,
               bio_blurb, bio_content, instagram, soundcloud, facebook,
               website, follower_count, content_url
        FROM artists
        WHERE not_found = 0 AND name IS NOT NULL
    """).fetchall()

    for r in rows:
        slug_to_row[r[0]] = {
            "id":            r[1],
            "name":          r[2],
            "image":         r[3],
            "coverImage":    r[4],
            "country":       r[5],
            "area":          r[6],
            "bioBlurb":      r[7],
            "bioContent":    r[8],
            "instagram":     r[9],
            "soundcloud":    r[10],
            "facebook":      r[11],
            "website":       r[12],
            "followerCount": r[13],
            "contentUrl":    r[14],
        }

    artists_out: dict = {}
    for name in artist_names:
        s = to_slug(name)
        if s in slug_to_row:
            artists_out[name] = slug_to_row[s]

    ARTISTS_JSON.write_text(json.dumps(artists_out, ensure_ascii=False, indent=2))
    print(f"Exported {len(artists_out)} artists → {ARTISTS_JSON.name}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich RA dashboard data")
    parser.add_argument("--venues-only",  action="store_true", help="Fetch venues only")
    parser.add_argument("--artists-only", action="store_true", help="Fetch artists only")
    parser.add_argument("--export-only",  action="store_true", help="Skip fetching, export JSON from DB")
    parser.add_argument("--batch-size", type=int,   default=DEFAULT_BATCH, help=f"Items per API request (default {DEFAULT_BATCH})")
    parser.add_argument("--delay",      type=float, default=DEFAULT_DELAY, help=f"Seconds between requests (default {DEFAULT_DELAY})")
    args = parser.parse_args()

    print(f"Loading {DATA_JSON.name} ...")
    data = json.loads(DATA_JSON.read_text())

    venue_ids    = list({e["venue_id"] for e in data if e.get("venue_id")})
    artist_names = list({a for e in data for a in e.get("artists", []) if a})
    print(f"  {len(venue_ids)} unique venue IDs · {len(artist_names)} unique artist names")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)

    if not args.export_only:
        if not args.artists_only:
            enrich_venues(conn, venue_ids, args.batch_size, args.delay)
        if not args.venues_only:
            enrich_artists(conn, artist_names, args.batch_size, args.delay)

    export_json(conn, artist_names)
    conn.close()
    print("\nAll done.")


if __name__ == "__main__":
    main()
