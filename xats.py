import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid

def mostrar_xat():
    # 1. Verificació de seguretat
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return
    
    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id
    
    # Inicialització de variables
    if 'conv_id' not in st.session_state:
        st.session_state.conv_id = None
    if 'msgs' not in st.session_state:
        st.session_state.msgs = []

    # --- FUNCIONS DE BASE DE DADES ---
    
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

    def load_conv(conversation_id):
        """Carrega missatges i els retorna"""
        try:
            res = supabase.table("messages")\
                .select("*")\
                .eq("conversation_id", conversation_id)\
                .order("created_at")\
                .execute()
            
            # DEBUG: Mostra si ha trobat res
            st.caption(f"📦 Carregats {len(res.data)} missatges de la BD.")
            return res.data
        except Exception as e:
            st.error(f"Error carregant missatges: {e}")
            return []

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

    def get_convs():
        try:
            return supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at").execute().data
        except:
            return []

    # --- Lògica d'Inicialització ---
    
    # Si no hi ha conversa, en crea una
    if st.session_state.conv_id is None:
        st.session_state.conv_id = create_conv()
        st.session_state.msgs = [] # Buidem la memòria temporal

    # Si la memòria temporal és buida, carrega de la BD
    # AIXÒ ÉS CLAU: Carrega l'historial cada vegada que entra
    if not st.session_state.msgs and st.session_state.conv_id:
        st.session_state.msgs = load_conv(st.session_state.conv_id)

    # --- INTERFÍCIE ---
    
    st.title("💬 Xat amb Entrenador IA")
    
    # Selector de Converses
    convs = get_convs()
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Selecciona conversa:", list(opts.keys()))
            if st.button("Carregar seleccionada"):
                st.session_state.conv_id = opts[sel]
                st.session_state.msgs = [] # Neteja per forçar recàrrega
                st.rerun()
        with col2:
            if st.button("🆕 Nova conversa"):
                st.session_state.conv_id = create_conv()
                st.session_state.msgs = []
                st.rerun()

    # Renderitzat del Xat
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300)
            st.markdown(m["content"])

    # Input
    prompt = st.chat_input("Pregunta sobre running...")
    
    # Si l'usuari escriu:
    if prompt:
        # 1. Mostrar missatge usuari
        user_msg = {"role": "user", "content": prompt}
        st.session_state.msgs.append(user_msg)
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # 2. Guardar a BD
        if st.session_state.conv_id:
            save_msg("user", prompt)

        # 3. Preparar context per a la IA (AIXÒ ÉS EL QUE FALLAVA)
        # Creem una llista NOMÉS amb rols vàlids (user/assistant)
        history_for_ai = []
        for msg in st.session_state.msgs:
            # Només agafem text i rol
            if msg["role"] in ["user", "assistant"]:
                history_for_ai.append({"role": msg["role"], "content": msg["content"]})

        # 4. Crida a la IA
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                try:
                    system_msg = {"role": "system", "content": "Ets un entrenador expert en running i trail running. Recorda tot el que s'ha dit abans en aquesta conversa. Respon en català."}
                    
                    # Envia: System + Història Completa
                    response = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=[system_msg] + history_for_ai
                    )
                    ans = response.choices[0].message.content
                    
                    # 5. Mostrar i guardar resposta
                    st.markdown(ans)
                    st.session_state.msgs.append({"role": "assistant", "content": ans})
                    if st.session_state.conv_id:
                        save_msg("assistant", ans)
                        
                except Exception as e:
                    st.error(f"Error IA: {e}")
