import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid


# --- EMBEDDINGS LOCALS ---
@st.cache_resource
def load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def get_embedding(text):
    model = load_embedding_model()
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()


# --- CONFIGURACIÓ DELS AGENTS ---
AGENTS = {
    "🏃 Entrenador": {
        "id": "entrenador",
        "emoji": "🏃",
        "color": "#FF4B4B",
        "descripció": "Planifica entrenos i fa pronòstics de rendiment",
        "system_prompt": (
            "Ets un entrenador personal expert en running i atletisme. "
            "El teu rol és planificar entrenaments personalitzats, analitzar el rendiment, "
            "fer pronòstics de temps i marques, i ajustar la càrrega d'entrenament. "
            "Utilitza les dades de l'historial per adaptar els plans. "
            "Sempre proposa entrenamens concrets amb distàncies, ritmes i dies. "
            "Respon en català."
        )
    },
    "🥗 Nutricionista": {
        "id": "nutricionista",
        "emoji": "🥗",
        "color": "#00CC88",
        "descripció": "Dieta, alimentació i nutrició esportiva",
        "system_prompt": (
            "Ets un nutricionista esportiu especialitzat en runners. "
            "El teu rol és recomanar dietes, plans d'alimentació, hidratació i suplements "
            "adaptats a l'entrenament i objectius de l'usuari. "
            "Utilitza les dades de l'historial (pes, objectius, sensacions) per personalitzar. "
            "Sempre dona consells pràctics i menús concrets. "
            "Respon en català."
        )
    },
    "🧠 Psicòleg": {
        "id": "psicolog",
        "emoji": "🧠",
        "color": "#7C3AED",
        "descripció": "Motivació, mentalitat i benestar emocional",
        "system_prompt": (
            "Ets un psicòleg esportiu especialitzat en runners. "
            "El teu rol és treballar la motivació, gestionar el bloqueig mental, "
            "la por a les lesions, l'ansietat de competició i el benestar emocional. "
            "Utilitza les dades de l'historial per detectar patrons emocionals. "
            "Si detectes cansament, desmotivació o estrès recurrent, menciona-ho. "
            "Respon amb empatia i en català."
        )
    },
    "📊 Analista": {
        "id": "analista",
        "emoji": "📊",
        "color": "#0099FF",
        "descripció": "Analitza les teves dades i fa pronòstics",
        "system_prompt": (
            "Ets un analista de dades esportives especialitzat en running. "
            "El teu rol és analitzar les dades de l'usuari (sensacions, fatiga, son, motivació, "
            "qualitat d'entrenament) i extreure patrons, tendències i pronòstics. "
            "Quan tinguis dades suficients, fes prediccions concretes: "
            "'Si continues així, en X setmanes podràs...'. "
            "Identifica correlacions: 'Quan dorms menys de 7h, la teva fatiga puja un X%'. "
            "Respon amb dades concretes i en català."
        )
    }
}


