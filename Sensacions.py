import streamlit as st
from datetime import datetime, timedelta
from database import get_db
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Sensacions", page_icon="💭")

# Verificar autenticació
if 'user' not in st.session_state or st.session_state.user is None:
    st.warning("🔒 Has d'iniciar sessió per accedir")
    st.stop()

supabase = get_db()
user_id = st.session_state.user.id

st.title("💭 Sensacions de l'Entrenament")
st.caption("Registra com t'has sentit després de cada entrenament")

# Tabs
tab1, tab2, tab3 = st.tabs(["📝 Registrar", "📊 Historial", "📈 Evolució"])

with tab1:
    st.subheader("Com t'has sentit avui?")
    
    col1, col2 = st.columns(2)
    
    with col1:
        date = st.date_input("Data", datetime.now())
        training_quality = st.slider("Qualitat de l'entrenament ⭐", 1, 10, 7, 
                                     help="Com de bé ha anat l'entrenament?")
        training_difficulty = st.slider("Dificultat percebuda 💪", 1, 10, 5,
                                       help="Com de dur t'ha semblat?")
        perceived_exertion = st.slider("Esfors percebut (RPE) 🔥", 1, 10, 6,
                                      help="Escala d'esforç percebut")
    
    with col2:
        sleep_hours = st.number_input("Hores de son 😴", 0.0, 12.0, 7.5, 0.5)
        sleep_quality = st.slider("Qualitat del son 🌙", 1, 10, 7,
                                 help="Com de bé has dormit?")
        muscle_soreness = st.slider("Fatiga muscular 🦵", 1, 10, 3,
                                   help="Com et trobes de carregat?")
    
    st.markdown("---")
    st.subheader("Estat General")
    
    col3, col4 = st.columns(2)
    
    with col3:
        fatigue_level = st.slider("Fatiga general 😮‍💨", 1, 10, 4,
                                 help="Nivell de cansament general")
        motivation = st.slider("Motivació 🔥", 1, 10, 7,
                              help="Ganes d'entrenar")
        stress_level = st.slider("Estrès 😰", 1, 10, 4,
                                help="Nivell d'estrès avui")
    
    with col4:
        mood = st.selectbox("Estat d'ànim 😊", 
                           ["Excel·lent", "Bé", "Normal", "Baix", "Molt baix"])
        notes = st.text_area("Notes/addicionals 📝", 
                            placeholder="Com et sents? Alguna molèstia?")
    
    # Botó guardar
    if st.button("💾 Guardar Sensacions", type="primary", use_container_width=True):
        try:
            data = {
                "user_id": user_id,
                "date": date.isoformat(),
                "training_quality": training_quality,
                "training_difficulty": training_difficulty,
                "sleep_hours": sleep_hours,
                "sleep_quality": sleep_quality,
                "muscle_soreness": muscle_soreness,
                "fatigue_level": fatigue_level,
                "motivation": motivation,
                "stress_level": stress_level,
                "mood": mood,
                "perceived_exertion": perceived_exertion,
                "notes": notes if notes else None
            }
            
            # Intentar inserir o actualitzar si ja existeix
            response = supabase.table("training_sensations").upsert(data).execute()
            
            st.success("✅ Sensacions guardades correctament!")
            st.balloons()
            
        except Exception as e:
            st.error(f"Error: {str(e)}")

with tab2:
    st.subheader("Historial de Sensacions")
    
    # Carregar dades
    response = supabase.table("training_sensations")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("date", desc=True)\
        .limit(20)\
        .execute()
    
    if response.data:
        df = pd.DataFrame(response.data)
        
        # Mostrar última entrada
        st.markdown("### Última entrada")
        last = df.iloc[0]
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Qualitat", f"{last['training_quality']}/10")
        with col2:
            st.metric("Son", f"{last['sleep_hours']}h")
        with col3:
            st.metric("Fatiga", f"{last['fatigue_level']}/10")
        with col4:
            st.metric("Motivació", f"{last['motivation']}/10")
        
        st.markdown("---")
        st.dataframe(df[['date', 'training_quality', 'sleep_hours', 
                        'sleep_quality', 'fatigue_level', 'motivation']], 
                    use_container_width=True)
    else:
        st.info("📝 Encara no has registrat cap sensació")

with tab3:
    st.subheader("Evolució de les Sensacions")
    
    # Carregar dades
    response = supabase.table("training_sensations")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("date", asc=True)\
        .execute()
    
    if response.data and len(response.data) > 1:
        df = pd.DataFrame(response.data)
        df['date'] = pd.to_datetime(df['date'])
        
        # Gràfics
        col1, col2 = st.columns(2)
        
        with col1:
            fig_quality = px.line(df, x='date', y='training_quality', 
                                 title="Qualitat de l'Entrenament",
                                 markers=True)
            fig_quality.update_yaxes(range=[0, 11])
            st.plotly_chart(fig_quality, use_container_width=True)
        
        with col2:
            fig_sleep = px.line(df, x='date', y='sleep_hours', 
                               title="Hores de Son",
                               markers=True)
            st.plotly_chart(fig_sleep, use_container_width=True)
        
        col3, col4 = st.columns(2)
        
        with col3:
            fig_fatigue = px.line(df, x='date', y='fatigue_level', 
                                 title="Fatiga General",
                                 markers=True)
            fig_fatigue.update_yaxes(range=[0, 11])
            st.plotly_chart(fig_fatigue, use_container_width=True)
        
        with col4:
            fig_motivation = px.line(df, x='date', y='motivation', 
                                    title="Motivació",
                                    markers=True)
            fig_motivation.update_yaxes(range=[0, 11])
            st.plotly_chart(fig_motivation, use_container_width=True)
        
        # Resum estadístic
        st.markdown("### 📊 Resum Estadístic")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Qualitat mitjana", f"{df['training_quality'].mean():.1f}/10")
        with col2:
            st.metric("Son mitjà", f"{df['sleep_hours'].mean():.1f}h")
        with col3:
            st.metric("Fatiga mitjana", f"{df['fatigue_level'].mean():.1f}/10")
    else:
        st.info("📈 Necessites més d'una entrada per veure gràfics")
