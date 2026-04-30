import streamlit as st
from openai import OpenAI
from supabase import create_client, Client

# --- 1. CONFIGURACIÓ INICIAL ---

# Configuració AKI.IO (IA)
client = OpenAI(
    api_key=st.secrets["AKI_API_KEY"],
    base_url=st.secrets["AKI_BASE_URL"]
)
MODEL_NAME = "qwen-turbo" 

# Configuració Supabase (Base de Dades)
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.title("🏋️‍♂️ El teu Assessor Fitness IA")
st.caption("Pregunta'm sobre rutines, nutrició o tècnica d'exercicis.")

# --- 2. HISTORIAL DEL XAT (MEMÒRIA) ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hola! Sóc el teu entrenador personal. En què et puc ajudar avui?"}
    ]

# Mostrar missatges
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 3. LÒGICA DEL XAT I GUARDAR A SQL ---
if prompt := st.chat_input("Com puc millorar el meu press de banca?"):
    
    # A. Guardar missatge usuari a l'historial i a la BD
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # GUARDAR A SUPABASE (SQL)
    try:
        supabase.table("messages").insert({
            "role": "user", 
            "content": prompt
        }).execute()
    except Exception as e:
        st.error(f"Error guardant a la BD: {e}")

    # B. Resposta de la IA
    with st.chat_message("assistant"):
        with st.spinner("Pensant..."):
            system_prompt = {"role": "system", "content": "Ets un assessor d'entrenament personal d'elit. Respon de forma concisa i tècnica en català."}
            api_messages = [system_prompt] + st.session_state.messages
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=api_messages,
                temperature=0.7
            )
            full_response = response.choices[0].message.content
            st.markdown(full_response)

    # C. Guardar resposta IA a l'historial i a la BD
    st.session_state.messages.append({"role": "assistant", "content": full_response})
    
    # GUARDAR A SUPABASE (SQL)
    try:
        supabase.table("messages").insert({
            "role": "assistant", 
            "content": full_response
        }).execute()
    except Exception as e:
        st.error(f"Error guardant a la BD: {e}")
