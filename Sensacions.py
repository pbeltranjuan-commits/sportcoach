import streamlit as st
from database import get_db
from datetime import datetime


# --- EMBEDDINGS LOCALS (reutilitza el mateix model que xats.py) ---
@st.cache_resource
def load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def get_embedding(text):
    model = load_embedding_model()
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()


def mostrar_sensacions():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return

    supabase = get_db()
    user_id = st.session_state.user.id

    # --- GUARDAR MEMÒRIA ---
    def save_memory(content_text):
        try:
            dated_content = f"[{datetime.now().strftime('%Y-%m-%d')}] {content_text}"
            emb = get_embedding(dated_content)
            supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": dated_content,
                "embedding": emb
            }).execute()
        except Exception as e:
            st.warning(f"⚠️ No s'ha pogut guardar la memòria: {str(e)}")

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

    if st.button("💾 Guardar", type="primary", use_container_width=True):
        try:
            # 1. Guardar a la taula training_sensations
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

            # 2. Guardar a memòria RAG perquè el xat ho sàpiga
            memory_text = (
                f"Sensacions del {date.isoformat()}: "
                f"qualitat entrenament {training_quality}/10, "
                f"fatiga {fatigue_level}/10, "
                f"motivació {motivation}/10, "
                f"hores de son {sleep_hours}h, "
                f"qualitat son {sleep_quality}/10"
            )
            if notes:
                memory_text += f". Notes: {notes}"

            save_memory(memory_text)

            st.success("✅ Guardat correctament!")
            st.balloons()

        except Exception as e:
            st.error(f"Error: {e}")
