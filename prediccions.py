import streamlit as st
import numpy as np
from database import get_db
from datetime import datetime, date


# =====================================================
# MODELS MATEMÀTICS
# =====================================================

def calcular_fitness_score(hrv, fc_repos, fc_max, hores_son, qualitat_son, fatiga, motivacio):
    """Calcula un fitness score 0-100 basat en les dades de l'usuari."""
    # Normalitzar cada variable (0-1)
    hrv_score = min(hrv / 100, 1.0) if hrv else 0.5
    fc_score = max(0, 1 - (fc_repos - 40) / 60) if fc_repos else 0.5
    son_hores_score = min(hores_son / 9, 1.0) if hores_son else 0.5
    son_qualitat_score = qualitat_son / 10 if qualitat_son else 0.5
    fatiga_score = 1 - (fatiga / 10) if fatiga else 0.5
    motivacio_score = motivacio / 10 if motivacio else 0.5

    # Pesos de cada factor
    score = (
        hrv_score * 0.30 +
        fc_score * 0.20 +
        son_hores_score * 0.15 +
        son_qualitat_score * 0.15 +
        fatiga_score * 0.10 +
        motivacio_score * 0.10
    ) * 100

    return round(score, 1)


def ritme_base_a_segons(ritme_str):
    """Converteix 'MM:SS' a segons per km."""
    try:
        parts = ritme_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except:
        return None


def prediu_temps_carrera_montecarlo(ritme_base_seg, fitness_score, distancia_km, desnivell_m=0, n_sim=10000):
    """
    Model Monte Carlo per predir temps de carrera.
    - ritme_base_seg: ritme de referència en seg/km
    - fitness_score: 0-100
    - distancia_km: distància objectiu
    - desnivell_m: desnivell acumulat en metres
    - n_sim: nombre de simulacions
    """
    # Factor fitness: millor fitness = ritme més ràpid
    factor_fitness = 1 + (50 - fitness_score) / 200

    # Factor desnivell: cada 100m de desnivell aprox +6% temps
    factor_desnivell = 1 + (desnivell_m / 100) * 0.06

    # Ritme ajustat per distància (Riegel's formula aproximada)
    if distancia_km <= 5:
        factor_dist = 1.0
    elif distancia_km <= 10:
        factor_dist = 1.04
    elif distancia_km <= 21.1:
        factor_dist = 1.10
    else:
        factor_dist = 1.18

    ritme_ajustat = ritme_base_seg * factor_fitness * factor_desnivell * factor_dist

    # Monte Carlo: simulem variabilitat en el rendiment
    variabilitat = np.random.normal(0, ritme_ajustat * 0.04, n_sim)  # 4% desv estàndard
    ritmes_simulats = ritme_ajustat + variabilitat
    temps_simulats = ritmes_simulats * distancia_km

    p10 = np.percentile(temps_simulats, 10)
    p50 = np.percentile(temps_simulats, 50)
    p90 = np.percentile(temps_simulats, 90)

    return p10, p50, p90


def calcular_risc_lesio_montecarlo(fatiga_hist, son_hist, hrv_hist, n_sim=10000):
    """
    Model Monte Carlo per estimar risc de lesió.
    Bassat en variabilitat de fatiga, son i HRV.
    """
    if not fatiga_hist or len(fatiga_hist) < 2:
        return None, None

    # Càlcul ACWR (Acute:Chronic Workload Ratio) simplificat amb fatiga
    fatiga_arr = np.array(fatiga_hist[-28:])
    aguda = np.mean(fatiga_arr[-7:]) if len(fatiga_arr) >= 7 else np.mean(fatiga_arr)
    cronica = np.mean(fatiga_arr) if len(fatiga_arr) >= 14 else aguda
    acwr = aguda / cronica if cronica > 0 else 1.0

    # Variabilitat HRV (alta variabilitat = menys recuperat)
    hrv_arr = np.array(hrv_hist) if hrv_hist else np.array([60])
    hrv_variabilitat = np.std(hrv_arr) / (np.mean(hrv_arr) + 1e-6)

    # Son deficient (< 7h de mitjana últims 7 dies)
    son_arr = np.array(son_hist[-7:]) if son_hist else np.array([7.5])
    son_deficit = max(0, 7 - np.mean(son_arr)) / 7

    # Factor de risc base
    risc_base = (
        (max(0, acwr - 1.0) * 0.5) +
        (hrv_variabilitat * 0.3) +
        (son_deficit * 0.2)
    )
    risc_base = min(risc_base, 1.0)

    # Monte Carlo
    variabilitat = np.random.normal(risc_base, risc_base * 0.2 + 0.05, n_sim)
    variabilitat = np.clip(variabilitat, 0, 1)

    risc_median = np.percentile(variabilitat, 50) * 100
    risc_p90 = np.percentile(variabilitat, 90) * 100

    return round(risc_median, 1), round(risc_p90, 1), round(acwr, 2)


