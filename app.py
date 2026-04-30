import streamlit as st
from supabase import create_client, Client
from openai import OpenAI
from auth import signup, login, logout, get_user_profile
from database import get_db

st.set_page_config(page_title="SportCoach IA", page_icon="🏃", layout="wide")

# Inicialitzar estat
if 'user' not in st.session_state:
    st.session_state.user = None
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = None

# Si no hi ha usuari, mostrar login/registre
if st.session_state.user is None:
    st.title("🏃 SportCoach IA - El teu entrenador personal")
    st.caption("Running & Trail Running amb Intel·ligència Artificial")
    
    tab1, tab2 = st.tabs(["🔑 Iniciar Sessió", "📝 Registrar-se"])
    
    with tab1:
        st.subheader("Benvingut de nou")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Contrasenya", type="password", key="login_password")
        
        if st.button("Entrar", type="primary"):
            user, error = login(email, password)
            if user:
                st.session_state.user = user.user
                st.session_state.user_profile = get_user_profile(user.user.id)
                st.rerun()
            else:
                st.error(f"Error: {error}")
    
    with tab2:
        st.subheader("Crea un compte nou")
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Contrasenya", type="password", key="signup_password")
        new_name = st.text_input("Nom complet", key="signup_name")
        
        if st.button("Registrar-se", type="primary"):
            user, error = signup(new_email, new_password, new_name)
            if user:
                st.success("✅ Registre completat! Revisa el teu email per confirmar-lo.")
                st.info("📧 Un cop confirmis l'email, podràs iniciar sessió.")
            else:
                st.error(f"Error: {error}")

else:
    # Usuari autenticat
    st.sidebar.title(f"👤 {st.session_state.user_profile.get('full_name', 'Usuari') if st.session_state.user_profile else 'Usuari'}")
    st.sidebar.write(f"📧 {st.session_state.user.email}")
    
    if st.sidebar.button("🚪 Tancar Sessió"):
        logout()
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.info("💡 Utilitza el menú lateral per navegar")
    
    # Pàgina principal
    st.title(f"Benvingut, {st.session_state.user_profile.get('full_name', 'Corredor') if st.session_state.user_profile else 'Corredor'}! 🏃")
    st.markdown("### El teu entrenador personal IA et espera")
    
    st.markdown("---")
    st.info("👈 Aviat tindras aquí el teu dashboard")
