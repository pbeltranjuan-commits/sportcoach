import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid
import json

def mostrar_xat():
    # 1. Verificació d'accés
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return
    
    # 2. Inicialitzar clients (utilitza el teu database.py existent)
    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id
    
    # 3. Estat de sessió
    if 'conv_id' not in st.session_state:
        st.session_state.conv_id = None
    if 'msgs' not in st.session_state:
        st.session_state.msgs = []

    # --- FUNCIONS INTERNES (Memòria + RAG) ---
    def save_memory(content_text):
        """Guarda un fet com a vector a long_term_memories"""
        try:
            emb = client.embeddings.create(input=content_text, model="text-embedding-3-small").data[0].embedding
            supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": content_text,
                "embedding": emb
            }).execute()
        except Exception:
            pass  # Falla silenciosa per no trencar el xat

    def get_relevant_memories(query_text, limit=5):
        """Busca a la BD els fets més semblants a la pregunta actual"""
        try:
            query_emb = client.embeddings.create(input=query_text, model="text-embedding-3-small").data[0].embedding
            res = supabase.rpc("match_memories", {
                "query_embedding": query_emb,
                "match_threshold": 0.7,
                "match_count": limit,
                "p_user_id": user_id
            }).execute()
            return [row["content"] for row in res.data] if res.data else []
        except Exception:
            return []

    # --- INICIALITZACIÓ DE CONVERSA ---
    if st.session_state.conv_id is None:
        res = supabase.table("conversations").insert({
            "user_id": user_id,
            "title": "Nova conversa",
            "updated_at": datetime.now().isoformat()
        }).execute()
        st.session_state.conv_id = res.data[0]['id']
        st.session_state.msgs = []
    
    # Carregar missatges de la conversa actual si està buida
    if not st.session_state.msgs:
        st.session_state.msgs = supabase.table("messages")\
            .select("*")\
            .eq("conversation_id", st.session_state.conv_id)\
            .order("created_at")\
            .execute().data

    # --- INTERFÍCIE ---
    st.title("💬 Xat IA")
    st.caption("🧠 Memòria activa: recorda fets d'fa mesos")
    
    # Selector de converses
    convs = supabase.table("conversations")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("updated_at", desc=True)\
        .limit(10)\
        .execute().data
        
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Carregar conversa:", list(opts.keys()))
            if st.button("Carregar seleccionada"):
                st.session_state.conv_id = opts[sel]
                st.session_state.msgs = []
                st.rerun()
        with col2:
            if st.button("🆕 Nova conversa"):
                res = supabase.table("conversations").insert({
                    "user_id": user_id,
                    "title": "Nova",
                    "updated_at": datetime.now().isoformat()
                }).execute()
                st.session_state.conv_id = res.data[0]['id']
                st.session_state.msgs = []
                st.rerun()

    st.markdown("---")
    
    # Input + Upload
    col1, col2 = st.columns([4, 1])
    with col1:
        prompt = st.chat_input("Pregunta sobre running, lesions, objectius...")
    with col2:
        uploaded_file = st.file_uploader("", type=["jpg", "jpeg", "png"], label_visibility="collapsed")

    # Renderitzar missatges existents
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300)
            st.markdown(m["content"])

    # --- PROCESSAR NOU MISSATGE ---
    if prompt:
        image_url = None
        
        # Pujar imatge si n'hi ha
        if uploaded_file:
            with st.spinner("Pujant imatge..."):
                ext = uploaded_file.name.split('.')[-1]
                fn = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("chat-images").upload(fn, uploaded_file.getvalue(), {"content-type": uploaded_file.type})
                image_url = supabase.storage.from_("chat-images").get_public_url(fn)
                st.image(uploaded_file, width=300)
        
        # 1. Guardar missatge d'usuari
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user",
            "content": prompt,
            "image_url": image_url
        }).execute()
        
        # 2. 🧠 EXTRACCIÓ AUTOMÀTICA DE FETS (Xat)
        try:
            ext_res = client.chat.completions.create(
                model="qwen-turbo",
                messages=[
                    {"role": "system", "content": "Extreu fets personals importants de l'usuari (edat, cabell, lesions, objectius, preferències, dades físiques). Retorna JSON: {\"facts\": [\"fet1\", \"fet2\"]}. Si no n'hi ha, retorna {}."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            clean_json = ext_res.choices[0].message.content.replace("```json", "").replace("```", "")
            facts = json.loads(clean_json).get("facts", [])
            for f in facts:
                save_memory(f"Usuari diu: {f}")
        except Exception:
            pass  # Si falla l'extracció, el xat continua normal

        # 3. 🧠 RAG: BUSCAR MEMÒRIES RELLEVANTS
        with st.spinner(" Consultant memòria..."):
            memories = get_relevant_memories(prompt, limit=5)
        
        # 4. Preparar context per a la IA
        context_str = ""
        if memories:
            context_str = "MEMÒRIA RECUPERADA (Fets passats):\n" + "\n".join([f"- {m}" for m in memories])
        
        system_prompt = f"""Ets un entrenador personal expert en running i trail running.
        {context_str}
        
        INSTRUCCIONS:
        1. Utilitza la 'MEMÒRIA RECUPERADA' si és rellevant per respondre.
        2. Si la memòria no conté la resposta, respon amb sentit comú tècnic.
        3. Respon sempre en català.
        """
        
        # 5. Crida a la IA
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                # Envio system + últims 8 missatges per estalviar tokens però mantenir context recent
                history = [{"role": "system", "content": system_prompt}] + st.session_state.msgs[-8:]
                try:
                    res = client.chat.completions.create(model="qwen-turbo", messages=history, temperature=0.7)
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    
                    # Guardar resposta
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    supabase.table("messages").insert({
                        "conversation_id": st.session_state.conv_id,
                        "role": "assistant",
                        "content": ans
                    }).execute()
                except Exception as e:
                    st.error(f"Error IA: {e}")
