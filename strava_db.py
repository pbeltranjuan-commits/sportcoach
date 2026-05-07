"""
strava_db.py  –  Capa Supabase per a dades Strava + injecció a long_term_memories (RAG)

TAULES NECESSÀRIES (executa setup_sql() al SQL Editor de Supabase):
  - strava_tokens      → tokens OAuth per usuari
  - strava_activities  → activitats sincronitzades
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from database import get_db


# ═══════════════════════════════════════════════════════════════════════════════
# SQL DE CONFIGURACIÓ  (executa una sola vegada al Supabase SQL Editor)
# ═══════════════════════════════════════════════════════════════════════════════

SETUP_SQL = """
-- ── Tokens OAuth de Strava ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS strava_tokens (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    strava_athlete_id   BIGINT NOT NULL,
    access_token        TEXT NOT NULL,
    refresh_token       TEXT NOT NULL,
    expires_at          BIGINT NOT NULL,
    athlete_firstname   TEXT,
    athlete_lastname    TEXT,
    athlete_city        TEXT,
    athlete_country     TEXT,
    athlete_profile_url TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ── Activitats de Strava ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS strava_activities (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    strava_id        BIGINT NOT NULL,
    name             TEXT,
    sport_type       TEXT,
    start_date       TIMESTAMPTZ,
    start_date_local TIMESTAMPTZ,
    elapsed_time_s   INTEGER,
    moving_time_s    INTEGER,
    distance_m       FLOAT,
    elevation_gain_m FLOAT,
    avg_speed_ms     FLOAT,
    max_speed_ms     FLOAT,
    avg_heartrate    FLOAT,
    max_heartrate    FLOAT,
    avg_cadence      FLOAT,
    avg_watts        FLOAT,
    suffer_score     INTEGER,
    kudos_count      INTEGER DEFAULT 0,
    pr_count         INTEGER DEFAULT 0,
    map_polyline     TEXT,
    trainer          BOOLEAN DEFAULT FALSE,
    commute          BOOLEAN DEFAULT FALSE,
    description      TEXT,
    synced_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, strava_id)
);

CREATE INDEX IF NOT EXISTS idx_strava_act_user_date
    ON strava_activities(user_id, start_date DESC);
CREATE INDEX IF NOT EXISTS idx_strava_act_sport
    ON strava_activities(user_id, sport_type);

-- RLS
ALTER TABLE strava_tokens     ENABLE ROW LEVEL SECURITY;
ALTER TABLE strava_activities ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='strava_tokens' AND policyname='strava_tokens_rls') THEN
    CREATE POLICY strava_tokens_rls ON strava_tokens FOR ALL USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='strava_activities' AND policyname='strava_activities_rls') THEN
    CREATE POLICY strava_activities_rls ON strava_activities FOR ALL USING (auth.uid() = user_id);
  END IF;
END $$;
"""


# ═══════════════════════════════════════════════════════════════════════════════
# TOKENS
# ═══════════════════════════════════════════════════════════════════════════════

def save_token(user_id: str, token_data: dict, athlete: dict) -> bool:
    db = get_db()
    payload = {
        "user_id":             user_id,
        "strava_athlete_id":   athlete.get("id"),
        "access_token":        token_data["access_token"],
        "refresh_token":       token_data["refresh_token"],
        "expires_at":          token_data["expires_at"],
        "athlete_firstname":   athlete.get("firstname", ""),
        "athlete_lastname":    athlete.get("lastname", ""),
        "athlete_city":        athlete.get("city", ""),
        "athlete_country":     athlete.get("country", ""),
        "athlete_profile_url": athlete.get("profile", ""),
        "updated_at":          datetime.utcnow().isoformat(),
    }
    res = db.table("strava_tokens").upsert(payload, on_conflict="user_id").execute()
    return bool(res.data)


def get_token(user_id: str) -> Optional[dict]:
    db = get_db()
    res = db.table("strava_tokens").select("*").eq("user_id", user_id).limit(1).execute()
    return res.data[0] if res.data else None


def update_token(user_id: str, new_tok: dict) -> bool:
    db = get_db()
    res = db.table("strava_tokens").update({
        "access_token":  new_tok["access_token"],
        "refresh_token": new_tok.get("refresh_token"),
        "expires_at":    new_tok["expires_at"],
        "updated_at":    datetime.utcnow().isoformat(),
    }).eq("user_id", user_id).execute()
    return bool(res.data)


def delete_token(user_id: str) -> bool:
    db = get_db()
    db.table("strava_tokens").delete().eq("user_id", user_id).execute()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITATS
# ═══════════════════════════════════════════════════════════════════════════════

def upsert_activities(user_id: str, activities: list[dict]) -> int:
    """Desa o actualitza una llista d'activitats parseades. Retorna nre. de files."""
    if not activities:
        return 0
    db = get_db()
    now = datetime.utcnow().isoformat()
    rows = [{**act, "user_id": user_id, "synced_at": now} for act in activities]
    res = db.table("strava_activities").upsert(rows, on_conflict="user_id,strava_id").execute()
    return len(res.data) if res.data else 0


