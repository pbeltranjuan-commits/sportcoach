import streamlit as st
from supabase import create_client
from openai import OpenAI

st.set_page_config(page_title="SportCoach", page_icon="🏃")

@st.cache_resource
def init():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]), OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])

supabase, client = init()

if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏃 SportCoach IA")
    email = st.text_input("Email")
    pwd = st.text_input("Password", type="password")
    
    if st.button("Entrar"):
        try:
            u = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
            st.session_state.user = u.user
            st.rerun()
        except Exception as e:
            st.error(e)
else:
    st.sidebar.write(f"👤 {st.session_state.user.email}")
    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()
    
    menu = st.sidebar.radio("Menu", ["Inici", "Xat"])
    
    if menu == "Inici":
        st.title("Benvingut!")
    elif menu == "Xat":
        st.title("💬 Xat")
        if "msgs" not in st.session_state:
            st.session_state.msgs = []
        
        for m in st.session_state.msgs:
            with st.chat_message(m["role"]):
                st.write(m["content"])
        
        if prompt := st.chat_input("Pregunta..."):
            st.session_state.msgs.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)
            
            with st.chat_message("assistant"):
                res = client.chat.completions.create(model="qwen-turbo", messages=[{"role": "user", "content": prompt}])
                ans = res.choices[0].message.content
