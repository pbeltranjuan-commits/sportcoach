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

    # --- GUARDAR MEMÒRIA (SENSE VECTORS) ---
    def save_memory(content_text):
        try:
            # Guarda directament sense vector
            res = supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": content_text,
                "embedding": None  # Null per ara
            }).execute()
            st.success(f"✅ Record guardat: {content_text[:50]}...")
            return True
        except Exception as e:
            st.error(f"❌ ERROR: {str(e)}")
            return False

    # --- CERCA PER TEXT SIMPLE (ILIKE) ---
    def search_memories(query_text, limit=5):
        try:
            # Cerca paraules clau al contingut
            words = query_text.lower().split()
            results = []
            
            for word in words:
                if len(word) > 3:  # Només paraules amb sentit
                    res = supabase.table("long_term_memories")\
                        .select("*")\
                        .eq("user_id", user_id)\
                        .ilike("content", f"%{word}%")\
                        .limit(limit)\
                        .execute()
                    if res.data:
                        results.extend(res.data)
            
            # Eliminar duplicats
            unique = {r['id']: r for r in results}.values()
            
            if unique:
                st.info(f"🔍 Trobats {len(unique)} records")
                return list(unique)
            else:
                st.warning("⚠️ Cap record trobat")
                return []
        except Exception as e:
            st.error(f"❌ ERROR CERCA: {str(e)}")
            return []

    # --- INICIALITZACIÓ ---
    if st.session_state.conv_id is None:
        res = supabase.table("conversations").insert({
            "user_id": user_id, "title": "Nova conversa", "updated_at": datetime.now().isoformat()
        }).execute()
        st.session_state.conv_id = res.data[0]['id']
        st.session_state.msgs = []
    
    if not st.session_state.msgs:
        st.session_state.msgs = supabase.table("messages").select("*").eq("conversation_id", st.session_state.conv_id).order("created_at").execute().data

    # --- INTERFÍCIE ---
    st.title("💬 Xat IA (Memòria Text)")
    
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
    
    # Botó de prova
    if st.button("🧪 PROVAR MEMÒRIA"):
        save_memory("Tinc 30 anys")
        save_memory("El meu cabell és roig")
        save_memory("Vaig trencar el menisc fa un any")

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
        
        # Guardar com a record
        save_memory(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                memories = search_memories(prompt, limit=5)
                
                context = "MEMÒRIA:\n" + "\n".join([f"- {m['content']}" for m in memories]) if memories else "Cap memòria."
                
                sys_msg = {"role": "system", "content": f"Ets un entrenador de running. {context} Respon en català."}
                history = [sys_msg] + st.session_state.msgs[-8:]
                
                try:
                    res = client.chat.completions.create(model="qwen-turbo", messages=history, temperature=0.7)
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    supabase.table("messages").insert({"conversation_id": st.session_state.conv_id, "role": "assistant", "content": ans}).execute()
                except Exception as e:
                    st.error(f"❌ ERROR IA: {str(e)}")