def mostrar_agents():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return

    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id

    # Inicialitzar estat
    if 'agent_seleccionat' not in st.session_state:
        st.session_state.agent_seleccionat = "🏃 Entrenador"
    if 'agent_msgs' not in st.session_state:
        st.session_state.agent_msgs = {}
    if 'agent_conv_ids' not in st.session_state:
        st.session_state.agent_conv_ids = {}

    # --- GUARDAR MEMÒRIA (compartida entre agents) ---
    def save_memory(content_text):
        try:
            dated_content = f"[{datetime.now().strftime('%Y-%m-%d')}] {content_text}"
            emb = get_embedding(dated_content)
            supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": dated_content,
                "embedding": emb
            }).execute()
            return True
        except Exception as e:
            return False

    # --- CERCA RAG (compartida entre agents) ---
    def get_relevant_memories(query_text, limit=6):
        try:
            query_emb = get_embedding(query_text)
            res = supabase.rpc("match_memories", {
                "query_embedding": query_emb,
                "match_threshold": 0.3,
                "match_count": limit,
                "p_user_id": user_id
            }).execute()
            if res.data:
                return [row["content"] for row in res.data]
            return []
        except Exception:
            return []

    # --- OBTENIR DADES DE SENSACIONS ---
    def get_sensacions_context():
        try:
            res = supabase.table("training_sensations") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("date", desc=True) \
                .limit(10) \
                .execute()
            if not res.data:
                return ""
            lines = ["DADES DE SENSACIONS RECENTS:"]
            for s in res.data:
                lines.append(
                    f"- {s['date']}: fatiga {s.get('fatigue_level','?')}/10, "
                    f"motivació {s.get('motivation','?')}/10, "
                    f"son {s.get('sleep_hours','?')}h (qualitat {s.get('sleep_quality','?')}/10), "
                    f"entrenament {s.get('training_quality','?')}/10"
                    + (f", notes: {s['notes']}" if s.get('notes') else "")
                )
            return "\n".join(lines)
        except Exception:
            return ""

    # --- INICIALITZAR CONVERSA PER AGENT ---
    def get_or_create_conv(agent_id):
        if agent_id not in st.session_state.agent_conv_ids:
            res = supabase.table("conversations").insert({
                "user_id": user_id,
                "title": f"Agent {agent_id}",
                "updated_at": datetime.now().isoformat()
            }).execute()
            st.session_state.agent_conv_ids[agent_id] = res.data[0]['id']
        if agent_id not in st.session_state.agent_msgs:
            st.session_state.agent_msgs[agent_id] = []
        return st.session_state.agent_conv_ids[agent_id]

    # --- INTERFÍCIE ---
    st.title("🤖 Agents IA")
    st.caption("Experts especialitzats que comparteixen la teva memòria")

    # Selector d'agents
    cols = st.columns(4)
    for i, (nom, agent) in enumerate(AGENTS.items()):
        with cols[i]:
            is_selected = st.session_state.agent_seleccionat == nom
            if st.button(
                f"{agent['emoji']}\n**{nom.split(' ', 1)[1]}**",
                use_container_width=True,
                type="primary" if is_selected else "secondary"
            ):
                st.session_state.agent_seleccionat = nom
                st.rerun()

    st.markdown("---")

    # Agent actiu
    agent_nom = st.session_state.agent_seleccionat
    agent = AGENTS[agent_nom]
    agent_id = agent["id"]
    conv_id = get_or_create_conv(agent_id)
    msgs = st.session_state.agent_msgs[agent_id]

    # Info de l'agent
    st.markdown(f"### {agent_nom}")
    st.caption(agent["descripció"])

    # Botó nova conversa
    col1, col2 = st.columns([5, 1])
    with col2:
        if st.button("🆕 Nova", use_container_width=True):
            res = supabase.table("conversations").insert({
                "user_id": user_id,
                "title": f"Agent {agent_id}",
                "updated_at": datetime.now().isoformat()
            }).execute()
            st.session_state.agent_conv_ids[agent_id] = res.data[0]['id']
            st.session_state.agent_msgs[agent_id] = []
            st.rerun()

    st.markdown("---")

    # Mostrar historial
    for m in msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Input
    prompt = st.chat_input(f"Parla amb {agent_nom}...")

    if prompt:
        msgs.append({"role": "user", "content": prompt})
        supabase.table("messages").insert({
            "conversation_id": conv_id,
            "role": "user",
            "content": prompt
        }).execute()

        save_memory(prompt)

        with st.chat_message("assistant"):
            with st.spinner(f"{agent['emoji']} Pensant..."):
                # Context: memòria RAG + sensacions
                memories = get_relevant_memories(prompt, limit=6)
                sensacions = get_sensacions_context()

                context_parts = []
                if memories:
                    context_parts.append(
                        "HISTORIAL DE L'USUARI:\n" + "\n".join([f"- {m}" for m in memories])
                    )
                if sensacions:
                    context_parts.append(sensacions)

                context = "\n\n".join(context_parts) if context_parts else "No hi ha historial previ."

                sys_msg = {
                    "role": "system",
                    "content": (
                        f"{agent['system_prompt']}\n\n"
                        f"CONTEXT DE L'USUARI:\n{context}"
                    )
                }

                history = [sys_msg] + [
                    {"role": m["role"], "content": m["content"]}
                    for m in msgs[-8:]
                ]

                try:
                    res = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=history,
                        temperature=0.7
                    )
                    ans = res.choices[0].message.content
                    st.markdown(ans)

                    msgs.append({"role": "assistant", "content": ans})
                    supabase.table("messages").insert({
                        "conversation_id": conv_id,
                        "role": "assistant",
                        "content": ans
                    }).execute()

                    save_memory(f"Agent {agent_nom}: {ans[:200]}")

                except Exception as e:
                    st.error(f"❌ ERROR: {str(e)}")