def recomanar_dia_entrenament(sensacions_recents):
    """Recomana el millor dia per entrenar basant-se en tendències."""
    if not sensacions_recents or len(sensacions_recents) < 3:
        return None

    scores = []
    for s in sensacions_recents:
        score = (
            (10 - s.get('fatigue_level', 5)) * 0.4 +
            s.get('motivation', 5) * 0.3 +
            s.get('sleep_quality', 5) * 0.2 +
            (s.get('sleep_hours', 7) / 9 * 10) * 0.1
        )
        scores.append(score)

    tendencia = np.polyfit(range(len(scores)), scores, 1)[0]
    avg_score = np.mean(scores[-3:])

    if avg_score >= 7 and tendencia >= 0:
        return "avui", avg_score, "🟢 Forma excel·lent"
    elif avg_score >= 5:
        return "demà o demà passat", avg_score, "🟡 Forma moderada"
    else:
        return "en 2-3 dies", avg_score, "🔴 Necessites recuperació"


def segons_a_temps(segons):
    """Converteix segons a format H:MM:SS o MM:SS."""
    segons = int(segons)
    h = segons // 3600
    m = (segons % 3600) // 60
    s = segons % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# =====================================================
# INTERFÍCIE PRINCIPAL
# =====================================================

def mostrar_prediccions():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return

    supabase = get_db()
    user_id = st.session_state.user.id

    st.title("📊 Prediccions Monte Carlo")
    st.caption("Model estadístic basat en les teves dades reals")

    # Carregar dades de sensacions
    sens_res = supabase.table("training_sensations") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("date", desc=False) \
        .execute()
    sensacions = sens_res.data if sens_res.data else []

    # Extreure historials
    fatiga_hist = [s['fatigue_level'] for s in sensacions if s.get('fatigue_level')]
    son_hist = [s['sleep_hours'] for s in sensacions if s.get('sleep_hours')]
    hrv_hist = []  # S'omplirà amb input manual per ara

    # Última entrada
    ultima = sensacions[-1] if sensacions else {}

    st.markdown("---")

    # =====================================================
    # SECCIÓ 1: DADES D'ENTRADA
    # =====================================================
    st.markdown("### 📥 Les teves dades")
    st.caption("Introdueix les teves dades actuals per generar prediccions")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**❤️ Dades cardíaques**")
        hrv = st.number_input("HRV (ms)", min_value=0, max_value=200,
                               value=60, help="Heart Rate Variability en mil·lisegons")
        fc_repos = st.number_input("FC en repòs (ppm)", min_value=30, max_value=120,
                                    value=int(ultima.get('resting_hr', 55)))
        fc_max = st.number_input("FC màxima (ppm)", min_value=100, max_value=220,
                                  value=185)

    with col2:
        st.markdown("**😴 Son**")
        hores_son = st.number_input("Hores de son", min_value=0.0, max_value=12.0,
                                     value=float(ultima.get('sleep_hours', 7.5)), step=0.5)
        qualitat_son = st.slider("Qualitat son", 1, 10,
                                  int(ultima.get('sleep_quality', 7)))

    with col3:
        st.markdown("**💪 Sensacions**")
        fatiga = st.slider("Fatiga actual", 1, 10,
                            int(ultima.get('fatigue_level', 4)))
        motivacio = st.slider("Motivació", 1, 10,
                               int(ultima.get('motivation', 7)))

    st.markdown("**🏃 Ritme de referència**")
    col4, col5 = st.columns(2)
    with col4:
        ritme_input = st.text_input("Ritme base (MM:SS /km)",
                                     value="5:30",
                                     help="El teu ritme còmode actual per km")
    with col5:
        hrv_input = st.text_input("Historial HRV (separats per comes)",
                                   value="",
                                   placeholder="ex: 58,62,55,70,65",
                                   help="Últims valors HRV per calcular risc de lesió")

    if hrv_input:
        try:
            hrv_hist = [float(x.strip()) for x in hrv_input.split(",") if x.strip()]
        except:
            hrv_hist = []

    st.markdown("---")

    # =====================================================
    # BOTÓ GENERAR
    # =====================================================
    if st.button("⚡ Generar Prediccions", type="primary", use_container_width=True):

        ritme_seg = ritme_base_a_segons(ritme_input)
        if not ritme_seg:
            st.error("❌ Format de ritme incorrecte. Usa MM:SS (ex: 5:30)")
            return

        fitness = calcular_fitness_score(hrv, fc_repos, fc_max, hores_son, qualitat_son, fatiga, motivacio)

        # =====================================================
        # SECCIÓ 2: FITNESS SCORE
        # =====================================================
        st.markdown("---")
        st.markdown("### 🎯 Forma Física Actual")

        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            color = "🟢" if fitness >= 70 else "🟡" if fitness >= 50 else "🔴"
            st.metric("Fitness Score", f"{fitness}/100", delta=color)
            if fitness >= 75:
                st.success("Excel·lent forma. Dia ideal per entrenar fort.")
            elif fitness >= 60:
                st.info("Bona forma. Entrenament moderat recomanat.")
            elif fitness >= 45:
                st.warning("Forma acceptable. Evita sobrecàrrega.")
            else:
                st.error("Forma baixa. Prioritza recuperació.")

        with col_f2:
            # Barra visual
            st.progress(int(fitness))
            factors = {
                "HRV": min(hrv / 100, 1.0) * 100,
                "FC repòs": max(0, 1 - (fc_repos - 40) / 60) * 100,
                "Son (h)": min(hores_son / 9, 1.0) * 100,
                "Son (qualitat)": qualitat_son * 10,
                "Fatiga (inv.)": (1 - fatiga / 10) * 100,
                "Motivació": motivacio * 10
            }
            for factor, val in factors.items():
                col_a, col_b = st.columns([2, 3])
                with col_a:
                    st.caption(factor)
                with col_b:
                    st.progress(int(val))

        # =====================================================
        # SECCIÓ 3: PREDICCIONS DE CARRERA
        # =====================================================
        st.markdown("---")
        st.markdown("### 🏁 Prediccions de Carrera")
        st.caption("Simulació Monte Carlo amb 10.000 escenaris")

        # Selector de carrera personalitzada
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            distancia_custom = st.number_input("Distància personalitzada (km)", 1.0, 200.0, 10.0, 0.5)
        with col_d2:
            desnivell_custom = st.number_input("Desnivell acumulat (m)", 0, 5000, 0, 50)

        carreres = [
            ("5K", 5.0, 0),
            ("10K", 10.0, 0),
            ("Mitja Marató", 21.097, 0),
            ("Marató", 42.195, 0),
            (f"Personalitzada ({distancia_custom}km, +{desnivell_custom}m)", distancia_custom, desnivell_custom),
        ]

        for nom, dist, desnivell in carreres:
            p10, p50, p90 = prediu_temps_carrera_montecarlo(
                ritme_seg, fitness, dist, desnivell
            )
            with st.expander(f"🏃 {nom}", expanded=(dist <= 10)):
                col_r1, col_r2, col_r3 = st.columns(3)
                with col_r1:
                    st.metric("🎯 Objectiu realista", segons_a_temps(p50))
                with col_r2:
                    st.metric("🚀 Millor escenari (10%)", segons_a_temps(p10))
                with col_r3:
                    st.metric("🐢 Pitjor escenari (90%)", segons_a_temps(p90))

                ritme_carrera = p50 / dist
                st.caption(f"Ritme mig estimat: {segons_a_temps(ritme_carrera)} /km")

        # =====================================================
        # SECCIÓ 4: RISC DE LESIÓ
        # =====================================================
        st.markdown("---")
        st.markdown("### ⚠️ Risc de Lesió o Sobreentrenament")

        if len(fatiga_hist) >= 7:
            hrv_per_risc = hrv_hist if hrv_hist else [hrv] * len(fatiga_hist)
            resultat = calcular_risc_lesio_montecarlo(fatiga_hist, son_hist, hrv_per_risc)

            if resultat[0] is not None:
                risc_med, risc_p90, acwr = resultat
                col_l1, col_l2, col_l3 = st.columns(3)
                with col_l1:
                    st.metric("Risc medià", f"{risc_med}%")
                with col_l2:
                    st.metric("Risc escenari advers", f"{risc_p90}%")
                with col_l3:
                    st.metric("ACWR (càrrega aguda/crònica)", str(acwr),
                              help="Valor ideal: 0.8-1.3. Per sobre de 1.5 és zona de perill.")

                if risc_med < 20:
                    st.success("🟢 Risc baix. Pots augmentar la càrrega d'entrenament.")
                elif risc_med < 40:
                    st.warning("🟡 Risc moderat. Mantén la càrrega actual i descansa bé.")
                else:
                    st.error("🔴 Risc alt. Redueix la intensitat i prioritza recuperació.")

                if acwr > 1.5:
                    st.error("⚠️ ACWR crític (>1.5): Has augmentat la càrrega massa ràpid. Descans obligatori.")
                elif acwr > 1.3:
                    st.warning("⚠️ ACWR elevat (>1.3): Zona de precaució. Redueix volum.")
        else:
            st.info(f"ℹ️ Necessites almenys 7 dies de dades al formulari de Sensacions per calcular el risc de lesió. Ara en tens {len(fatiga_hist)}.")

        # =====================================================
        # SECCIÓ 5: MILLOR DIA PER ENTRENAR
        # =====================================================
        st.markdown("---")
        st.markdown("### 📅 Millor Moment per Entrenar Fort")

        if len(sensacions) >= 3:
            dia, score, estat = recomanar_dia_entrenament(sensacions[-7:])
            st.markdown(f"**Recomanació:** Entrena **{dia}**")
            st.markdown(f"**Estat actual:** {estat} (score: {score:.1f}/10)")

            if score >= 7:
                st.success("Aprofita! Avui és un dia excel·lent per fer un entrenament de qualitat.")
            elif score >= 5:
                st.info("Pots entrenar, però a intensitat moderada.")
            else:
                st.warning("El teu cos demana recuperació. Opta per descans actiu o res.")
        else:
            st.info(f"ℹ️ Necessites almenys 3 dies de dades al formulari de Sensacions. Ara en tens {len(sensacions)}.")

        st.markdown("---")
        st.caption("⚙️ Les prediccions es basen en models estadístics. No substitueixen el criteri d'un professional mèdic o entrenador titulat.")
