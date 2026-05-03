import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime

def mostrar_xat():
    """Funció principal del mòdul de xat"""
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return
    
    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id
    
    if 'conv_id' not in st.session_state:
        st.session_state.conv_id = None
    if 'msgs' not in st.session_state:
        st.session_state.msgs = []
    
    def create_conv():
        res = supabase.table("conversations").insert({
            "user_id": user_id, 
            "title": "Nova conversa", 
            "updated_at": datetime.now().isoformat()
        }).execute()
        return res.data[0]['id']
    
    def save_msg(role, content):
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id, 
            "role": role, 
            "content": content
        }).execute()
        supabase.table("conversations").update({
            "updated_at": datetime.now().isoformat()
        }).eq("id", st.session_state.conv_id).execute()
    
    def load_conv():
        res = supabase.table("messages").select("*").eq(
            "conversation_id", st.session_state.conv_id
        ).order("created_at", asc=True).execute()
        return [{"role": m["role"], "content": m["content"]} for m in res.data]
    
    def get_convs():
        res = supabase.table("conversations").select("*").eq(
            "user_id", user_id
        ).order("updated_at", desc=True).limit(10).execute()
        return res.data
    
    # Inicialitzar
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = []
    if not st.session_state.msgs:
        st.session_state.msgs = load_conv()
    
    st.title("💬 Xat amb Entrenador IA")
    
    # Selector
    col1, col2 = st.columns([3, 1])
    with col1:
        convs = get_convs()
        if convs:
            opts = {c['title'] or f"Conv {i}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Carregar conversa:", list(opts.keys()))
            if st.button("Carregar"):
                st.session_state.conv_id = opts[sel]
                st.session_state.msgs = []
                st.rerun()
    with col2:
        if st.button("🆕 Nova"):
            st.session_state.conv_id = create_conv()
            st.session_state.msgs = []
            st.rerun()
    
    # Xat
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    
    if prompt := st.chat_input("Pregunta sobre running..."):
        st.session_state.msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        save_msg("user", prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                api_msgs = [{"role": "system", "content": "Ets un entrenador expert en running i trail running. Respon en català."}] + st.session_state.msgs
                res = client.chat.completions.create(model="qwen-turbo", messages=api_msgs, temperature=0.7)
                ans = res.choices[0].message.content
                st.markdown(ans)
        save_msg("assistant", ans)
        st.session_state.msgs.append({"role": "assistant", "content": ans})
