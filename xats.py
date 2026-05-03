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
    
    if 'conv_id' not in st.session_state:
        st.session_state.conv_id = None
    if 'msgs' not in st.session_state:
        st.session_state.msgs = []
    
    def create_conv():
        try:
            res = supabase.table("conversations").insert({
                "user_id": user_id, 
                "title": "Nova conversa", 
                "updated_at": datetime.now().isoformat()
            }).execute()
            return res.data[0]['id']
        except Exception as e:
            st.error(f"Error creant conversa: {e}")
            return None
    
    def upload_image(file):
        try:
            file_extension = file.name.split('.')[-1]
            file_name = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{file_extension}"
            supabase.storage.from_("chat-images").upload(
                file_name, 
                file.getvalue(),
                {"content-type": file.type}
            )
            public_url = supabase.storage.from_("chat-images").get_public_url(file_name)
            return public_url
        except Exception as e:
            st.error(f"Error pujant imatge: {e}")
            return None
    
    def save_msg(role, content, image_url=None):
        try:
            data = {
                "conversation_id": st.session_state.conv_id, 
                "role": role, 
                "content": content,
                "image_url": image_url
            }
            supabase.table("messages").insert(data).execute()
        except Exception as e:
            st.error(f"Error guardant: {e}")
    
    def load_conv(conversation_id):
        try:
            res = supabase.table("messages").select("*").eq(
                "conversation_id", conversation_id
            ).order("created_at").execute()
            st.info(f"📦 Carregats {len(res.data)} missatges")
            return res.data
        except Exception as e:
            st.error(f"Error carregant: {e}")
            return []
    
    def get_convs():
        try:
            res = supabase.table("conversations").select("*").eq(
                "user_id", user_id
            ).order("updated_at").execute()
            return res.data
        except Exception as e:
            return []
    
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = []
    
    if not st.session_state.msgs and st.session_state.conv_id:
        st.session_state.msgs = load_conv(st.session_state.conv_id)
    
    st.title("💬 Xat amb Entrenador IA")
    st.caption("📸 Pots adjuntar fotos")
    
    convs = get_convs()
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
                st.session_state.conv_id = create_conv()
                st.session_state.msgs = []
                st.rerun()
    
    st.markdown("---")
    
    col1, col2 = st.columns([4, 1])
    with col1:
        prompt = st.chat_input("Pregunta sobre running...")
    with col2:
        uploaded_file = st.file_uploader("", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300)
            if m.get("content"):
                st.markdown(m["content"])
    
    if prompt:
        image_url = None
        
        if uploaded_file:
            with st.spinner("Pujant imatge..."):
                image_url = upload_image(uploaded_file)
                if image_url:
                    st.image(uploaded_file, width=300)
        
        user_msg = {"role": "user", "content": prompt, "image_url": image_url}
        st.session_state.msgs.append(user_msg)
        
        with st.chat_message("user"):
            if image_url:
                st.image(image_url, width=300)
            st.markdown(prompt)
        
        if st.session_state.conv_id:
            save_msg("user", prompt, image_url)
        
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                history_for_ai = [{"role": "system", "content": "Ets un entrenador expert en running. Recorda TOT l'historial. Respon en català."}]
                
                for msg in st.session_state.msgs:
                    if msg.get("content"):
                        msg_content = msg["content"]
                        if msg.get("image_url"):
                            msg_content += " [IMATGE ADJUNTA]"
                        history_for_ai.append({"role": msg["role"], "content": msg_content})
                
                try:
                    response = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=history_for_ai,
                        temperature=0.7
                    )
                    ans = response.choices[0].message.content
                    st.markdown(ans)
                    
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    if st.session_state.conv_id:
                        save_msg("assistant", ans, None)
                        
                except Exception as e:
                    st.error(f"Error IA: {e}")
