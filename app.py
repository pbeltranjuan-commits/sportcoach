import streamlit as st

st.set_page_config(page_title="SportCoach IA", page_icon="🏃", layout="wide")

try:
    from auth import signup, login, logout, get_user_profile
    from database import get_db
    import xats
    import Sensacions
except Exception as e:
    st.error(f"❌ Error carregant mòduls: {e}")
    st.stop()

if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏃 SportCoach IA")
    st.write("Inicia sessió per continuar...")
    
    tab1, tab2 = st.tabs(["Login", "Registre"])
    
    with tab1:
        email = st.text_input("Email", key="l_e")
        pwd = st.text_input("Password", type="password", key="l_p")
        if st.button("Entrar"):
            u, err = login(email, pwd)
            if u:
                st.session_state.user = u.user
                st.rerun()
            else:
                st.error(err)
    
    with tab2:
        email = st.text_input("Email", key="r_e")
        pwd = st.text_input("Password", type="password", key="r_p")
        name = st.text_input("Nom", key="r_n")
        if st.button("Registrar"):
            u, err = signup(email, pwd, name)
            if u:
                st.success("Registre completat!")
            else:
                st.error(err)
else:
    st.sidebar.title(f"👤 {st.session_state.user.email}")
    if st.sidebar.button("Logout"):
        logout()
        st.session_state.user = None
        st.rerun()
    
    menu = st.sidebar.radio("Navegació", ["Inici", "Xat IA", "Sensacions"])
    
    if menu == "Inici":
        st.title("Benvingut!")
    elif menu == "Xat IA":
        try:
            xats.mostrar_xat()
        except Exception as e:
            st.error(f"Error al xat: {e}")
    elif menu == "Sensacions":
        try:
            Sensacions.mostrar_sensacions()
        except Exception as e:
            st.error(f"Error a sensacions: {e}")
