import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid

def mostrar_xat():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return
    
    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id
    
    if 'conv_id' not in st.session_state: st.session_state.conv_id = None
    if 'msgs' not in st.session_state: st.session_state.msgs = []

    # --- FUNCIÓ DE GUARDAT (AMB ERRORS VISIBLES) ---
    def save_memory(content_text):
        try:
            # 1. Crear vector
            emb_res = client.embeddings.create(input=content_text, model="text-embedding-3-small")
            emb = emb_res.data[0].embedding
            
            # 2. Guardar a Supabase
            res = supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": content_text,
                "embedding": emb
            }).execute()
            
            st.success(f"✅ Memòria guardada: {content_text[:50]}...")
            return True
        except Exception as e:
            st.error(f"❌ ERROR GUARDANT MEMÒRIA: {str(e)}")
            return False

    # --- FUNCIÓ DE CERCA (RAG) ---
    def get_relevant_memories(query_text, limit=3):
        try:
            query_emb = client.embeddings.create(input=query_text, model="text-embedding-3-small").data[0].embedding
            res = supabase.rpc("match_memories", {
                "query_embedding": query_emb,
                "match_threshold": 0.5,  # Baixa per assegurar que troba alguna cosa
                "match_count": limit,
                "p_user_id": user_id
            }).execute()
            
            if res.data:
                st.info(f"🔍 Trobats {len(res.data)} records: {[r['content'][:30] for r in res.data]}")
                return [row["content"] for row in res.data]
            else:
                st.warning("⚠️ No s'han trobat records a la BD")
                return []
        except Exception as e:
            st.error(f"❌ ERROR CERCA RAG: {str(e)}")
            return []

    # --- INICIALITZACIÓ CONVERSA ---
    if st.session_state.conv_id is None:
        res = supabase.table("conversations").insert({
            "user_id": user_id, "title": "Nova conversa", "updated_at": datetime.now().isoformat()
        }).execute()
        st.session_state.conv_id = res.data[0]['id']
        st.session_state.msgs = []
    
    if not st.session_state.msgs:
        st.session_state.msgs = supabase.table("messages").select("*").eq("conversation_id", st.session_state.conv_id).order("created_at").execute().data

    # --- INTERFÍCIE ---
    st.title("💬 Xat IA (Debug Actiu)")
    st.caption(" Memòria: errors visibles + prova manual")
    
    # Selector
    convs = supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(10).execute().data
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Carregar:", list(opts.keys()))
            if st.button("Carregar"): st.session_state.conv_id = opts[sel]; st.session_state.msgs = []; st.rerun()
        with col2:
            if st.button("🆕 Nova"): 
                res = supabase.table("conversations").insert({"user_id": user_id, "title": "Nova", "updated_at": datetime.now().isoformat()}).execute()
                st.session_state.conv_id = res.data[0]['id']; st.session_state.msgs = []; st.rerun()

    st.markdown("---")
    
    # Botó de prova manual (CLAU)
    if st.button("🧪 PROVAR MEMÒRIA MANUALMENT"):
        test_facts = ["Tinc 30 anys", "El meu cabell és roig", "Vaig trencar el menisc fa un any"]
        for f in test_facts:
            save_memory(f)
        st.info("Espera 2 segons i pregunta 'Quants anys tinc?' a dalt 👆")

    col1, col2 = st.columns([4, 1])
    with col1: prompt = st.chat_input("Pregunta...")
    with col2: uploaded_file = st.file_uploader("", type=["jpg", "png"], label_visibility="collapsed")

    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"): st.image(m["image_url"], width=300)
            st.markdown(m["content"])

    if prompt:
        image_url = None
        if uploaded_file:
            with st.spinner("Pujant..."):
                ext = uploaded_file.name.split('.')[-1]
                fn = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("chat-images").upload(fn, uploaded_file.getvalue())
                image_url = supabase.storage.from_("chat-images").get_public_url(fn)
        
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({"conversation_id": st.session_state.conv_id, "role": "user", "content": prompt, "image_url": image_url}).execute()
        
        # ✅ GUARDAR AUTOMÀTIC (Sense JSON complex, directe)
        save_memory(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Consultant memòria i pensant..."):
                memories = get_relevant_memories(prompt, limit=5)
                
                context = "MEMÒRIA:\n" + "\n".join([f"- {m}" for m in memories]) if memories else "Cap memòria trobada."
                
                sys_msg = {"role": "system", "content": f"Ets un entrenador de running. {context} Respon en català. Si la memòria diu alguna dada, utilitza-la."}
                history = [sys_msg] + st.session_state.msgs[-8:]
                
                try:
                    res = client.chat.completions.create(model="qwen-turbo", messages=history, temperature=0.7)
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    supabase.table("messages").insert({"conversation_id": st.session_state.conv_id, "role": "assistant", "content": ans}).execute()
                except Exception as e:
                    st.error(f"❌ ERROR IA: {str(e)}")
