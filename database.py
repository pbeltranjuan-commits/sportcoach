from supabase import create_client, Client
import streamlit as st

@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def get_db():
    if 'supabase' not in st.session_state:
        st.session_state.supabase = init_supabase()
    return st.session_state.supabase