import streamlit as st
st.set_page_config(page_title="SportCoach IA", page_icon="🏃", layout="wide")

# --- Imports amb gestió d'errors ---
modules_loaded = {}

try:
    from auth import signup, login, logout, get_user_profile
    modules_loaded['auth'] = True
except Exception as e:
    st.warning(f"⚠️ Warning: No s'ha pogut carregar 'auth': {e}")
    modules_loaded['auth'] = False

try:
    from database import get_db
    modules_loaded['database'] = True
except Exception as e:
    st.warning(f"⚠️ Warning: No s'ha pogut carregar 'database': {e}")
    modules_loaded['database'] = False

# Imports dels mòduls principals (amb fallback)
for mod_name in ['xats', 'Sensacions', 'agents', 'prediccions', 'models', 'strava_sync']:
    try:
        exec(f"import {mod_name}")
        modules_loaded[mod_name] = True
    except ImportError as e:
        st.warning(f"⚠️ Warning: No s'ha pogut carregar '{mod_name}': {e}")
        modules_loaded[mod_name] = False
    except Exception as e:
        st.warning(f"⚠️ Warning: Error carregant '{mod_name}': {e}")
        modules_loaded[mod_name] = False

# Si fallen els crítics, aturem l'app
if not modules_loaded.get('auth') or not modules_loaded.get('database'):
    st.error("❌ Error crític: No es poden carregar els mòduls bàsics (auth/database).")
    st.stop()

# --- Gestió de l'estat de sessió ---
if 'user' not in st.session_state:
    st.session_state.user = None
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = None

# --- Pàgina de Login / Registre ---
if st.session_state.user is None:
    st.title("🏃 SportCoach IA")
    st.caption("Esports amb Intel·ligència Artificial")

    tab1, tab2 = st.tabs(["🔑 Iniciar Sessió", "📝 Registrar-se"])
    
    with tab1:
        st.subheader("Benvingut de nou")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Contrasenya", type="password", key="login_password")
        if st.button("Entrar", type="primary"):
            if modules_loaded['auth']:
                user, error = login(email, password)
                if user:
                    st.session_state.user = user.user
                    st.session_state.user_profile = get_user_profile(user.user.id)
                    st.success("✅ Sessió iniciada!")
                    st.rerun()
                else:
                    st.error(f"Error: {error}")
            else:
                st.error("❌ El sistema d'autenticació no està disponible.")

    with tab2:
        st.subheader("Crea un compte nou")
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Contrasenya", type="password", key="signup_password")
        new_name = st.text_input("Nom complet", key="signup_name")
        if st.button("Registrar-se", type="primary"):
            if modules_loaded['auth']:
                user, error = signup(new_email, new_password, new_name)
                if user:
                    st.success("✅ Registre completat! Ara pots iniciar sessió.")
                    st.info("📧 Si no et deixa entrar, confirma el correu a Supabase.")
                else:
                    st.error(f"Error: {error}")
            else:
                st.error("❌ El sistema de registre no està disponible.")

# --- App Principal (Usuari Loguejat) ---
else:
    user_name = (
        st.session_state.user_profile.get('full_name', 'esportista')
        if st.session_state.user_profile
        else st.session_state.user.email.split('@')[0]
    )

    st.sidebar.title(f"👤 {user_name}")
    st.sidebar.write(f"📧 {st.session_state.user.email}")

    if st.sidebar.button("🚪 Tancar Sessió"):
        if modules_loaded['auth']:
            logout()
        st.session_state.user = None
        st.session_state.user_profile = None
        st.rerun()

    st.sidebar.markdown("---")

    # Construir menú dinàmicament segons quins mòduls estan disponibles
    available_pages = ["🏠 Inici"]
    if modules_loaded.get('xats'): available_pages.append("💬 Xat IA")
    if modules_loaded.get('strava_sync'): available_pages.append("🚴 Strava")
    if modules_loaded.get('agents'): available_pages.append("🤖 Agents")
    if modules_loaded.get('Sensacions'): available_pages.append("💭 Sensacions")
    if modules_loaded.get('prediccions'): available_pages.append("📊 Prediccions")
    if modules_loaded.get('models'): available_pages.append("🧬 Models")

    menu = st.sidebar.radio("Navegació", available_pages, index=0)

    if menu == "🏠 Inici":
        st.title(f"Benvingut, {user_name}! 🏃")
        st.markdown("### El teu entrenador personal IA")
        st.info("Selecciona una opció al menú lateral")
        
        # Mostrar estat dels mòduls (només per debug)
        with st.expander("🔧 Estat dels mòduls (Debug)"):
            for mod, status in modules_loaded.items():
                st.write(f"{'✅' if status else '❌'} {mod}")

    elif menu == "💬 Xat IA":
        if modules_loaded.get('xats'):
            try:
                xats.mostrar_xat()
            except Exception as e:
                st.error(f"❌ Error al xat: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.warning("⚠️ El mòdul de Xat no està disponible.")

    elif menu == "🚴 Strava":
        if modules_loaded.get('strava_sync'):
            try:
                strava_sync.show()
            except Exception as e:
                st.error(f"❌ Error a Strava: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.warning("⚠️ El mòdul de Strava no està disponible.")

    elif menu == "🤖 Agents":
        if modules_loaded.get('agents'):
            try:
                agents.mostrar_agents()
            except Exception as e:
                st.error(f"❌ Error als agents: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.warning("⚠️ El mòdul d'Agents no està disponible.")

    elif menu == "💭 Sensacions":
        if modules_loaded.get('Sensacions'):
            try:
                Sensacions.mostrar_sensacions()
            except Exception as e:
                st.error(f"❌ Error a sensacions: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.warning("⚠️ El mòdul de Sensacions no està disponible.")

    elif menu == "📊 Prediccions":
        if modules_loaded.get('prediccions'):
            try:
                prediccions.mostrar_prediccions()
            except Exception as e:
                st.error(f"❌ Error a prediccions: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.warning("⚠️ El mòdul de Prediccions no està disponible.")

    elif menu == "🧬 Models":
        if modules_loaded.get('models'):
            try:
                models.mostrar_models()
            except Exception as e:
                st.error(f"❌ Error als models: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.warning("⚠️ El mòdul de Models no està disponible.")
