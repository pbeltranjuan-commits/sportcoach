import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid
import pandas as pd
import io
from PIL import Image

# --- EMBEDDINGS LOCALS ---
@st.cache_resource
def load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def get_embedding(text):
    model = load_embedding_model()
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()

# --- OCR PER LLEGIR IMATGES ---
def extract_text_from_image(image_file):
    """Extreu text d'una imatge amb OCR (tesseract)"""
    try:
        import pytesseract
        img = Image.open(image_file)
        text = pytesseract.image_to_string(img, lang='cat+spa+eng')
        return text.strip() if text.strip() else "Imatge sense text detectable"
    except ImportError:
        return "⚠️ pytesseract no instal·lat al servidor"
    except Exception as e:
        return f"Error llegint imatge: {str(e)}"


def mostrar_xat():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return

    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id

    if 'conv_id' not in st.session_state:
        st.session_state.conv_id = None
    if 'msgs' not in st.session_state:
        st.session_state.msgs = []

    def save_memory(content_text):
        try:
            dated_content = f"[{datetime.now().strftime('%Y-%m-%d')}] {content_text}"
            emb = get_embedding(dated_content)
            supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": dated_content,
                "embedding": emb
            }).execute()
            return True
        except Exception as e:
            st.error(f"❌ ERROR GUARDANT MEMÒRIA: {str(e)}")
            return False

    def process_uploaded_file(uploaded_file):
        """Processa fitxers CSV/Excel i guarda les dades com a memòries"""
        try:
            file_ext = uploaded_file.name.split('.')[-1].lower()
            if file_ext == 'csv':
                df = pd.read_csv(uploaded_file)
            elif file_ext in ['xlsx', 'xls']:
                df = pd.read_excel(uploaded_file)
            else:
                st.error("Format no suportat. Utilitza CSV o Excel")
                return False
            
            data_summary = f"Dades del fitxer {uploaded_file.name}:\n"
            data_summary += f"Files: {len(df)}, Columnes: {', '.join(df.columns)}\n"
            data_summary += df.to_string(index=False)
            
            save_memory(f"FITXER PUJAT: {uploaded_file.name} - {data_summary[:500]}...")
            st.success(f"✅ Fitxer processat: {len(df)} files guardades com a memòria")
            return True
        except Exception as e:
            st.error(f"❌ Error processant fitxer: {str(e)}")
            return False

    def extract_and_save_memories(user_message, assistant_response):
        try:
            extraction = client.chat.completions.create(
                model="qwen-turbo",
                messages=[{
                    "role": "user",
                    "content": f"""Analitza aquesta conversa i extreu NOMÉS fets rellevants sobre l'usuari
(estat físic, lesions, cansament, objectius, hàbits de running, emocions importants, edat, pes, característiques personals, vehicle, multes).
Si no hi ha res rellevant, respon exactament: CAP

Usuari: {user_message}
Assistent: {assistant_response}

Respon amb una llista de fets, un per línia, sense guions ni explicacions."""
                }],
                temperature=0,
                max_tokens=200
            )
            content = extraction.choices[0].message.content
            if not content: return
            facts_text = content.strip()
            if facts_text.upper() != "CAP":
                for fact in facts_text.split("\n"):
                    fact = fact.strip("- ").strip()
                    if fact: save_memory(fact)
        except Exception as e:
            st.error(f"❌ Error extracció memòria: {str(e)}")

    # Paraules clau ampliades (incloent vehicles/multes)
    PERSONAL_KEYWORDS = [
        "vell", "jove", "edat", "anys", "quants anys", "qui soc", "com estic",
        "lesió", "lesions", "menisc", "dolor", "cabell", "pes", "alçada",
        "objectiu", "hàbit", "cansament", "cansat", "fatigat",
        "viejo", "joven", "edad", "años", "quién soy", "cómo estoy",
        "lesión", "pelo", "peso", "altura", "objetivo", "cansado",
        "cotxe", "vehicle", "matrícula", "multa", "radar", "infracció", "conductor",
        "coche", "vehículo", "matricula", "multa", "radar", "infracción", "conductor"
    ]

    def get_relevant_memories(query_text, limit=5):
        try:
            query_lower = query_text.lower()
            is_personal = any(kw in query_lower for kw in PERSONAL_KEYWORDS)

            if is_personal:
                search_query = "edat anys lesions estat físic característiques personals objectius vehicle multes de l'usuari"
            else:
                try:
                    expanded = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=[{
                            "role": "user",
                            "content": f"""Reformula aquesta pregunta per buscar informació personal d'un usuari (edat, lesions, estat físic, objectius, hàbits, vehicle, multes).
Pregunta: {query_text}
Escriu només la reformulació en català, sense explicacions."""
                        }],
                        temperature=0, max_tokens=80
                    )
                    search_query = expanded.choices[0].message.content.strip()
                except:
                    search_query = query_text

            query_emb = get_embedding(search_query)
            res = supabase.rpc("match_memories", {
                "query_embedding": query_emb,
                "match_threshold": 0.3,
                "match_count": limit,
                "p_user_id": user_id
            }).execute()

            if res.data:
                return [row["content"] for row in res.data]
            return []
        except Exception as e:
            st.error(f"❌ ERROR CERCA RAG: {str(e)}")
            return []

    # Inicialitzar conversa
    if st.session_state.conv_id is None:
        res = supabase.table("conversations").insert({
            "user_id": user_id, "title": "Nova conversa", "updated_at": datetime.now().isoformat()
        }).execute()
        st.session_state.conv_id = res.data[0]['id']
        st.session_state.msgs = []

    if not st.session_state.msgs:
        st.session_state.msgs = supabase.table("messages").select("*").eq("conversation_id", st.session_state.conv_id).order("created_at").execute().data

    st.title("💬 Xat IA - Entrenador de Running")
    st.caption("Memòria intel·ligent activa: recordo el teu historial + llegeixo documents 📸")

    # Selector de converses
    convs = supabase.table("conversations").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(10).execute().data
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Carregar:", list(opts.keys()))
            if st.button("Carregar"):
                st.session_state.conv_id = opts[sel]
                st.session_state.msgs = []
                st.rerun()
        with col2:
            if st.button("🆕 Nova"):
                res = supabase.table("conversations").insert({
                    "user_id": user_id, "title": "Nova", "updated_at": datetime.now().isoformat()
                }).execute()
                st.session_state.conv_id = res.data[0]['id']
                st.session_state.msgs = []
                st.rerun()

    st.markdown("---")
    
    # Botons de gestió de memòria
    col_test1, col_test2, col_test3 = st.columns(3)
    with col_test1:
        if st.button("🧪 Provar Memòria"):
            save_memory("Tinc 30 anys")
            save_memory("El meu cotxe és un Toyota amb matrícula ABC-1234")
            st.info("Memòries de prova guardades!")
    with col_test2:
        if st.button("📊 Estadístiques"):
            total_mem = supabase.table("long_term_memories").select("*", count="exact").eq("user_id", user_id).execute()
            st.metric("Total memòries", total_mem.count if hasattr(total_mem, 'count') else len(total_mem.data))
    with col_test3:
        if st.button("📋 Veure memòries"):
            all_mems = supabase.table("long_term_memories").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute()
            if all_mems.data:
                for mem in all_mems.data:
                    st.text_area(f" {mem['created_at'][:10]}", mem['content'], height=80)
            else:
                st.info("Cap memòria guardada encara")

    st.markdown("### 📎 Adjuntar fitxers")
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        prompt = st.chat_input("Pregunta sobre running, lesions, objectius, vehicles...")
    with col2:
        uploaded_image = st.file_uploader("Imatge", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    with col3:
        uploaded_file = st.file_uploader("CSV/Excel", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

    # Processar CSV/Excel
    if uploaded_file:
        with st.spinner(f"📊 Processant {uploaded_file.name}..."):
            process_uploaded_file(uploaded_file)

    # Processar IMATGE amb OCR
    if uploaded_image:
        with st.spinner(" Llegint text de la imatge..."):
            ocr_text = extract_text_from_image(uploaded_image)
            
            if ocr_text and "Error" not in ocr_text and "⚠️" not in ocr_text:
                # Mostra el text extret (debug)
                with st.expander("👁️ Veure text extret per l'OCR"):
                    st.code(ocr_text)
                
                # Guarda a memòria amb context clar
                memory_text = f"DOCUMENT PUJAT (imatge OCR): {ocr_text}"
                save_memory(memory_text)
                st.success(f"✅ Text guardat a la memòria ({len(ocr_text)} caràcters)")
            else:
                st.warning(f"⚠️ {ocr_text}")

    # Mostrar missatges del xat
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300, caption="📷 Imatge adjunta")
            st.markdown(m["content"])

    # Processar prompt de l'usuari
    if prompt:
        image_url = None
        
        # Pujar imatge a Storage (només per visualització)
        if uploaded_image:
            with st.spinner("Pujant imatge..."):
                ext = uploaded_image.name.split('.')[-1]
                fn = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("chat-images").upload(fn, uploaded_image.getvalue())
                image_url = supabase.storage.from_("chat-images").get_public_url(fn)

        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user",
            "content": prompt,
            "image_url": image_url
        }).execute()

        with st.chat_message("assistant"):
            with st.spinner("Consultant memòria i pensant..."):
                memories = get_relevant_memories(prompt, limit=5)

                if memories:
                    context = "HISTORIAL DE L'USUARI (amb dates):\n" + "\n".join([f"- {m}" for m in memories])
                else:
                    context = "No hi ha historial previ de l'usuari."

                sys_msg = {
                    "role": "system",
                    "content": (
                        "Ets un assistent personal expert en running, salut i gestió documental. "
                        f"Tens accés a l'historial de l'usuari:\n\n{context}\n\n"
                        "INSTRUCCIONS: "
                        "1. Utilitza l'historial per personalitzar les respostes. "
                        "2. Si hi ha dates, raona temporalment. "
                        "3. Si l'historial conté dades de documents OCR (multes, vehicles, lesions), UTILITZA-LES. "
                        "4. Respon sempre en català de forma clara i directa."
                    )
                }
                history = [sys_msg] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.msgs[-8:]]

                try:
                    res = client.chat.completions.create(model="qwen-turbo", messages=history, temperature=0.7)
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    supabase.table("messages").insert({
                        "conversation_id": st.session_state.conv_id,
                        "role": "assistant",
                        "content": ans
                    }).execute()
                    extract_and_save_memories(prompt, ans)
                except Exception as e:
                    st.error(f"❌ ERROR IA: {str(e)}")
