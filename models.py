import streamlit as st
import numpy as np
from database import get_db


# =====================================================
# FUNCIONS MATEMÀTIQUES
# =====================================================

def ritme_a_segons(ritme_str):
    try:
        parts = ritme_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except:
        return None

def segons_a_temps(segons):
    segons = int(segons)
    h = segons // 3600
    m = (segons % 3600) // 60
    s = segons % 60
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

def calcular_vo2max(fc_repos, fc_max, ritme_seg_km):
    resultats = []
    if fc_repos and fc_max and fc_max > fc_repos:
        resultats.append(15 * (fc_max / fc_repos))
    if ritme_seg_km:
        velocitat_ms = 1000 / ritme_seg_km
        resultats.append(min((velocitat_ms * 0.2 + 3.5) / 0.75 * 3.5, 85))
    return round(np.mean(resultats), 1) if resultats else None

def calcular_zones_fc(fc_repos, fc_max):
    fc_reserva = fc_max - fc_repos
    return {
        "Zona 1 — Recuperació (50-60%)":        (int(fc_repos + fc_reserva * 0.50), int(fc_repos + fc_reserva * 0.60)),
        "Zona 2 — Aeròbic base (60-70%)":       (int(fc_repos + fc_reserva * 0.60), int(fc_repos + fc_reserva * 0.70)),
        "Zona 3 — Tempo aeròbic (70-80%)":      (int(fc_repos + fc_reserva * 0.70), int(fc_repos + fc_reserva * 0.80)),
        "Zona 4 — Llindar anaeròbic (80-90%)":  (int(fc_repos + fc_reserva * 0.80), int(fc_repos + fc_reserva * 0.90)),
        "Zona 5 — VO2max (90-100%)":            (int(fc_repos + fc_reserva * 0.90), fc_max),
    }

def calcular_recuperacio(fatiga, hrv, hores_son, qualitat_son, intensitat):
    hores_base = intensitat * 3
    multiplicador = 1 + (fatiga / 10) * 0.4 + max(0, 1 - hrv / 100) * 0.3 + (max(0, 1 - hores_son / 8) * 0.5 + max(0, 1 - qualitat_son / 10) * 0.5) * 0.3
    hores = hores_base * multiplicador
    sim = np.clip(np.random.normal(hores, hores * 0.15, 5000), 4, 96)
    return round(np.percentile(sim, 25), 0), round(np.percentile(sim, 50), 0), round(np.percentile(sim, 75), 0)

def calcular_progressio(sensacions_hist, ritme_inicial_seg, setmanes=12):
    if not sensacions_hist or len(sensacions_hist) < 3:
        return None, None
    motivacions = [s.get('motivation', 5) / 10 for s in sensacions_hist]
    fatigues = [(10 - s.get('fatigue_level', 5)) / 10 for s in sensacions_hist]
    consistencia = np.mean(motivacions) * 0.6 + np.mean(fatigues) * 0.4
    millora_setmanal = consistencia * 0.008
    projectio = []
    for s in range(setmanes + 1):
        r = ritme_inicial_seg * ((1 - millora_setmanal) ** s)
        sim = np.random.normal(r, r * 0.02, 1000)
        projectio.append({'setmana': s, 'p25': round(np.percentile(sim, 25), 1),
                          'p50': round(np.percentile(sim, 50), 1), 'p75': round(np.percentile(sim, 75), 1)})
    return projectio, round(consistencia * 100, 1)

def calcular_correlacio_son(sensacions_hist):
    dades = [(s.get('sleep_hours'), s.get('training_quality'))
             for s in sensacions_hist if s.get('sleep_hours') and s.get('training_quality')]
    if len(dades) < 5:
        return None, None
    son = [d[0] for d in dades]
    rendiment = [d[1] for d in dades]
    correlacio = np.corrcoef(son, rendiment)[0, 1]
    coefs = np.polyfit(son, rendiment, 1)
    return round(correlacio, 2), coefs

