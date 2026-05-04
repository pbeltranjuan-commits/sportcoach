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
            st.success(f"✅ Conversa creada: {res.data[0]['id'][:8]}...")
            return res.data[0]['id']
        except Exception as e:
            st.error(f"Error creant conversa: {e}")
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
            res = supabase.table("messages").insert(data).execute()
            st.success(f"✅ Missatge {role} guardat a SQL")
            return res
        except Exception as e:
            st.error(f"❌ Error guardant: {e}")
            return None
    
    def load_conv(cid):
        try:
            st.info(f" Carregant missatges de: {cid[:8] if cid else 'None'}...")
            res = supabase.table("messages").select("*").eq("conversation_id", cid).order("created_at").execute()
            st.info(f"📦 Trobats {len(res.data)} missatges a la BD")
            if res.data:
                for i, msg in enumerate(res.data):
                    st.caption(f"{i+1}. {msg['role']}: {msg['content'][:50]}...")
            return res.data
        except Exception as e:
            st.error(f"❌ Error carregant: {e}")
            return []
    
    def get_convs():
        try:
            res = supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at").execute()
            st.caption(f"💬 {len(res.data)} converses trobades")
            return res.data
        except Exception as e:
            st.error(f"Error llistant: {e}")
            return []
    
    # Inicialitzar
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = []
    
    # CARREGAR DE LA BD
    st.markdown("---")
    st.subheader("🔍 Debug - Carregant dades...")
    db_msgs = load_conv(st.session_state.conv_id)
    
    if db_msgs and not st.session_state.msgs:
        st.session_state.msgs = db_msgs
        st.success(f"✅ Carregats {len(db_msgs)} missatges a memòria")
    
    st.markdown("---")
    
    # Interfície
    st.title("💬 Xat IA")
    st.caption("📸 Pots adjuntar fotos")
    
    # Mostrar estadístiques
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Missatges en memòria", len(st.session_state.msgs))
    with col2:
        st.metric("Conversa actual", st.session_state.conv_id[:8] if st.session_state.conv_id else "Cap")
    with col3:
        convs = get_convs()
        st.metric("Total converses", len(convs) if convs else 0)
    
    convs = get_convs()
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Carregar:", list(opts.keys()))
            if st.button("Carregar seleccionada"):
                st.session_state.conv_id = opts[sel]
                st.session_state.msgs = []
                st.rerun()
        with col2:
            if st.button("🆕 Nova"):
                st.session_state.conv_id = create_conv()
                st.session_state.msgs = []
                st.rerun()
    
    st.markdown("---")
    
    col1, col2 = st.columns([4, 1])
    with col1:
        prompt = st.chat_input("Pregunta...")
    with col2:
        uploaded_file = st.file_uploader("", type=["jpg", "png"], label_visibility="collapsed")
    
    # Mostrar missatges
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
        
        user_msg = {"role": "user", "content": prompt, "image_url": image_url}
        st.session_state.msgs.append(user_msg)
        
        with st.chat_message("user"):
            if image_url:
                st.image(image_url, width=300)
            st.markdown(prompt)
        
        # GUARDAR A SQL
        if st.session_state.conv_id:
            save_msg("user", prompt, image_url)
            # Espera petita per assegurar que s'ha guardat
            import time
            time.sleep(0.5)
        
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                # CARREGAR HISTORIAL ACTUALITZAT
                current_history = load_conv(st.session_state.conv_id)
                
                st.info(f"📋 Enviats {len(current_history)} missatges a la IA")
                
                history_for_ai = [{"role": "system", "content": "Ets un entrenador personal expert en running i trail running. TOTS els missatges es guarden a SQL i pots recordar converses anteriors. Respon en català."}]
                
                for msg in current_history:
                    if msg.get("content"):
                        txt = msg["content"]
                        if msg.get("image_url"):
                            txt += " [IMATGE]"
                        history_for_ai.append({"role": msg["role"], "content": txt})
                
                try:
                    res = client.chat.completions.create(model="qwen-turbo", messages=history_for_ai, temperature=0.7)
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    if st.session_state.conv_id:
                        save_msg("assistant", ans, None)
                except Exception as e:
                    st.error(f"Error IA: {e}")
