"""
strava_api.py  –  Client REST per a l'API de Strava (OAuth + dades)
"""

from __future__ import annotations
import urllib.parse
from datetime import datetime
from typing import Optional
import requests
from strava_config import get_strava_config, STRAVA_AUTH_URL, STRAVA_TOKEN_URL, STRAVA_API_BASE, STRAVA_SCOPE


# ── OAuth ─────────────────────────────────────────────────────────────────────

def build_auth_url() -> str:
    cfg = get_strava_config()
    params = {
        "client_id":       cfg["client_id"],
        "redirect_uri":    cfg["redirect_uri"],
        "response_type":   "code",
        "approval_prompt": "auto",
        "scope":           STRAVA_SCOPE,
    }
    return f"{STRAVA_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Intercanvia el codi OAuth per access_token + refresh_token."""
    cfg = get_strava_config()
    r = requests.post(STRAVA_TOKEN_URL, data={
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code":          code,
        "grant_type":    "authorization_code",
    }, timeout=15)
    r.raise_for_status()
    return r.json()


def refresh_token(refresh_tok: str) -> dict:
    cfg = get_strava_config()
    r = requests.post(STRAVA_TOKEN_URL, data={
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "grant_type":    "refresh_token",
        "refresh_token": refresh_tok,
    }, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Peticions autenticades ────────────────────────────────────────────────────

def _get(endpoint: str, token: str, params: dict = None):
    r = requests.get(
        f"{STRAVA_API_BASE}/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_athlete(token: str) -> dict:
    return _get("athlete", token)


def get_athlete_stats(token: str, athlete_id: int) -> dict:
    return _get(f"athletes/{athlete_id}/stats", token)


def get_activities_page(token: str, page: int = 1, per_page: int = 100,
                        after: Optional[datetime] = None) -> list[dict]:
    params = {"page": page, "per_page": per_page}
    if after:
        params["after"] = int(after.timestamp())
    return _get("athlete/activities", token, params)


def get_all_activities(token: str, after: Optional[datetime] = None,
                       max_pages: int = 20) -> list[dict]:
    """Recull totes les activitats paginant automàticament."""
    all_acts = []
    for page in range(1, max_pages + 1):
        batch = get_activities_page(token, page=page, after=after)
        if not batch:
            break
        all_acts.extend(batch)
        if len(batch) < 100:
            break
    return all_acts


# ── Parseig ───────────────────────────────────────────────────────────────────

def parse_activity(raw: dict) -> dict:
    """Normalitza un dict d'activitat Strava al format de la taula Supabase."""
    def safe(val, cast=float, default=None):
        try:
            return cast(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    return {
        "strava_id":          raw.get("id"),
        "name":               raw.get("name", ""),
        "sport_type":         raw.get("sport_type") or raw.get("type", ""),
        "start_date":         raw.get("start_date"),
        "start_date_local":   raw.get("start_date_local"),
        "elapsed_time_s":     safe(raw.get("elapsed_time"), int),
        "moving_time_s":      safe(raw.get("moving_time"), int),
        "distance_m":         safe(raw.get("distance")),
        "elevation_gain_m":   safe(raw.get("total_elevation_gain")),
        "avg_speed_ms":       safe(raw.get("average_speed")),
        "max_speed_ms":       safe(raw.get("max_speed")),
        "avg_heartrate":      safe(raw.get("average_heartrate")),
        "max_heartrate":      safe(raw.get("max_heartrate")),
        "avg_cadence":        safe(raw.get("average_cadence")),
        "avg_watts":          safe(raw.get("average_watts")),
        "suffer_score":       safe(raw.get("suffer_score"), int),
        "kudos_count":        safe(raw.get("kudos_count"), int, 0),
        "pr_count":           safe(raw.get("pr_count"), int, 0),
        "map_polyline":       (raw.get("map") or {}).get("summary_polyline", ""),
        "trainer":            bool(raw.get("trainer", False)),
        "commute":            bool(raw.get("commute", False)),
        "description":        raw.get("description", "") or "",
    }
