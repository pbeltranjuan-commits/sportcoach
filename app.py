import streamlit as st
from openai import OpenAI

# 1. Configuració de l'API AKI.IO (compatible amb OpenAI)
client = OpenAI(
    api_key=st.secrets["AKI_API_KEY"],
    base_url=st.secrets["AKI_BASE_URL"]
)

MODEL_NAME = "qwen-turbo"  # Model ràpid i econòmic

st.title("🏋️♂️ El teu Assessor Fitness IA")
st.caption("Pregunta'm sobre rutines, nutrició o tècnica d'exercicis.")

# 2. Inicialitzar l'historial del xat
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hola! Sóc el teu entrenador personal. En què et puc ajudar avui?"}
    ]

# 3. Mostrar missatges
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 4. Input del xat
if prompt := st.chat_input("Com puc millorar el meu press de banca?"):
    
    # Afegir missatge de l'usuari
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 5. Resposta de la IA
    with st.chat_message("assistant"):
        with st.spinner("Pensant..."):
            # System prompt per donar context
            system_prompt = {"role": "system", "content": "Ets un assessor d'entrenament personal d'elit. Respon de forma concisa i tècnica en català."}
            
            # Unim system prompt + historial
            api_messages = [system_prompt] + st.session_state.messages
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=api_messages,
                temperature=0.7
            )
            full_response = response.choices[0].message.content
            st.markdown(full_response)
    
    # Afegir resposta a l'historial
    st.session_state.messages.append({"role": "assistant", "content": full_response})
