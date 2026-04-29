import streamlit as st
import google.generativeai as genai

# 1. Configuració de l'API (assegura't que el secrets.toml estigui bé)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.title("🏋️‍♂️ El teu Assessor Fitness IA")
st.caption("Pregunta'm sobre rutines, nutrició o tècnica d'exercicis.")

# 2. Inicialitzar l'historial del xat (perquè no s'esborri en interactuar)
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hola! Sóc el teu entrenador personal. En què et puc ajudar avui?"}
    ]

# 3. Mostrar els missatges de l'historial cada vegada que l'app s'actualitza
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 4. Input del xat (on l'usuari escriu)
if prompt := st.chat_input("Com puc millorar el meu press de banca?"):
    
    # Afegir missatge de l'usuari a l'historial i mostrar-lo
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 5. Resposta de la IA
    with st.chat_message("assistant"):
        with st.spinner("Pensant..."):
            # Preparem el context: passem tot l'historial a Gemini
            system_prompt = "Ets un assessor d'entrenament personal d'elit. Respon de forma concisa i tècnica en català."
            
            # Unim l'historial per donar context a la IA
            context = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            full_prompt = f"{system_prompt}\n\nHistorial:\n{context}\n\nAssistant:"
            
            response = model.generate_content(full_prompt)
            full_response = response.text
            st.markdown(full_response)
    
    # Afegir la resposta de la IA a l'historial
    st.session_state.messages.append({"role": "assistant", "content": full_response})