def fetch_activities(user_id: str, sport_type: str = None,
                     limit: int = 200) -> list[dict]:
    db = get_db()
    q = (db.table("strava_activities")
         .select("*")
         .eq("user_id", user_id)
         .order("start_date", desc=True)
         .limit(limit))
    if sport_type:
        q = q.eq("sport_type", sport_type)
    return q.execute().data or []


def get_last_sync_date(user_id: str) -> Optional[datetime]:
    db = get_db()
    res = (db.table("strava_activities")
           .select("start_date")
           .eq("user_id", user_id)
           .order("start_date", desc=True)
           .limit(1)
           .execute())
    if res.data:
        try:
            return datetime.fromisoformat(res.data[0]["start_date"].replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def get_summary(user_id: str) -> dict:
    """Estadístiques agregades per sport_type."""
    acts = fetch_activities(user_id, limit=5000)
    by_sport: dict[str, dict] = {}
    totals = {"count": 0, "distance_km": 0.0, "time_h": 0.0, "elevation_m": 0.0}
    for a in acts:
        sp = a.get("sport_type", "Other")
        if sp not in by_sport:
            by_sport[sp] = {"count": 0, "distance_km": 0.0, "time_h": 0.0, "elevation_m": 0.0}
        d  = (a.get("distance_m") or 0) / 1000
        t  = (a.get("moving_time_s") or 0) / 3600
        el = (a.get("elevation_gain_m") or 0)
        for bucket in (by_sport[sp], totals):
            bucket["count"]       += 1
            bucket["distance_km"] += d
            bucket["time_h"]      += t
            bucket["elevation_m"] += el
    return {"by_sport": by_sport, "totals": totals}


# ═══════════════════════════════════════════════════════════════════════════════
# INJECCIÓ A MEMÒRIA RAG  (long_term_memories de xats.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_embedding(text: str) -> list[float]:
    """Usa el mateix model d'embeddings que xats.py."""
    from sentence_transformers import SentenceTransformer
    import streamlit as st

    @st.cache_resource
    def _load():
        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    return _load().encode(text, normalize_embeddings=True).tolist()


def activity_to_memory_text(act: dict) -> str:
    """Converteix una activitat en text llegible per al RAG."""
    date_str = ""
    if act.get("start_date_local"):
        try:
            dt = datetime.fromisoformat(act["start_date_local"].replace("Z", ""))
            date_str = dt.strftime("%d/%m/%Y")
        except Exception:
            date_str = act["start_date_local"][:10]

    sport   = act.get("sport_type", "Activitat")
    name    = act.get("name", "")
    dist_km = round((act.get("distance_m") or 0) / 1000, 2)
    time_s  = act.get("moving_time_s") or 0
    h, rem  = divmod(time_s, 3600)
    m, s    = divmod(rem, 60)
    time_str = f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"

    parts = [f"[{date_str}] STRAVA {sport}: '{name}'"]
    if dist_km:
        parts.append(f"distància {dist_km} km")
    parts.append(f"temps {time_str}")
    if act.get("elevation_gain_m"):
        parts.append(f"desnivell +{int(act['elevation_gain_m'])} m")
    if act.get("avg_heartrate"):
        parts.append(f"FC mitjana {int(act['avg_heartrate'])} bpm")
    if act.get("max_heartrate"):
        parts.append(f"FC màxima {int(act['max_heartrate'])} bpm")
    if act.get("avg_speed_ms"):
        speed_kmh = act["avg_speed_ms"] * 3.6
        if sport in ("Run", "TrailRun"):
            pace_s = 1000 / act["avg_speed_ms"]
            pm, ps = divmod(int(pace_s), 60)
            parts.append(f"ritme {pm}:{ps:02d} min/km")
        else:
            parts.append(f"velocitat {round(speed_kmh, 1)} km/h")
    if act.get("suffer_score"):
        parts.append(f"suffer score {act['suffer_score']}")
    if act.get("pr_count") and act["pr_count"] > 0:
        parts.append(f"{act['pr_count']} PR assolits")

    return ", ".join(parts)


def inject_activities_to_memory(user_id: str, activities: list[dict],
                                 force: bool = False) -> int:
    """
    Converteix les activitats en textos i els desa a long_term_memories amb embedding.
    Comprava si ja existeix (per strava_id) per evitar duplicats.
    Retorna el nombre de registres nous inserits.
    """
    db = get_db()
    inserted = 0

    for act in activities:
        strava_id = act.get("strava_id")
        if not strava_id:
            continue

        # Comprovació de duplicat per contingut
        marker = f"STRAVA_ID:{strava_id}"
        if not force:
            existing = (db.table("long_term_memories")
                        .select("id")
                        .eq("user_id", user_id)
                        .ilike("content", f"%{marker}%")
                        .limit(1)
                        .execute())
            if existing.data:
                continue  # ja existeix

        text = f"{marker} | {activity_to_memory_text(act)}"
        try:
            emb = _get_embedding(text)
            db.table("long_term_memories").insert({
                "user_id":   user_id,
                "content":   text,
                "embedding": emb,
            }).execute()
            inserted += 1
        except Exception:
            continue

    return inserted
