import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid
import pandas as pd
from PIL import Image

@st.cache_resource
def load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def get_embedding(text):
    model = load_embedding_model()
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()

def extract_text_from_image(image_file):
    try:
        import pytesseract
        img = Image.open(image_file)
        return pytesseract.image_to_string(img, lang='cat+spa+eng').strip()
    except:
        return "ERROR: OCR no disponible"

def mostrar_xat():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning(" Has d'iniciar sessió")
        return

    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id

    if 'conv_id' not in st.session_state: st.session_state.conv_id = None
    if 'msgs' not in st.session_state: st.session_state.msgs = []

    def save_memory(content_text):
        try:
            dated = f"[{datetime.now().strftime('%Y-%m-%d')}] {content_text}"
            emb = get_embedding(dated)
            supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": dated,
                "embedding": emb
            }).execute()
            st.success(f"✅ Guardat: {content_text[:60]}...")
        except Exception as e:
            st.error(f"❌ Error SQL: {str(e)}")

    # Inicialitzar
    if st.session_state.conv_id is None:
        res = supabase.table("conversations").insert({
            "user_id": user_id, "title": "Nova", "updated_at": datetime.now().isoformat()
        }).execute()
        st.session_state.conv_id = res.data[0]['id']
        st.session_state.msgs = []

    if not st.session_state.msgs:
        st.session_state.msgs = supabase.table("messages").select("*").eq(
            "conversation_id", st.session_state.conv_id
        ).order("created_at").execute().data

    st.title("💬 Xat IA + Memòria SQL")
    
    # Botó per veure TOTES les memòries (debug)
    if st.button(" VEURE TOTES LES MEVES DADES GUARDADES"):
        try:
            res = supabase.table("long_term_memories").select("*").eq(
                "user_id", user_id
            ).order("created_at", desc=True).limit(20).execute()
            
            if res.
                st.info(f" Total: {len(res.data)} registres trobats")
                for i, r in enumerate(res.data):
                    with st.expander(f"{i+1}. {r['created_at'][:10]}"):
                        st.write(r['content'])
            else:
                st.warning(" Cap dada guardada encara")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        prompt = st.chat_input("Pregunta...")
    with col2:
        uploaded_img = st.file_uploader(" Imatge", type=["jpg","png","jpeg"])

    # Processar imatge IMMEDIATAMENT
    if uploaded_img:
        st.info("🔍 Llegint imatge...")
        ocr_text = extract_text_from_image(uploaded_img)
        
        if ocr_text and "ERROR" not in ocr_text:
            st.expander("👁️ Text detectat").write(ocr_text)
            save_memory(f"DOCUMENT: {ocr_text}")
        else:
            st.error(ocr_text)

    # Mostrar xat
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"): st.image(m["image_url"], width=300)
            st.markdown(m["content"])

    # Processar pregunta
    if prompt:
        # Guardar missatge
        st.session_state.msgs.append({"role": "user", "content": prompt})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user", 
            "content": prompt
        }).execute()
        
        # 🔍 CERCAR TOTES LES MEMÒRIES (no només les semblants)
        with st.spinner("Buscant a la base de dades..."):
            try:
                # Obtenim TOTES les memòries de l'usuari (màxim 50)
                all_memories = supabase.table("long_term_memories").select("*").eq(
                    "user_id", user_id
                ).order("created_at", desc=True).limit(50).execute()
                
                if all_memories.
                    # Creem un context amb TOTES les dades
                    context = "DADES DE L'USUARI (tot l'historial):\n\n"
                    for mem in all_memories.data:
                        context += f"- {mem['content']}\n"
                    
                    st.info(f"📚 Trobades {len(all_memories.data)} memòries a la base de dades")
                else:
                    context = "No hi ha dades prèvies de l'usuari."
                    st.warning("⚠️ Cap memòria trobada")
                    
            except Exception as e:
                context = "Error carregant dades."
                st.error(f"Error cerca: {e}")

        # Respondre amb IA
        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                try:
                    system_msg = {
                        "role": "system",
                        "content": f"""Ets un assistent útil.
                        
{context}

INSTRUCCIONS:
1. Si la pregunta es pot respondre amb les DADES DE L'USUARI de dalt, respon utilitzant AQUEIXES DADES.
2. Si no hi ha informació rellevant, digues que no ho saps.
3. Respon en català de forma clara i directa.
4. Cita la font si utilitzes dades concretes (ex: "Segons el document que vas pujar...")."""
                    }
                    
                    history = [system_msg, {"role": "user", "content": prompt}]
                    
                    res = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=history,
                        temperature=0.3  # Més determinista
                    )
                    
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    
                    # Guardar resposta
                    st.session_state.msgs.append({"role": "assistant", "content": ans})
                    supabase.table("messages").insert({
                        "conversation_id": st.session_state.conv_id,
                        "role": "assistant",
                        "content": ans
                    }).execute()
                    
                except Exception as e:
                    st.error(f"❌ Error IA: {e}")
