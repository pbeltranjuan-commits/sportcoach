import streamlit as st
from supabase import create_client
from datetime import datetime

st.set_page_config(page_title="Sensacions", page_icon="💭")

if 'user' not in st.session_state or st.session_state.user is None:
    st.warning("🔒 Has d'iniciar sessió")
    st.stop()

supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
user_id = st.session_state.user.id

st.title("💭 Sensacions de l'Entrenament")

col1, col2 = st.columns(2)

with col1:
    date = st.date_input("Data", datetime.now())
    training_quality = st.slider("Qualitat entrenament ⭐", 1, 10, 7)
    sleep_hours = st.number_input("Hores de son 😴", 0.0, 12.0, 7.5, 0.5)
    sleep_quality = st.slider("Qualitat son 🌙", 1, 10, 7)

with col2:
    fatigue_level = st.slider("Fatiga 😮‍💨", 1, 10, 4)
    motivation = st.slider("Motivació 🔥", 1, 10, 7)
    notes = st.text_area("Notes 📝")

if st.button("💾 Guardar", type="primary"):
    try:
        data = {
            "user_id": user_id,
            "date": date.isoformat(),
            "training_quality": training_quality,
            "sleep_hours": sleep_hours,
            "sleep_quality": sleep_quality,
            "fatigue_level": fatigue_level,
            "motivation": motivation,
            "notes": notes if notes else None
        }
        
        supabase.table("training_sensations").upsert(data).execute()
        st.success("✅ Guardat correctament!")
        st.balloons()
    except Exception as e:
        st.error(f"Error: {e}")
