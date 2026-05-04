import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid

# Inicialitzar clients
def init_clients():
    return get_db(), OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])

def mostrar_xat():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return
    
    supabase, client = init_clients()
    user_id = st.session_state.user.id
    
    if 'conv_id' not in st.session_state:
        st.session_state.conv_id = None
    if 'msgs' not in st.session_state:
        st.session_state.msgs = []

    # --- FUNCIONS DE BASE DE DADES ---

    def save_memory(fact, user_id):
        """Guarda un fet important com a vector"""
        try:
            # Crear vector del fet
            emb = client.embeddings.create(input=fact, model="text-embedding-3-small").data[0].embedding
            supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": fact,
                "embedding": emb
            }).execute()
        except Exception as e:
            # No parem l'app si falla la memòria
            pass

    def get_relevant_memories(query, user_id, limit=5):
        """Busca records rellevants a la BD"""
        try:
            # 1. Crear vector de la pregunta
            query_emb = client.embeddings.create(input=query, model="text-embedding-3-small").data[0].embedding
            
            # 2. Buscar a Supabase
            res = supabase.rpc("match_memories", {
                "query_embedding": query_emb,
                "match_threshold": 0.75,
                "match_count": limit,
                "p_user_id": user_id
            }).execute()
            
            # Retornar els textos trobats
            return [row["content"] for row in res.data] if res.data else []
        except Exception as e:
            return []

    def create_conv():
        try:
            res = supabase.table("conversations").insert({
                "user_id": user_id,
                "title": "Nova conversa",
                "updated_at": datetime.now().isoformat()
            }).execute()
            return res.data[0]['id']
        except:
            return None

    def save_msg(role, content, image_url=None):
        try:
            supabase.table("messages").insert({
                "conversation_id": st.session_state.conv_id,
                "role": role,
                "content": content,
                "image_url": image_url
            }).execute()
        except:
            pass

    def load_conv(cid):
        try:
            return supabase.table("messages").select("*").eq("conversation_id", cid).order("created_at").execute().data
        except:
            return []

    # --- INICIALITZACIÓ ---
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = []
    
    # Carregar missatges recents del xat actual
    if not st.session_state.msgs:
        st.session_state.msgs = load_conv(st.session_state.conv_id)

    # --- INTERFÍCIE ---
    st.title("💬 Xat IA (Memòria Infinita)")
    st.caption("🧠 Recorda fets d'fa 1 any")
    
    # Selector de converses
    convs = supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(10).execute().data
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Carregar:", list(opts.keys()))
            if st.button("Carregar"):
                st.session_state.conv_id = opts[sel]
                st.session_state.msgs = []
                st.rerun()
        with col2:
            if st.button("🆕 Nova"):
                st.session_state.conv_id = create_conv()
                st.session_state.msgs = []
                st.rerun()
    
    st.markdown("---")
    
    # Input
    col1, col2 = st.columns([4, 1])
    with col1:
        prompt = st.chat_input("Pregunta...")
    with col2:
        uploaded_file = st.file_uploader("", type=["jpg", "png"], label_visibility="collapsed")
    
    # Mostrar xat actual
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300)
            if m.get("content"):
                st.markdown(m["content"])
    
    # --- PROCESSAR MISSATGE ---
    if prompt:
        image_url = None
        
        # Pujar imatge si cal
        if uploaded_file:
            with st.spinner("Pujant..."):
                file_ext = uploaded_file.name.split('.')[-1]
                file_name = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{file_ext}"
                supabase.storage.from_("chat-images").upload(file_name, uploaded_file.getvalue())
                image_url = supabase.storage.from_("chat-images").get_public_url(file_name)
                st.image(uploaded_file, width=300)
        
        # Guardar missatge usuari
        with st.chat_message("user"):
            if image_url: st.image(image_url, width=300)
            st.markdown(prompt)
        
        if st.session_state.conv_id:
            save_msg("user", prompt, image_url)
        
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        
        # 🧠 PAS 1: Buscar Memòries Rellevants (RAG)
        # Això busca a la BD coses relacionades amb "prompt" (ex: "cabell", "lesió")
        with st.spinner("🧠 Recordant..."):
            relevant_memories = get_relevant_memories(prompt, user_id)
        
        # 🧠 PAS 2: Guardar nous fets (Background)
        # Demanem a la IA que extregui fets nous d'aquest missatge per guardar-los
        try:
            extraction = client.chat.completions.create(
                model="qwen-turbo",
                messages=[
                    {"role": "system", "content": "Extreu fets personals de l'usuari (ex: 'Tinc el cabell roig', 'Vaig trencar el menisc'). Retorna JSON: {\"facts\": [\"fet1\"]}. Si no hi ha fets, {}."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            import json
            try:
                facts = json.loads(extraction.choices[0].message.content).get("facts", [])
                for f in facts:
                    save_memory(f, user_id)
            except:
                pass
        except:
            pass
            
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                # Construir context
                context = ""
                if relevant_memories:
                    context = "MEMÒRIA RECUPERADA (Fets passats):\n" + "\n".join([f"- {m}" for m in relevant_memories])
                
                # System Prompt
                system_msg = {
                    "role": "system", 
                    "content": f"""Ets un entrenador expert en running. 
                    {context}
                    
                    INSTRUCCIONS:
                    1. Si la 'MEMÒRIA RECUPERADA' conté informació rellevant, utilitza-la per respondre.
                    2. Si no hi ha memòria, respon amb sentit comú.
                    3. Respon en català."""
                }
                
                # Historial recent (només els últims 10 missatges per estalviar tokens)
                history = [system_msg] + st.session_state.msgs[-10:]
                
                try:
                    res = client.chat.completions.create(model="qwen-turbo", messages=history, temperature=0.7)
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    
                    if st.session_state.conv_id:
                        save_msg("assistant", ans, None)
                    
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    
                except Exception as e:
                    st.error(f"Error: {e}")
