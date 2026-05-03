import streamlit as st
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
    user_name = st.session_state.user_profile.get('full_name', 'Corredor') if st.session_state.user_profile else st.session_state.user.email.split('@')[0]
    
    st.sidebar.title(f"👤 {user_name}")
    st.sidebar.write(f"📧 {st.session_state.user.email}")
    
    if st.sidebar.button("🚪 Tancar Sessió"):
        logout()
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # Menu de navegació
    menu = st.sidebar.radio(
        "Navegació",
        ["🏠 Inici", "💬 Xat IA", "💭 Sensacions"],
        index=0
    )
    
    # ==================== PÀGINA INICI ====================
    if menu == "🏠 Inici":
        st.title(f"Benvingut, {user_name}! 🏃")
        st.markdown("### El teu entrenador personal IA")
        st.info("Selecciona una opció al menú lateral per començar")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Converses", "0")
        with col2:
            st.metric("Mètriques guardades", "0")
        with col3:
            st.metric("Dies entrenant", "0")
    
    # ==================== PÀGINA XAT ====================
    elif menu == "💬 Xat IA":
        # Importar el mòdul de xat
        try:
            exec(open('xats.py').read())
        except Exception as e:
            st.error(f"Error carregant el xat: {e}")
            st.info("El mòdul de xat estarà disponible aviat")
    
    # ==================== PÀGINA SENSACIONS ====================
    elif menu == "💭 Sensacions":
        # Importar el mòdul de sensacions
        try:
            exec(open('Sensacions.py').read())
        except Exception as e:
            st.error(f"Error carregant sensacions: {e}")
            st.info("El mòdul de sensacions estarà disponible aviat")
