"""
strava_config.py  –  Credencials i constants de Strava per a SportCoach IA
"""

import os
import streamlit as st


def get_strava_config() -> dict:
    """Retorna les credencials des de st.secrets o variables d'entorn."""
    try:
        return {
            "client_id":     st.secrets["strava"]["client_id"],
            "client_secret": st.secrets["strava"]["client_secret"],
            "redirect_uri":  st.secrets["strava"].get("redirect_uri", "http://localhost:8501"),
        }
    except (KeyError, AttributeError):
        return {
            "client_id":     os.getenv("STRAVA_CLIENT_ID", ""),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET", ""),
            "redirect_uri":  os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8501"),
        }


STRAVA_AUTH_URL  = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
STRAVA_API_BASE  = "https://www.strava.com/api/v3"
STRAVA_SCOPE     = "read,activity:read_all,profile:read_all"

ACTIVITY_EMOJI = {
    "Run": "🏃", "TrailRun": "⛰️", "VirtualRun": "🖥️",
    "Ride": "🚴", "VirtualRide": "🖥️",
    "Swim": "🏊", "Walk": "🚶", "Hike": "🥾",
    "WeightTraining": "🏋️", "Workout": "💪",
    "Yoga": "🧘", "Rowing": "🚣", "Soccer": "⚽",
}

def activity_emoji(sport_type: str) -> str:
    return ACTIVITY_EMOJI.get(sport_type, "🏅")
