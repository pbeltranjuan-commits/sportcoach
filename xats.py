import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid
import base64
import google.generativeai as genai
from PIL import Image
import io


# --- EMBEDDINGS LOCALS ---
@st.cache_resource
def load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def get_embedding(text):
    model = load_embedding_model()
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()


# --- OCR AMB GEMINI VISION ---
def extract_text_from_image_vision(image_bytes):
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel("gemini-1.5-flash")
        img = Image.open(io.BytesIO(image_bytes))
        response = model.generate_content([
            img,
            (
                "Extreu i transcriu TOT el text que veus en aquesta imatge. "
                "Inclou tots els números, valors, dates, etiquetes i unitats. "
                "Si és una captura d'una app esportiva (Garmin, Polar, Apple Health, Wahoo, etc.), "
                "extreu les mètriques: HRV, FC, VO2max, distància, ritme, calories, son, etc. "
                "Respon NOMÉS amb el text extret, sense explicacions."
            )
        ])
        text = response.text
        return text.strip() if text and text.strip() else None
    except Exception as e:
        st.warning(f"⚠️ Gemini Vision error: {str(e)}")
        return None


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
    if 'pending_ocr' not in st.session_state:
        st.session_state.pending_ocr = None
    if 'pending_image_url' not in st.session_state:
        st.session_state.pending_image_url = None

    # --- GUARDAR MEMÒRIA ---
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

    # --- PROCESSAR CSV/EXCEL ---
    def process_file_and_save(uploaded_file):
        try:
            import pandas as pd
            ext = uploaded_file.name.split('.')[-1].lower()
            if ext == 'csv':
                df = pd.read_csv(uploaded_file)
            elif ext in ['xlsx', 'xls']:
                df = pd.read_excel(uploaded_file)
            else:
                st.error("Format no suportat")
                return None
            summary = (
                f"Fitxer '{uploaded_file.name}': "
                f"{len(df)} files, columnes: {', '.join(df.columns.tolist())}. "
                f"Primeres dades: {df.head(5).to_string(index=False)}"
            )
            save_memory(f"FITXER PUJAT: {summary[:800]}")
            return df
        except Exception as e:
            st.error(f"❌ Error processant fitxer: {str(e)}")
            return None

    # --- PARAULES CLAU PER FORÇAR CERCA PERSONAL ---
    PERSONAL_KEYWORDS = [
        "vell", "jove", "edat", "anys", "quants anys", "qui soc", "com estic",
        "lesió", "lesions", "menisc", "dolor", "cabell", "pes", "alçada",
        "objectiu", "hàbit", "cansament", "cansat", "fatigat", "son", "dormir",
        "hores", "qualitat", "motivació", "sensació", "entrenament", "hrv",
        "freqüència", "cardíaca", "batecs", "pulsacions", "ritme", "vo2",
        "viejo", "joven", "edad", "años", "quién soy", "cómo estoy",
        "lesión", "pelo", "peso", "altura", "objetivo", "cansado", "horas",
        "recordes", "recuerdas", "vas dir", "dijiste", "fa temps", "antes",
        "captura", "imatge", "foto", "screenshot"
    ]

    # --- CERCA RAG ---
    def get_relevant_memories(query_text, limit=6):
        try:
            query_lower = query_text.lower()
            is_personal = any(kw in query_lower for kw in PERSONAL_KEYWORDS)

            if is_personal:
                search_query = "edat anys lesions estat físic característiques personals objectius son hores fatiga motivació HRV freqüència cardíaca entrenament dades"
            else:
                try:
                    expanded = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=[{
                            "role": "user",
                            "content": f"""Reformula aquesta pregunta per buscar informació personal d'un usuari (edat, lesions, estat físic, objectius, hàbits, emocions, dades d'entrenament, HRV, FC).
Pregunta: {query_text}
Escriu només la reformulació en català, sense explicacions."""
                        }],
                        temperature=0,
                        max_tokens=80
                    )
                    exp_content = expanded.choices[0].message.content
                    search_query = exp_content.strip() if exp_content else query_text
                except Exception:
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

    # --- INICIALITZACIÓ CONVERSA ---
    if st.session_state.conv_id is None:
        res = supabase.table("conversations").insert({
            "user_id": user_id,
            "title": "Nova conversa",
            "updated_at": datetime.now().isoformat()
        }).execute()
        st.session_state.conv_id = res.data[0]['id']
        st.session_state.msgs = []

    if not st.session_state.msgs:
        st.session_state.msgs = (
            supabase.table("messages")
            .select("*")
            .eq("conversation_id", st.session_state.conv_id)
            .order("created_at")
            .execute()
            .data
        )

    # --- INTERFÍCIE ---
    st.title("💬 Xat IA - El teu Entrenador Virtual")
    st.caption("Memòria intel·ligent activa: recordo totes les teves converses")

    convs = (
        supabase.table("conversations")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(10)
        .execute()
        .data
    )
    if convs:
        col1, col2 = st.columns([3, 1])
        with col1:
            opts = {c['title'] or f"Conv {i+1}": c['id'] for i, c in enumerate(convs)}
            sel = st.selectbox("Carregar:", list(opts.keys()))
            if st.button("Carregar"):
                st.session_state.conv_id = opts[sel]
                st.session_state.msgs = []
                st.session_state.pending_ocr = None
                st.session_state.pending_image_url = None
                st.rerun()
        with col2:
            if st.button("🆕 Nova"):
                res = supabase.table("conversations").insert({
                    "user_id": user_id,
                    "title": "Nova",
                    "updated_at": datetime.now().isoformat()
                }).execute()
                st.session_state.conv_id = res.data[0]['id']
                st.session_state.msgs = []
                st.session_state.pending_ocr = None
                st.session_state.pending_image_url = None
                st.rerun()

    st.markdown("---")

    # --- ADJUNTS ---
    uploaded_image = st.file_uploader(
        "📷 Adjunta captura (Garmin, HRV, etc.)",
        type=["jpg", "jpeg", "png"],
        label_visibility="visible"
    )
    uploaded_file = st.file_uploader(
        "📊 Adjunta fitxer de dades",
        type=["csv", "xlsx", "xls"],
        label_visibility="visible"
    )

    # Processar CSV/Excel
    if uploaded_file:
        with st.spinner(f"📊 Processant {uploaded_file.name}..."):
            df = process_file_and_save(uploaded_file)
            if df is not None:
                st.success(f"✅ Fitxer guardat a memòria ({len(df)} files)")
                st.dataframe(df.head(5))

    # Processar imatge amb Vision API
    if uploaded_image:
        img_bytes = uploaded_image.getvalue()
        st.image(uploaded_image, width=250)

        with st.spinner("🔍 Analitzant imatge amb IA..."):
            ocr_text = extract_text_from_image_vision(img_bytes)

        if ocr_text:
            # Guardar a memòria immediatament
            save_memory(f"DADES DE CAPTURA: {ocr_text[:800]}")
            st.success("✅ Dades de la imatge guardades a memòria!")
            st.info(f"📄 Text detectat: {ocr_text[:300]}{'...' if len(ocr_text) > 300 else ''}")
            st.session_state.pending_ocr = ocr_text
        else:
            st.warning("⚠️ No s'ha pogut extreure text de la imatge")
            st.session_state.pending_ocr = None

        # Pujar a storage
        try:
            ext = uploaded_image.name.split('.')[-1]
            fn = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{ext}"
            supabase.storage.from_("chat-images").upload(fn, img_bytes)
            st.session_state.pending_image_url = supabase.storage.from_("chat-images").get_public_url(fn)
        except Exception:
            st.session_state.pending_image_url = None

    st.markdown("---")

    # Mostrar historial
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300)
            st.markdown(m["content"])

    # --- INPUT I PROCESSAMENT ---
    prompt = st.chat_input("Pregunta...")

    if prompt:
        ocr_context = st.session_state.pending_ocr
        image_url = st.session_state.pending_image_url

        # Prompt enriquit amb OCR si n'hi ha
        prompt_with_ocr = prompt
        if ocr_context:
            prompt_with_ocr = (
                f"{prompt}\n\n"
                f"[Dades extretes de la imatge adjunta:\n{ocr_context[:600]}]"
            )

        # Mostrar missatge usuari
        with st.chat_message("user"):
            if image_url:
                st.image(image_url, width=300)
            st.markdown(prompt)

        # Guardar a BD
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user",
            "content": prompt,
            "image_url": image_url
        }).execute()

        # Guardar prompt a memòria
        save_memory(prompt)

        # Netejar pending
        st.session_state.pending_ocr = None
        st.session_state.pending_image_url = None

        with st.chat_message("assistant"):
            with st.spinner("Consultant memòria i pensant..."):
                memories = get_relevant_memories(prompt_with_ocr, limit=8)

                if memories:
                    context = "HISTORIAL DE L'USUARI (amb dates):\n" + "\n".join([f"- {m}" for m in memories])
                else:
                    context = "No hi ha historial previ de l'usuari."

                sys_msg = {
                    "role": "system",
                    "content": (
                        "Ets un entrenador virtual personal especialitzat en running. "
                        f"Tens accés a l'historial complet de l'usuari:\n\n{context}\n\n"
                        "INSTRUCCIONS IMPORTANTS:\n"
                        "1. Si l'historial conté dades rellevants per a la pregunta, utilitza-les SEMPRE.\n"
                        "2. Si hi ha captures d'apps esportives (HRV, FC, VO2max, etc.), analitza-les i comenta-les.\n"
                        "3. Si hi ha dates, raona temporalment (p.ex. 'fa 3 mesos deies que...').\n"
                        "4. Si l'usuari et diu alguna dada personal (edat, pes, lesió...), confirma que ho has registrat.\n"
                        "5. Respon sempre en català."
                    )
                }

                history = [sys_msg] + [
                    {
                        "role": m["role"],
                        "content": m["content"] if m["content"] != prompt else prompt_with_ocr
                    }
                    for m in st.session_state.msgs[-8:]
                ]

                try:
                    res = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=history,
                        temperature=0.7
                    )
                    ans = res.choices[0].message.content
                    st.markdown(ans)

                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    supabase.table("messages").insert({
                        "conversation_id": st.session_state.conv_id,
                        "role": "assistant",
                        "content": ans
                    }).execute()

                    save_memory(f"Entrenador: {ans[:300]}")

                except Exception as e:
                    st.error(f"❌ ERROR IA: {str(e)}")
