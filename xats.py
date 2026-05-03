import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import base64

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
        """Puja imatge a Supabase Storage"""
        try:
            # Nom únic per la imatge
            import uuid
            file_extension = file.name.split('.')[-1]
            file_name = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{file_extension}"
            
            # Puja a Supabase Storage
            supabase.storage.from_("chat-images").upload(
                file_name, 
                file.getvalue(),
                {"content-type": file.type}
            )
            
            # Obté URL pública
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
                "image_url": image_url,
                "has_image": image_url is not None
            }
            supabase.table("messages").insert(data).execute()
        except Exception as e:
            st.error(f"Error guardant missatge: {e}")
    
    def load_conv():
        try:
            res = supabase.table("messages").select("*").eq(
                "conversation_id", st.session_state.conv_id
            ).order("created_at").execute()
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
            st.error(f"Error llistant converses: {e}")
            return []
    
    # Inicialitzar
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = []
    
    if not st.session_state.msgs and st.session_state.conv_id:
        st.session_state.msgs = load_conv()
    
    st.title("💬 Xat amb Entrenador IA")
    st.caption("Pots adjuntar fotos de la teva tècnica, lesions, etc.")
    
    # Selector de converses
    convs = get_convs()
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
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
    
    # Input amb imatge
    st.markdown("---")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        prompt = st.chat_input("Pregunta sobre running...")
    
    with col2:
        uploaded_file = st.file_uploader("", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    
    # Mostrar missatges
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("has_image") and m.get("image_url"):
                st.image(m["image_url"], width=300)
            if m.get("content"):
                st.markdown(m["content"])
    
    # Processar missatge
    if prompt:
        image_url = None
        
        # Si hi ha imatge, pujar-la
        if uploaded_file:
            with st.spinner("Pujant imatge..."):
                image_url = upload_image(uploaded_file)
                if image_url:
                    st.image(uploaded_file, width=300)
        
        # Guardar missatge usuari
        st.session_state.msgs.append({
            "role": "user", 
            "content": prompt,
            "has_image": image_url is not None,
            "image_url": image_url
        })
        
        if st.session_state.conv_id:
            save_msg("user", prompt, image_url)
        
        # Resposta IA
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                # Preparar missatges per a la IA
                api_msgs = [{"role": "system", "content": "Ets un entrenador expert en running i trail running. Respon en català. Si l'usuari adjunta una foto, analitza-la i dona consells sobre tècnica, postura o equipament."}]
                
                # Afegir historial (només text)
                for m in st.session_state.msgs:
                    if m.get("content"):
                        api_msgs.append({"role": m["role"], "content": m["content"]})
                
                # Si hi ha imatge, afegir context
                if image_url:
                    api_msgs.append({
                        "role": "user", 
                        "content": f"{prompt} [IMATGE ADJUNTA: L'usuari ha compartit una foto]"
                    })
                else:
                    api_msgs.append({"role": "user", "content": prompt})
                
                res = client.chat.completions.create(
                    model="qwen-turbo", 
                    messages=api_msgs, 
                    temperature=0.7
                )
                ans = res.choices[0].message.content
                st.markdown(ans)
        
        # Guardar resposta
        if st.session_state.conv_id:
            save_msg("assistant", ans, None)
        
        st.session_state.msgs.append({"role": "assistant", "content": ans, "has_image": False, "image_url": None})
