"""
strava_sync.py  –  Pàgina Streamlit "🚴 Strava" per a SportCoach IA

Funcions:
  1. Connexió / desconnexió OAuth amb Strava
  2. Sincronització d'activitats a Supabase (strava_activities)
  3. Injecció automàtica a long_term_memories (RAG)
  4. Visualització ràpida d'activitats i estadístiques
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import streamlit as st

from strava_config import activity_emoji
from strava_api import (
    build_auth_url,
    exchange_code,
    refresh_token as api_refresh_token,
    get_athlete,
    get_all_activities,
    parse_activity,
)
from strava_db import (
    save_token,
    get_token,
    update_token,
    delete_token,
    upsert_activities,
    fetch_activities,
    get_last_sync_date,
    get_summary,
    inject_activities_to_memory,
    activity_to_memory_text,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers de sessió i token
# ══════════════════════════════════════════════════════════════════════════════

def _user_id() -> str:
    return st.session_state.get("user_id", "anonymous")


def _get_valid_token() -> Optional[str]:
    """
    Retorna un access_token vàlid.
    Ordre: session_state → DB → refresh si caducat → None.
    """
    tok = st.session_state.get("strava_token")
    if not tok:
        tok = get_token(_user_id())
        if tok:
            st.session_state["strava_token"] = tok

    if not tok:
        return None

    # Refresh si caduca en menys de 5 minuts
    if datetime.utcnow().timestamp() > tok.get("expires_at", 0) - 300:
        try:
            new_tok = api_refresh_token(tok["refresh_token"])
            update_token(_user_id(), new_tok)
            st.session_state["strava_token"] = {**tok, **new_tok}
            return new_tok["access_token"]
        except Exception as e:
            st.warning(f"⚠️ No s'ha pogut renovar el token de Strava: {e}")
            return None

    return tok["access_token"]


def _disconnect():
    delete_token(_user_id())
    st.session_state.pop("strava_token", None)
    st.session_state.pop("strava_athlete", None)
    st.success("Compte de Strava desconnectat.")
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Gestió callback OAuth
# ══════════════════════════════════════════════════════════════════════════════

def _handle_oauth_callback():
    """Si la URL conté ?code=..., intercanvia el codi i guarda el token + atleta."""
    params = st.query_params
    code  = params.get("code")
    error = params.get("error")

    if error:
        st.error(f"Strava ha retornat un error: {error}")
        st.query_params.clear()
        return

    if not code:
        return

    with st.spinner("Connectant amb Strava…"):
        try:
            token_data = exchange_code(code)
            athlete    = token_data.get("athlete") or {}

            # Si Strava no retorna l'atleta dins el token, fem crida explícita
            if not athlete.get("id"):
                athlete = get_athlete(token_data["access_token"])

            save_token(_user_id(), token_data, athlete)
            st.session_state["strava_token"]  = token_data
            st.session_state["strava_athlete"] = athlete
            st.query_params.clear()
            st.success("✅ Connectat amb Strava correctament!")
            st.rerun()
        except Exception as e:
            st.error(f"Error en connectar amb Strava: {e}")
            st.query_params.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Seccions UI
# ══════════════════════════════════════════════════════════════════════════════

def _section_connection(access_token: Optional[str]):
    st.subheader("🔗 Connexió")

    if access_token:
        athlete = st.session_state.get("strava_athlete")
        if not athlete:
            tok_row = get_token(_user_id()) or {}
            athlete = {
                "firstname": tok_row.get("athlete_firstname", ""),
                "lastname":  tok_row.get("athlete_lastname", ""),
                "city":      tok_row.get("athlete_city", ""),
            }

        name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip() or "Atleta"
        city = athlete.get("city", "")

        col_info, col_btn = st.columns([4, 1])
        with col_info:
            st.success(f"✅ Connectat com **{name}**" + (f" · {city}" if city else ""))
        with col_btn:
            if st.button("Desconnectar", type="secondary", use_container_width=True):
                _disconnect()

        last_sync = get_last_sync_date(_user_id())
        if last_sync:
            st.caption(f"Última activitat sincronitzada: {last_sync.strftime('%d/%m/%Y %H:%M')}")
    else:
        st.info("Connecta el teu compte de Strava per sincronitzar les teves activitats.")
        st.link_button("🚴 Connectar amb Strava", build_auth_url(), type="primary")


def _section_sync(access_token: str):
    st.subheader("🔄 Sincronitzar activitats")

    last_sync = get_last_sync_date(_user_id())

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        options = {
            "Des de l'última sync": -1,
            "Últims 7 dies":        7,
            "Últims 30 dies":       30,
            "Últims 90 dies":       90,
            "Últim any":            365,
            "Totes":                0,
        }
        default_key = "Des de l'última sync" if last_sync else "Últims 30 dies"
        selected = st.selectbox("Sincronitzar", list(options.keys()),
                                index=list(options.keys()).index(default_key))
        days = options[selected]

    with col2:
        inject_rag = st.checkbox(
            "Injectar a memòria RAG", value=True,
            help="Desa les activitats com a memòries per al xat IA",
        )
    with col3:
        st.write(""); st.write("")
        sync_btn = st.button("▶️ Sync", type="primary", use_container_width=True)

    if not sync_btn:
        return

    # Calcula `after`
    if days == -1:
        after = last_sync
    elif days == 0:
        after = None
    else:
        after = datetime.utcnow() - timedelta(days=days)

    progress = st.progress(0, text="Obtenint activitats de Strava…")

    try:
        raw_activities = get_all_activities(access_token, after=after)
    except Exception as e:
        st.error(f"Error en obtenir activitats: {e}")
        progress.empty()
        return

    if not raw_activities:
        st.info("No s'han trobat activitats en el període seleccionat.")
        progress.empty()
        return

    progress.progress(40, text=f"Parsejant {len(raw_activities)} activitats…")
    parsed = [parse_activity(a) for a in raw_activities]

    progress.progress(60, text="Desant a Supabase…")
    try:
        saved = upsert_activities(_user_id(), parsed)
    except Exception as e:
        st.error(f"Error en desar activitats: {e}")
        progress.empty()
        return

    rag_inserted = 0
    if inject_rag:
        progress.progress(80, text="Injectant a memòria RAG…")
        try:
            rag_inserted = inject_activities_to_memory(_user_id(), parsed)
        except Exception as e:
            st.warning(f"Activitats desades, però error en RAG: {e}")

    progress.progress(100, text="✅ Sincronització completada!")
    progress.empty()

    c1, c2, c3 = st.columns(3)
    c1.metric("Activitats obtingudes",   len(raw_activities))
    c2.metric("Desades / actualitzades", saved)
    if inject_rag:
        c3.metric("Noves memòries RAG", rag_inserted)

    st.rerun()


def _section_stats():
    st.subheader("📊 Resum d'activitats")

    try:
        summary = get_summary(_user_id())
    except Exception as e:
        st.warning(f"No s'han pogut carregar les estadístiques: {e}")
        return

    totals   = summary.get("totals", {})
    by_sport = summary.get("by_sport", {})

    if not totals.get("count"):
        st.info("Encara no hi ha activitats sincronitzades.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total activitats", totals["count"])
    c2.metric("Distància total",  f"{totals['distance_km']:.0f} km")
    c3.metric("Temps total",      f"{totals['time_h']:.1f} h")
    c4.metric("Desnivell total",  f"{totals['elevation_m']:.0f} m")

    if by_sport:
        st.write("")
        cols = st.columns(min(len(by_sport), 4))
        for i, (sport, data) in enumerate(
            sorted(by_sport.items(), key=lambda x: x[1]["count"], reverse=True)
        ):
            with cols[i % 4]:
                st.markdown(f"**{activity_emoji(sport)} {sport}**")
                st.caption(
                    f"{data['count']} act · "
                    f"{data['distance_km']:.0f} km · "
                    f"{data['time_h']:.1f} h"
                )


def _section_activities():
    st.subheader("📋 Activitats recents")

    col1, col2 = st.columns([2, 1])
    with col1:
        sport_filter = st.text_input("Filtrar per esport (ex: Run, Ride…)", value="")
    with col2:
        limit = st.selectbox("Mostrar", [25, 50, 100, 200], index=1)

    try:
        acts = fetch_activities(
            _user_id(),
            sport_type=sport_filter.strip() or None,
            limit=limit,
        )
    except Exception as e:
        st.warning(f"Error en carregar activitats: {e}")
        return

    if not acts:
        st.info("No s'han trobat activitats.")
        return

    st.caption(f"Mostrant {len(acts)} activitats")

    for act in acts:
        sport = act.get("sport_type", "")
        emoji = activity_emoji(sport)
        name  = act.get("name") or sport

        date_str = ""
        if act.get("start_date_local"):
            try:
                dt = datetime.fromisoformat(act["start_date_local"].replace("Z", ""))
                date_str = dt.strftime("%d/%m/%Y")
            except Exception:
                date_str = str(act["start_date_local"])[:10]

        dist_km = round((act.get("distance_m") or 0) / 1000, 2)
        time_s  = act.get("moving_time_s") or 0
        h, rem  = divmod(time_s, 3600)
        m, s    = divmod(rem, 60)
        time_str = f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"

        hr_str = f" · ❤️ {int(act['avg_heartrate'])} bpm" if act.get("avg_heartrate") else ""
        el_str = f" · ⛰️ +{int(act['elevation_gain_m'])} m" if act.get("elevation_gain_m") else ""

        with st.expander(f"{emoji} {name}  —  {date_str}  ·  {dist_km} km  ·  {time_str}{hr_str}{el_str}"):
            if act.get("description"):
                st.caption(act["description"])
            st.code(activity_to_memory_text(act), language=None)


# ══════════════════════════════════════════════════════════════════════════════
# Punt d'entrada principal
# ══════════════════════════════════════════════════════════════════════════════

def show():
    st.title("🚴 Strava")

    _handle_oauth_callback()

    access_token = _get_valid_token()

    _section_connection(access_token)

    if not access_token:
        return

    st.divider()
    _section_sync(access_token)

    st.divider()
    _section_stats()

    st.divider()
    _section_activities()


if __name__ == "__main__":
    show()