def calcular_perdua_pes(pes_actual, pes_objectiu, km_setmanals):
    if not pes_actual or not pes_objectiu or not km_setmanals:
        return None
    kg_a_perdre = pes_actual - pes_objectiu
    if kg_a_perdre <= 0:
        return None
    cals_setmanals = pes_actual * 1.0 * km_setmanals
    cals_total = kg_a_perdre * 7700
    set_running = cals_total / cals_setmanals
    set_combinat = cals_total / (cals_setmanals + 2100)
    sim_r = np.random.normal(set_running, set_running * 0.2, 5000)
    sim_c = np.random.normal(set_combinat, set_combinat * 0.15, 5000)
    return {
        'kg': round(kg_a_perdre, 1),
        'cals': round(cals_setmanals),
        'r_p50': round(np.percentile(sim_r, 50)),
        'r_p75': round(np.percentile(sim_r, 75)),
        'c_p50': round(np.percentile(sim_c, 50)),
        'c_p75': round(np.percentile(sim_c, 75)),
    }


# =====================================================
# INTERFÍCIE
# =====================================================

def mostrar_models():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return

    supabase = get_db()
    user_id = st.session_state.user.id

    sens_res = supabase.table("training_sensations") \
        .select("*").eq("user_id", user_id).order("date", desc=False).execute()
    sensacions = sens_res.data if sens_res.data else []
    ultima = sensacions[-1] if sensacions else {}

    st.title("🧬 Models Avançats")
    st.caption("VO2max · Zones FC · Recuperació · Progressió · Son · Pes")
    st.markdown("---")

    # Dades d'entrada compartides
    st.markdown("### 📥 Dades d'entrada")
    col1, col2, col3 = st.columns(3)
    with col1:
        fc_repos = st.number_input("FC repòs (ppm)", 30, 120, int(ultima.get('resting_hr', 55)))
        fc_max = st.number_input("FC màxima (ppm)", 100, 220, 185)
    with col2:
        hrv = st.number_input("HRV actual (ms)", 0, 200, 60)
        ritme_input = st.text_input("Ritme base (MM:SS /km)", "5:30")
    with col3:
        hores_son = st.number_input("Hores de son", 0.0, 12.0, float(ultima.get('sleep_hours', 7.5)), 0.5)
        qualitat_son = st.slider("Qualitat son", 1, 10, int(ultima.get('sleep_quality', 7)))
        fatiga = st.slider("Fatiga actual", 1, 10, int(ultima.get('fatigue_level', 4)))

    ritme_seg = ritme_a_segons(ritme_input)

    st.markdown("---")

    # Tabs per cada model
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🫁 VO2max", "❤️ Zones FC", "⏱️ Recuperació",
        "📈 Progressió", "😴 Son", "⚖️ Pes"
    ])

    # =====================================================
    # TAB 1: VO2MAX
    # =====================================================
    with tab1:
        st.markdown("### 🫁 Predicció de VO2max")
        st.caption("Estimació basada en FC i ritme de carrera")

        if st.button("Calcular VO2max", type="primary"):
            vo2 = calcular_vo2max(fc_repos, fc_max, ritme_seg)
            if vo2:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("VO2max estimat", f"{vo2} ml/kg/min")
                    if vo2 >= 60:
                        st.success("🟢 Excel·lent (atleta d'alt nivell)")
                    elif vo2 >= 50:
                        st.info("🔵 Molt bo (runner experimentat)")
                    elif vo2 >= 40:
                        st.warning("🟡 Bo (runner recreatiu)")
                    else:
                        st.error("🔴 Baix (marge de millora important)")
                with col_b:
                    st.markdown("**Referència per edat (homes):**")
                    st.table({
                        "Nivell": ["Excel·lent", "Molt bo", "Bo", "Acceptable", "Baix"],
                        "VO2max": [">55", "45-55", "38-45", "30-38", "<30"]
                    })
            else:
                st.error("Comprova les dades introduïdes")

    # =====================================================
    # TAB 2: ZONES FC
    # =====================================================
    with tab2:
        st.markdown("### ❤️ Zones d'Entrenament per FC")
        st.caption("Mètode Karvonen (FC de reserva)")

        if st.button("Calcular Zones FC", type="primary"):
            if fc_max > fc_repos:
                zones = calcular_zones_fc(fc_repos, fc_max)
                colors = ["🔵", "🟢", "🟡", "🟠", "🔴"]
                beneficis = [
                    "Recuperació activa, millora flux sanguini",
                    "Base aeròbica, crema greixos, llarga durada",
                    "Millora resistència, ritme de carrera",
                    "Llindar lactàtic, millora velocitat",
                    "Capacitat màxima, intervals curts"
                ]
                for i, (zona, (min_fc, max_fc)) in enumerate(zones.items()):
                    col_a, col_b, col_c = st.columns([3, 1, 3])
                    with col_a:
                        st.markdown(f"{colors[i]} **{zona}**")
                    with col_b:
                        st.markdown(f"**{min_fc} – {max_fc} ppm**")
                    with col_c:
                        st.caption(beneficis[i])
                    st.divider()
            else:
                st.error("FC màxima ha de ser major que FC en repòs")

    # =====================================================
    # TAB 3: RECUPERACIÓ
    # =====================================================
    with tab3:
        st.markdown("### ⏱️ Temps de Recuperació Òptim")
        st.caption("Model de Banister + Monte Carlo")

        intensitat = st.slider("Intensitat de l'última sessió", 1, 10, 7,
                               help="1=molt suau, 10=competició o màxim esforç")

        if st.button("Calcular Recuperació", type="primary"):
            p25, p50, p75 = calcular_recuperacio(fatiga, hrv, hores_son, qualitat_son, intensitat)
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("⚡ Mínim recomanat", f"{int(p25)}h")
            with col_b:
                st.metric("🎯 Òptim", f"{int(p50)}h")
            with col_c:
                st.metric("🛡️ Conservador", f"{int(p75)}h")

            dies_p50 = p50 / 24
            if dies_p50 <= 1:
                st.success(f"✅ Pots tornar a entrenar en menys d'un dia ({int(p50)}h)")
            elif dies_p50 <= 2:
                st.info(f"ℹ️ Descansa {int(p50)}h (~{dies_p50:.1f} dies) abans de la propera sessió intensa")
            else:
                st.warning(f"⚠️ Necessites {int(p50)}h (~{dies_p50:.1f} dies) de recuperació. Considera sessions suaus.")

    # =====================================================
    # TAB 4: PROGRESSIÓ DE MARCA
    # =====================================================
    with tab4:
        st.markdown("### 📈 Progressió de Marca")
        st.caption("Projecció Monte Carlo basada en la teva consistència d'entrenament")

        setmanes = st.slider("Setmanes de projecció", 4, 24, 12)

        if st.button("Calcular Progressió", type="primary"):
            if not ritme_seg:
                st.error("Comprova el format del ritme (MM:SS)")
            elif len(sensacions) < 3:
                st.warning(f"Necessites almenys 3 dies de Sensacions. Ara en tens {len(sensacions)}.")
            else:
                projectio, consistencia = calcular_progressio(sensacions, ritme_seg, setmanes)
                if projectio:
                    st.metric("Índex de consistència", f"{consistencia}%",
                              help="Basat en la teva motivació i fatiga dels últims dies")

                    st.markdown("**Evolució del ritme projectada:**")
                    col_h, col_m, col_f = st.columns(3)
                    with col_h:
                        st.metric("Ara", ritme_input + " /km")
                    with col_m:
                        mig = projectio[setmanes // 2]
                        st.metric(f"Setmana {setmanes // 2}", segons_a_temps(mig['p50']) + " /km")
                    with col_f:
                        final = projectio[-1]
                        st.metric(f"Setmana {setmanes}", segons_a_temps(final['p50']) + " /km",
                                  delta=f"-{int(ritme_seg - final['p50'])}s/km")

                    st.markdown("**Taula de progressió setmanal:**")
                    taula = []
                    for p in projectio[::2]:  # cada 2 setmanes
                        taula.append({
                            "Setmana": p['setmana'],
                            "Millor cas": segons_a_temps(p['p25']) + " /km",
                            "Previsió": segons_a_temps(p['p50']) + " /km",
                            "Pitjor cas": segons_a_temps(p['p75']) + " /km",
                        })
                    import pandas as pd
                    st.dataframe(pd.DataFrame(taula), use_container_width=True, hide_index=True)

    # =====================================================
    # TAB 5: SON I RENDIMENT
    # =====================================================
    with tab5:
        st.markdown("### 😴 Efecte del Son en el Rendiment")
        st.caption("Correlació estadística entre hores de son i qualitat d'entrenament")

        if st.button("Analitzar Correlació Son", type="primary"):
            if len(sensacions) < 5:
                st.warning(f"Necessites almenys 5 dies de Sensacions. Ara en tens {len(sensacions)}.")
            else:
                correlacio, coefs = calcular_correlacio_son(sensacions)
                if correlacio is not None:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("Correlació son ↔ rendiment", f"{correlacio}")
                        if correlacio >= 0.7:
                            st.success("🟢 Correlació molt forta: el son afecta molt el teu rendiment")
                        elif correlacio >= 0.4:
                            st.info("🔵 Correlació moderada: el son té un efecte notable")
                        elif correlacio >= 0.2:
                            st.warning("🟡 Correlació feble: altres factors influeixen més")
                        else:
                            st.error("🔴 Sense correlació clara")
                    with col_b:
                        if coefs is not None:
                            millora = coefs[0]
                            st.metric("Millora per hora extra de son",
                                      f"+{millora:.2f} punts de qualitat d'entrenament")
                            hores_optimes = max(7, min(9, -coefs[1] / (2 * coefs[0]))) if coefs[0] != 0 else 8
                            st.metric("Hores de son òptimes estimades", f"{hores_optimes:.1f}h")
                else:
                    st.warning("No hi ha prou dades amb les dues variables registrades.")

    # =====================================================
    # TAB 6: PÈRDUA DE PES
    # =====================================================
    with tab6:
        st.markdown("### ⚖️ Predicció de Pèrdua de Pes")
        st.caption("Estimació basada en calories cremades amb running")

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            pes_actual = st.number_input("Pes actual (kg)", 40.0, 200.0, 75.0, 0.5)
        with col_p2:
            pes_objectiu = st.number_input("Pes objectiu (kg)", 40.0, 200.0, 70.0, 0.5)
        with col_p3:
            km_setmanals = st.number_input("Km setmanals de running", 0.0, 200.0, 30.0, 5.0)

        if st.button("Calcular Pèrdua de Pes", type="primary"):
            resultat = calcular_perdua_pes(pes_actual, pes_objectiu, km_setmanals)
            if resultat:
                st.markdown(f"**Objectiu:** perdre {resultat['kg']} kg")
                st.metric("Calories cremades per running/setmana", f"{int(resultat['cals'])} kcal")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**🏃 Només amb running:**")
                    st.metric("Previsió", f"{int(resultat['r_p50'])} setmanes")
                    st.caption(f"Escenari advers: {int(resultat['r_p75'])} setmanes")
                with col_b:
                    st.markdown("**🥗 Running + dieta (-300 kcal/dia):**")
                    st.metric("Previsió", f"{int(resultat['c_p50'])} setmanes")
                    st.caption(f"Escenari advers: {int(resultat['c_p75'])} setmanes")

                st.info("💡 La combinació running + petit dèficit calòric és la forma més sostenible de perdre pes sense perdre rendiment.")
            elif pes_objectiu >= pes_actual:
                st.info("El pes objectiu és igual o superior al pes actual.")

        st.caption("⚙️ Estimacions estadístiques. No substitueixen assessorament nutricional professional.")
