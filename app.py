import streamlit as st
from openai import OpenAI

# --- 1. CONFIGURACIÓ DE LA IA (AKI.IO) ---
try:
    client = OpenAI(
        api_key=st.secrets["AKI_API_KEY"],
        base_url=st.secrets["AKI_BASE_URL"]
    )
    MODEL_NAME = "qwen-turbo"
    IA_OK = True
except Exception as e:
    st.error(f"❌ Error configurant la IA: {e}")
    IA_OK = False

# --- 2. CONFIGURACIÓ DE SUPABASE (OPCIONAL) ---
supabase = None
DB_OK = False
try:
    from supabase import create_client, Client
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY")
    if url and key:
        supabase: Client = create_client(url, key)
        DB_OK = True
except Exception as e:
    st.warning(f"⚠️ Supabase no disponible: {e}")
    DB_OK = False

# --- 3. INTERFÍCIE ---
st.title("🏋️‍♂️ El teu Assessor Fitness IA")
st.caption("Pregunta'm sobre rutines, nutrició o tècnica d'exercicis.")

if DB_OK:
    st.success("✅ Base de dades connectada")
else:
    st.warning("⚠️ Mode sense base de dades (els missatges no es guardaran)")

# --- 4. HISTORIAL DEL XAT ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hola! Sóc el teu entrenador personal. En què et puc ajudar avui?"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 5. LÒGICA DEL XAT ---
if prompt := st.chat_input("Com puc millorar el meu press de banca?"):
    
    if not IA_OK:
        st.error("❌ La IA no està configurada. Revisa els secrets.")
        st.stop()
    
    # Missatge usuari
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Guardar a Supabase (si funciona)
    if DB_OK and supabase:
        try:
            supabase.table("messages").insert({"role": "user", "content": prompt}).execute()
        except:
            pass  # No fem res si falla
    
    # Resposta de la IA
    with st.chat_message("assistant"):
        with st.spinner("Pensant..."):
            try:
                system_prompt = {"role": "system", "content": "Ets un assessor d'entrenament personal d'elit. Respon de forma concisa i tècnica en català."}
                api_messages = [system_prompt] + st.session_state.messages
                
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=api_messages,
                    temperature=0.7
                )
                full_response = response.choices[0].message.content
                st.markdown(full_response)
                
                # Guardar resposta a Supabase (si funciona)
                if DB_OK and supabase:
                    try:
                        supabase.table("messages").insert({"role": "assistant", "content": full_response}).execute()
                    except:
                        pass
                        
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                
            except Exception as e:
                st.error(f"❌ Error amb la IA: {e}")
