import streamlit as st
from database import get_db
from openai import OpenAI
from datetime import datetime
import uuid
import pandas as pd
from PIL import Image

# --- EMBEDDINGS LOCALS (El mateix model que usa Sensacions) ---
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
        return "⚠️ pytesseract no instal·lat"
    except Exception as e:
        return f"Error llegint imatge: {str(e)}"

# --- PROCESSAR CSV/EXCEL ---
def process_uploaded_file(uploaded_file, user_id, save_memory_func):
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
        
        save_memory_func(f"FITXER PUJAT: {uploaded_file.name} - {data_summary[:500]}...")
        st.success(f"✅ Fitxer processat: {len(df)} files guardades com a memòria")
        return True
    except Exception as e:
        st.error(f"❌ Error processant fitxer: {str(e)}")
        return False

def mostrar_xat():
    if 'user' not in st.session_state or st.session_state.user is None:
        st.warning("🔒 Has d'iniciar sessió")
        return

    supabase = get_db()
    client = OpenAI(api_key=st.secrets["AKI_API_KEY"], base_url=st.secrets["AKI_BASE_URL"])
    user_id = st.session_state.user.id

    if 'conv_id' not in st.session_state: st.session_state.conv_id = None
    if 'msgs' not in st.session_state: st.session_state.msgs = []

    # =====================================================
    # 1. GUARDAR A MEMÒRIA LLARG TERMINI (SQL)
    # =====================================================
    def save_memory(content_text):
        try:
            dated = f"[{datetime.now().strftime('%Y-%m-%d')}] {content_text}"
            emb = get_embedding(dated)
            supabase.table("long_term_memories").insert({
                "user_id": user_id,
                "content": dated,
                "embedding": emb
            }).execute()
            return True
        except Exception as e:
            st.error(f"❌ Error guardant memòria: {e}")
            return False

    # =====================================================
    # 2. CERCAR A LONG TERM MEMORIES (Sensacions, OCR, Fets)
    # =====================================================
    def search_long_term_memories(query_text, limit=5):
        """Cerca memòries rellevants (Sensacions, OCR, dades personals)"""
        try:
            query_emb = get_embedding(query_text)
            res = supabase.rpc("match_memories", {
                "query_embedding": query_emb,
                "match_threshold": 0.4,
                "match_count": limit,
                "p_user_id": user_id
            }).execute()
            
            # ✅ CORREGIT: afegit .data
            if res.data:
                return [row["content"] for row in res.data]
            return []
        except Exception as e:
            st.warning(f"⚠️ Error cercant memòria vectorial: {e}")
            return []

    # =====================================================
    # 3. CARREGAR CONVERSES RECIENTS (SQL)
    # =====================================================
    def get_recent_messages(limit=20):
        """Carrega els últims missatges de TOTES les converses de l'usuari"""
        try:
            convs = supabase.table("conversations").select("id").eq("user_id", user_id).execute()
            # ✅ CORREGIT: afegit .data
            if not convs.data: return []
            
            all_ids = [c['id'] for c in convs.data]
            msgs = supabase.table("messages").select("*").in_("conversation_id", all_ids).order("created_at", desc=True).limit(limit).execute()
            
            return msgs.data if msgs.data else []
        except Exception as e:
            st.warning(f"⚠️ Error carregant missatges: {e}")
            return []

    # Inicialitzar conversa
    if st.session_state.conv_id is None:
        res = supabase.table("conversations").insert({
            "user_id": user_id, "title": "Nova", "updated_at": datetime.now().isoformat()
        }).execute()
        st.session_state.conv_id = res.data[0]['id']
        st.session_state.msgs = []

    if not st.session_state.msgs:
        st.session_state.msgs = supabase.table("messages").select("*").eq("conversation_id", st.session_state.conv_id).order("created_at").execute().data

    st.title("💬 Xat IA - Memòria Total")
    st.caption("🧠 Recorda: Converses + Sensacions + Imatges + Fitxers")

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
    
    # Botons de debug
    col_debug1, col_debug2, col_debug3 = st.columns(3)
    with col_debug1:
        if st.button("🔍 Veure dades a SQL"):
            mem = supabase.table("long_term_memories").select("*", count="exact").eq("user_id", user_id).execute()
            sens = supabase.table("training_sensations").select("*", count="exact").eq("user_id", user_id).execute()
            st.info(f"📦 long_term_memories: {mem.count if hasattr(mem, 'count') else 0}")
            st.info(f"🏃 training_sensations: {sens.count if hasattr(sens, 'count') else 0}")
    with col_debug2:
        if st.button("🧪 Provar Memòria"):
            save_memory("Tinc 33 anys")
            save_memory("El meu gos es diu Lua")
            st.success("✅ Memòries de prova guardades!")
    with col_debug3:
        if st.button("📋 Veure memòries recents"):
            all_mems = supabase.table("long_term_memories").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(5).execute()
            # ✅ CORREGIT: afegit .data
            if all_mems.data:
                for i, m in enumerate(all_mems.data):
                    st.text_area(f"{i+1}. {m['created_at'][:10]}", m['content'], height=60, key=f"mem_{i}_{m.get('id', i)}")
            else:
                st.info("Cap memòria guardada")

    st.markdown("### 📎 Adjuntar fitxers")
    col_input, col_img, col_file = st.columns([3, 1, 1])
    
    with col_input:
        prompt = st.chat_input("Pregunta sobre running, lesions, objectius...")
    with col_img:
        uploaded_image = st.file_uploader("Imatge", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    with col_file:
        uploaded_file = st.file_uploader("CSV/Excel", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

    # Processar fitxer CSV/Excel
    if uploaded_file:
        with st.spinner(f"📊 Processant {uploaded_file.name}..."):
            process_uploaded_file(uploaded_file, user_id, save_memory)

    # Processar imatge amb OCR
    if uploaded_image:
        with st.spinner("🔍 Llegint text de la imatge..."):
            ocr_text = extract_text_from_image(uploaded_image)
            if ocr_text and "Error" not in ocr_text and "⚠️" not in ocr_text:
                save_memory(f"IMATGE PUJADA (OCR): {ocr_text}")
                st.info(f"📄 Text detectat: {ocr_text[:200]}{'...' if len(ocr_text) > 200 else ''}")
                # Mostrar imatge pujada
                with col_img:
                    st.image(uploaded_image, width=200)
            else:
                st.warning(f"⚠️ {ocr_text}")

    # Mostrar missatges del xat
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300, caption="📷 Imatge adjunta")
            st.markdown(m["content"])

    # =====================================================
    # PROCESSAR PROMPT DE L'USUARI
    # =====================================================
    if prompt:
        image_url = None
        
        # Pujar imatge a Storage (si n'hi ha)
        if uploaded_image:
            with st.spinner("Pujant imatge..."):
                ext = uploaded_image.name.split('.')[-1]
                fn = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("chat-images").upload(fn, uploaded_image.getvalue())
                image_url = supabase.storage.from_("chat-images").get_public_url(fn)

        # 1️⃣ GUARDAR A LA TAULA DE MISSATGES (SQL - conversa actual)
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user",
            "content": prompt,
            "image_url": image_url
        }).execute()

        # 2️⃣ GUARDAR AUTOMÀTICAMENT A MEMÒRIA LLARG TERMINI (per recordar-ho sempre)
        save_memory(f"Usuari diu: {prompt}")

        with st.chat_message("assistant"):
            with st.spinner("🧠 Consultat memòria i pensant..."):
                # 3️⃣ OBTENIR CONTEXT COMBINAT
                
                # A. Memòria rellevant (Sensacions, OCR, Fets antics)
                long_term = search_long_term_memories(prompt, limit=5)
                memory_context = ""
                if long_term:
                    memory_context = "📂 DADES GUARDADES (Sensacions, Fets, OCR):\n"
                    for m in long_term:
                        memory_context += f"- {m}\n"
                    memory_context += "\n"
                
                # B. Conversa recent (El que s'ha dit al xat fa poc)
                recent_msgs = get_recent_messages(limit=15)
                chat_context = ""
                if recent_msgs:
                    chat_context = "💬 CONVERSA RECENT (últims missatges):\n"
                    for m in recent_msgs:
                        emoji = "👤" if m['role'] == 'user' else "🤖"
                        chat_context += f"{emoji} {m['content']}\n"
                    chat_context += "\n"

                # 4️⃣ CONSTRUIR PROMPT DEL SISTEMA
                sys_msg = {
                    "role": "system",
                    "content": (
                        "Ets un assistent personal expert en running i salut.\n\n"
                        f"{memory_context}"
                        f"{chat_context}"
                        "INSTRUCCIONS CRÍTIQUES:\n"
                        "1. Si l'usuari pregunta per dades concretes (hores de son, fatiga, edat, cotxe, lesions, etc.),"
                        " busca primer a 'DADES GUARDADES'.\n"
                        "2. Si l'usuari fa una pregunta de continuïtat o segueix un tema, mira 'CONVERSA RECENT'.\n"
                        "3. Si trobes la informació, RESPON UTILITZANT LES DADES CONCRETES.\n"
                        "4. Si no hi ha informació rellevant, digues 'No tinc aquesta informació guardada'.\n"
                        "5. Respon sempre en català, de forma clara i directa."
                    )
                }
                
                # Historial de la conversa actual (últims 8 missatges)
                current_history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.msgs[-8:]]
                
                # Combinar system prompt + historial actual
                history = [sys_msg] + current_history

                try:
                    res = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=history,
                        temperature=0.7
                    )
                    ans = res.choices[0].message.content
                    st.markdown(ans)
                    
                    # Guardar resposta a SQL
                    st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
                    supabase.table("messages").insert({
                        "conversation_id": st.session_state.conv_id,
                        "role": "assistant",
                        "content": ans
                    }).execute()
                    
                except Exception as e:
                    st.error(f"❌ ERROR IA: {str(e)}")
