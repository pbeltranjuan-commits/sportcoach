import streamlit as st
from database import get_db

def signup(email, password, full_name):
    supabase = get_db()
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"full_name": full_name}
            }
        })
        return response, None
    except Exception as e:
        return None, str(e)

def login(email, password):
    supabase = get_db()
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return response, None
    except Exception as e:
        return None, str(e)

def logout():
    supabase = get_db()
    supabase.auth.sign_out()
    st.session_state.user = None
    st.session_state.user_profile = None

def get_user_profile(user_id):
    supabase = get_db()
    response = supabase.table("profiles").select("*").eq("id", user_id).execute()
    return response.data[0] if response.data else None
