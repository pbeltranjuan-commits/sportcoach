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
    
    # === FUNCIONS ===
    
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
        """Puja imatge a Supabase Storage"""
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
            st.success("✅ Missatge guardat a SQL")
        except Exception as e:
            st.error(f"Error guardant: {e}")
    
    def load_conv(conversation_id):
        """Carrega missatges de la BD"""
        try:
            res = supabase.table("messages")\
                .select("*")\
                .eq("conversation_id", conversation_id)\
                .order("created_at")\
                .execute()
            
            st.info(f"📦 Carregats {len(res.data)} missatges de la base de dades")
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
            st.error(f"Error llistant: {e}")
            return []
    
    # === INICIALITZACIÓ ===
    
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = []
    
    # Carregar missatges si estan buits
    if not st.session_state.msgs and st.session_state.conv_id:
        st.session_state.msgs = load_conv(st.session_state.conv_id)
    
    # === INTERFÍCIE ===
    
    st.title("💬 Xat amb Entrenador IA")
    st.caption("📸 Pots adjuntar fotos de la teva tècnica o lesions")
    
    # Selector de converses
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
    
    # Input amb upload de fitxers
    col1, col2 = st.columns([4, 1])
    with col1:
        prompt = st.chat_input("Pregunta sobre running...")
    with col2:
        uploaded_file = st.file_uploader("", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    
    # Mostrar missatges existents
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300, caption="📷 Imatge adjunta")
            if m.get("content"):
                st.markdown(m["content"])
    
    # Processar nou missatge
    if prompt:
