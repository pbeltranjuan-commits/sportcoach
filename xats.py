import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid


# --- EMBEDDINGS LOCALS (sense OpenAI) ---
@st.cache_resource
def load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def get_embedding(text):
    model = load_embedding_model()
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()


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

    # --- ANALITZAR IMATGE AMB URL PÚBLICA ---
    def analyze_image_and_save(image_url):
        try:
            response = client.chat.completions.create(
                model="qwen-turbo",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        },
                        {
                            "type": "text",
                            "text": "Descriu aquesta imatge en detall. Si conté dades d'entrenament, running, salut o resultats esportius, extreu tota la informació numèrica i rellevant. Respon en català."
                        }
                    ]
                }],
                max_tokens=500
            )
            description = response.choices[0].message.content
            if description:
                save_memory(f"IMATGE ANALITZADA: {description}")
                return description
            return None
        except Exception as e:
            st.warning(f"⚠️ No s'ha pogut analitzar la imatge: {str(e)}")
            return None

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
        "hores", "qualitat", "motivació", "sensació", "entrenament",
        "viejo", "joven", "edad", "años", "quién soy", "cómo estoy",
        "lesión", "pelo", "peso", "altura", "objetivo", "cansado", "horas",
        "recordes", "recuerdas", "vas dir", "dijiste", "fa temps", "antes"
    ]

    # --- CERCA RAG ---
    def get_relevant_memories(query_text, limit=6):
        try:
            query_lower = query_text.lower()
            is_personal = any(kw in query_lower for kw in PERSONAL_KEYWORDS)

            if is_personal:
                search_query = "edat anys lesions estat físic característiques personals objectius son hores fatiga motivació conversa anterior usuari"
            else:
                try:
                    expanded = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=[{
                            "role": "user",
                            "content": f"""Reformula aquesta pregunta per buscar informació personal d'un usuari (edat, lesions, estat físic, objectius, hàbits, emocions, dades d'entrenament).
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
                st.rerun()

    st.markdown("---")

    if st.button("🧪 PROVAR MEMÒRIA MANUALMENT"):
        test_facts = ["Tinc 30 anys", "El meu cabell és roig", "Vaig trencar el menisc fa un any"]
        for f in test_facts:
            save_memory(f)
        st.info("Memòries de prova guardades! Pregunta 'Soc vell?' o 'Quants anys tinc?' per verificar.")

    # --- ADJUNTS I INPUT ---
    col1, col2, col3 = st.columns([4, 1, 1])
    with col1:
        prompt = st.chat_input("Pregunta...")
    with col2:
        uploaded_image = st.file_uploader("📷", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    with col3:
        uploaded_file = st.file_uploader("📊", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

    # Processar CSV/Excel
    if uploaded_file:
        with st.spinner(f"📊 Processant {uploaded_file.name}..."):
            df = process_file_and_save(uploaded_file)
            if df is not None:
                st.success(f"✅ Fitxer guardat a memòria ({len(df)} files)")
                st.dataframe(df.head(5))

    # Processar imatge: pujar a Storage primer, després analitzar amb URL
    pending_image_url = None
    if uploaded_image:
        with st.spinner("📤 Pujant imatge..."):
            try:
                ext = uploaded_image.name.split('.')[-1]
                fn = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("chat-images").upload(fn, uploaded_image.getvalue())
                pending_image_url = supabase.storage.from_("chat-images").get_public_url(fn)
                st.image(uploaded_image, width=200)

                with st.spinner("🔍 Analitzant imatge..."):
                    description = analyze_image_and_save(pending_image_url)
                    if description:
                        st.success("✅ Imatge analitzada i guardada a memòria")
                        st.info(f"📄 {description[:200]}...")
            except Exception as e:
                st.error(f"❌ Error pujant imatge: {str(e)}")

    # Mostrar historial
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300)
            st.markdown(m["content"])

    # --- PROCESSAMENT DEL MISSATGE ---
    if prompt:
        image_url = pending_image_url

        # Guardar missatge a SQL
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user",
            "content": prompt,
            "image_url": image_url
        }).execute()

        # Guardar sempre a memòria llarg termini
        save_memory(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Consultant memòria i pensant..."):
                memories = get_relevant_memories(prompt, limit=6)

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
                        "2. Si hi ha dates, raona temporalment (p.ex. 'fa 3 mesos deies que...').\n"
                        "3. Si l'usuari et diu alguna dada personal (edat, pes, lesió...), confirma que ho has registrat.\n"
                        "4. Respon sempre en català."
                    )
                }
                history = [sys_msg] + [
                    {"role": m["role"], "content": m["content"]}
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
