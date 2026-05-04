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
            st.error(f"Error: {e}")
            return None
    
    def upload_image(file):
        try:
            file_ext = file.name.split('.')[-1]
            file_name = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{file_ext}"
            supabase.storage.from_("chat-images").upload(file_name, file.getvalue(), {"content-type": file.type})
            return supabase.storage.from_("chat-images").get_public_url(file_name)
        except Exception as e:
            st.error(f"Error pujant: {e}")
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
    
    def load_all_user_messages():
        """CARREGA TOTS ELS MISSATGES DE L'USUARI (de totes les converses)"""
        try:
            # 1. Obtenir totes les converses de l'usuari
            convs_res = supabase.table("conversations").select("id").eq("user_id", user_id).execute()
            conv_ids = [c['id'] for c in convs_res.data]
            
            if not conv_ids:
                return []
            
            # 2. Carregar tots els missatges de totes les converses
            messages_res = supabase.table("messages").select("*").in_("conversation_id", conv_ids).order("created_at").execute()
            
            st.caption(f"📚 Carregats {len(messages_res.data)} missatges de {len(conv_ids)} converses")
            return messages_res.data
        except Exception as e:
            st.error(f"Error carregant: {e}")
            return []
    
    def load_conv(cid):
        """Carrega missatges d'una conversa específica (per mostrar)"""
        try:
            res = supabase.table("messages").select("*").eq("conversation_id", cid).order("created_at").execute()
            return res.data
        except Exception as e:
            st.error(f"Error: {e}")
            return []
    
    def get_convs():
        try:
            return supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(10).execute().data
        except:
            return []
    
    # Inicialitzar
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = []
    
    # CARREGAR TOTS ELS MISSATGES DE L'USUARI (memòria global)
    all_messages = load_all_user_messages()
    
    # Interfície
    st.title("💬 Xat IA amb Memòria Global")
    st.caption(f"🧠 Recorda {len(all_messages)} missatges de totes les converses")
    
    # Selector de conversa (només per organitzar)
    convs = get_convs()
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1} ({c['updated_at'][:10]})": c['id'] for i, c in enumerate(convs)}
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
        prompt = st.chat_input("Pregunta...")
    with col2:
        uploaded_file = st.file_uploader("", type=["jpg", "png"], label_visibility="collapsed")
    
    # Mostrar missatges de la conversa actual
    current_conv_msgs = load_conv(st.session_state.conv_id) if st.session_state.conv_id else []
    st.session_state.msgs = current_conv_msgs
    
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300)
            if m.get("content"):
                st.markdown(m["content"])
    
    # Processar
    if prompt:
        image_url = None
        
        if uploaded_file:
            with st.spinner("Pujant..."):
                image_url = upload_image(uploaded_file)
                if image_url:
                    st.image(uploaded_file, width=300)
        
        # Guardar missatge usuari
        with st.chat_message("user"):
            if image_url:
                st.image(image_url, width=300)
            st.markdown(prompt)
        
        if st.session_state.conv_id:
            save_msg("user", prompt, image_url)
        
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                # CARREGAR TOTS ELS MISSATGES ACTUALITZATS
                import time
                time.sleep(0.3)
                all_messages = load_all_user_messages()
                
                st.info(f"🧠 Memòria global: {len(all_messages)} missatges")
                
                # Construir historial per a la IA amb TOTS els missatges
                history_for_ai = [{"role": "system", "content": "Ets un entrenador expert en running i trail running. Recorda TOTA la informació de totes les converses anteriors d'aquest usuari (lesions, preferències, objectius, color de cabell, etc.). Respon en català de forma tècnica."}]
                
                for msg in all_messages:
                    content = msg.get("content", "")
                    if content:
                        if msg.get("image_url"):
                            content += " [IMATGE]"
                        history_for_ai.append({
                            "role": msg.get("role", "user"),
                            "content": content
                        })
                
                st.info(f"📤 Enviats {len(history_for_ai)-1} missatges a la IA")
                
                try:
                    res = client.chat.completions.create(model="qwen-turbo", messages=history_for_ai, temperature=0.7)
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    
                    if st.session_state.conv_id:
                        save_msg("assistant", ans, None)
                    
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    
                except Exception as e:
                    st.error(f"Error IA: {e}")
