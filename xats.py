import streamlit as st
from supabase import create_client
from openai import OpenAI
from datetime import datetime

st.set_page_config(page_title="Xat IA", page_icon="💬")

# Verificar login
if 'user' not in st.session_state or st.session_state.user is None:
    st.warning("🔒 Has d'iniciar sessió")
    st.stop()

# Inicialitzar clients
@st.cache_resource
def init_clients():
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    return supabase, client

supabase, client = init_clients()
user_id = st.session_state.user.id

# Inicialitzar estat
if 'current_conversation_id' not in st.session_state:
    st.session_state.current_conversation_id = None
if 'messages' not in st.session_state:
    st.session_state.messages = []

# Funcions
def create_conversation(user_id, title="Nova conversa"):
    data = {"user_id": user_id, "title": title, "updated_at": datetime.now().isoformat()}
    response = supabase.table("conversations").insert(data).execute()
    return response.data[0]['id']

def save_message(conversation_id, role, content):
    data = {"conversation_id": conversation_id, "role": role, "content": content}
    supabase.table("messages").insert(data).execute()
    supabase.table("conversations").update({"updated_at": datetime.now().isoformat()}).eq("id", conversation_id).execute()

def load_conversation(conversation_id):
    response = supabase.table("messages").select("*").eq("conversation_id", conversation_id).order("created_at", asc=True).execute()
    return response.data

def get_user_conversations(user_id):
    response = supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(10).execute()
    return response.data

# ==================== INTERFÍCIE ====================
st.title("💬 Xat amb el teu Entrenador IA")

# Crear/carregar conversa
if st.session_state.current_conversation_id is None:
    st.session_state.current_conversation_id = create_conversation(user_id)
    st.session_state.messages = []
    st.success("✅ Nova conversa creada!")
else:
    if not st.session_state.messages:
        messages_db = load_conversation(st.session_state.current_conversation_id)
        st.session_state.messages = [{"role": m["role"], "content": m["content"]} for m in messages_db]

# Selector de conversa
col1, col2 = st.columns([3, 1])
with col1:
    conversations = get_user_conversations(user_id)
    if conversations:
        conv_options = {c['title'] or f"Conversa {i+1}": c['id'] for i, c in enumerate(conversations)}
        selected_title = st.selectbox("Carregar conversa:", list(conv_options.keys()))
        if st.button("Carregar"):
            st.session_state.current_conversation_id = conv_options[selected_title]
            st.session_state.messages = []
            st.rerun()

with col2:
    if st.button(" Nova conversa"):
        st.session_state.current_conversation_id = create_conversation(user_id)
        st.session_state.messages = []
        st.rerun()

# Mostrar missatges
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
if prompt := st.chat_input("Com puc millorar el meu running?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    save_message(st.session_state.current_conversation_id, "user", prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Pensant..."):
            system_prompt = "Ets un entrenador personal expert en running i trail running. Respon en català."
            api_messages = [{"role": "system", "content": system_prompt}] + st.session_state.messages
            
            response = client.chat.completions.create(
                model="qwen-turbo",
                messages=api_messages,
                temperature=0.7
            )
            full_response = response.choices[0].message.content
            st.markdown(full_response)
    
    save_message(st.session_state.current_conversation_id, "assistant", full_response)
    st.session_state.messages.append({"role": "assistant", "content": full_response})
