import streamlit as st
st.set_page_config(page_title="SportCoach IA", page_icon="🏃", layout="wide")

try:
    from auth import signup, login, logout, get_user_profile
    from database import get_db
    import xats
    import Sensacions
    import agents
    import prediccions
    import models
    import strava_sync  # ✅ NOU: Import del mòdul Strava
except Exception as e:
    st.error(f"❌ Error carregant mòduls: {e}")
    st.stop()

if 'user' not in st.session_state:
    st.session_state.user = None
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = None

if st.session_state.user is None:
    st.title("🏃 SportCoach IA")
    st.caption("Esports amb Intel·ligència Artificial")

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
                st.success("✅ Sessió iniciada!")
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
                st.success("✅ Registre completat! Ara pots iniciar sessió.")
                st.info("📧 Si no et deixa entrar, confirma el correu a Supabase.")
            else:
                st.error(f"Error: {error}")

else:
    user_name = (
        st.session_state.user_profile.get('full_name', 'esportista')
        if st.session_state.user_profile
        else st.session_state.user.email.split('@')[0]
    )

    st.sidebar.title(f"👤 {user_name}")
    st.sidebar.write(f"📧 {st.session_state.user.email}")

    if st.sidebar.button("🚪 Tancar Sessió"):
        logout()
        st.session_state.user = None
        st.session_state.user_profile = None
        st.rerun()

    st.sidebar.markdown("---")

    # ✅ NOU: Afegit "🚴 Strava" al menú
    menu = st.sidebar.radio(
        "Navegació",
        ["🏠 Inici", "💬 Xat IA", "🚴 Strava", "🤖 Agents", "💭 Sensacions", "📊 Prediccions", "🧬 Models"],
        index=0
    )

    if menu == "🏠 Inici":
        st.title(f"Benvingut, {user_name}! 🏃")
        st.markdown("### El teu entrenador personal IA")
        st.info("Selecciona una opció al menú lateral")

    elif menu == "💬 Xat IA":
        try:
            xats.mostrar_xat()
        except Exception as e:
            st.error(f"❌ Error al xat: {e}")
            import traceback
            st.code(traceback.format_exc())

    # ✅ NOU: Pàgina de Strava
    elif menu == "🚴 Strava":
        try:
            strava_sync.show()  # Crida la funció principal del mòdul Strava
        except Exception as e:
            st.error(f"❌ Error a Strava: {e}")
            import traceback
            st.code(traceback.format_exc())

    elif menu == "🤖 Agents":
        try:
            agents.mostrar_agents()
        except Exception as e:
            st.error(f"❌ Error als agents: {e}")
            import traceback
            st.code(traceback.format_exc())

    elif menu == "💭 Sensacions":
        try:
            Sensacions.mostrar_sensacions()
        except Exception as e:
            st.error(f"❌ Error a sensacions: {e}")
            import traceback
            st.code(traceback.format_exc())

    elif menu == "📊 Prediccions":
        try:
            prediccions.mostrar_prediccions()
        except Exception as e:
            st.error(f"❌ Error a prediccions: {e}")
            import traceback
            st.code(traceback.format_exc())

    elif menu == "🧬 Models":
        try:
            models.mostrar_models()
        except Exception as e:
            st.error(f"❌ Error als models: {e}")
            import traceback
            st.code(traceback.format_exc())
