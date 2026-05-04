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
    try:
        import pytesseract
        img = Image.open(image_file)
        text = pytesseract.image_to_string(img, lang='cat+spa+eng')
        return text.strip() if text.strip() else "Imatge sense text detectable"
    except ImportError:
        return "️ pytesseract no instal·lat"
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

    # =====================================================
    # 🔑 NOU: CARREGAR HISTORIAL GLOBAL DE TOTES LES CONVERSES
    # =====================================================
    def get_global_context(user_id, current_conv_id, limit=15):
        """Carrega els últims missatges de TOTES les converses de l'usuari"""
        try:
            # 1. Obtenir IDs de totes les converses de l'usuari
            convs = supabase.table("conversations").select("id").eq("user_id", user_id).execute()
            all_conv_ids = [c['id'] for c in convs.data]
            
            # 2. Filtrar només les converses que NO són l'actual (per no duplicar)
            other_conv_ids = [cid for cid in all_conv_ids if cid != current_conv_id]
            
            if not other_conv_ids:
                return []
            
            # 3. Carregar últims missatges d'aquestes altres converses
            recent_msgs = supabase.table("messages").select("*").in_("conversation_id", other_conv_ids).order("created_at", desc=True).limit(limit).execute()
            
            if recent_msgs.data:
                return recent_msgs.data # Retorna els més recents primer
            return []
        except Exception as e:
            st.warning(f"⚠️ No s'ha pogut carregar l'historial global: {e}")
            return []

    # =====================================================
    # 🔑 NOU: GUARDAR AUTOMÀTICAMENT TOTS ELS MISSATGES DE L'USUARI
    # =====================================================
    def auto_save_user_message(text):
        """Guarda el missatge de l'usuari directament a long_term_memories per a futur"""
        if len(text) > 10: # No guardar coses molt curtes com "hola"
            save_memory(f"Usuari va dir: {text}")

    def process_uploaded_file(uploaded_file):
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
            st.success(f"✅ Fitxer processat: {len(df)} files guardades")
            return True
        except Exception as e:
            st.error(f"❌ Error processant fitxer: {str(e)}")
            return False

    # Inicialitzar conversa
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

    st.title("💬 Xat IA - Memòria Total")
    st.caption("🧠 Recorda TOTES les converses + imatges + fitxers")

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
    
    # Botons de gestió
    col_test1, col_test2, col_test3 = st.columns(3)
    with col_test1:
        if st.button("🧪 Provar Memòria"):
            save_memory("Tinc 32 anys")
            save_memory("M'agrada el sushi")
            st.info("✅ Memòries de prova guardades!")
    with col_test2:
        if st.button("📊 Estadístiques"):
            total_mem = supabase.table("long_term_memories").select("*", count="exact").eq("user_id", user_id).execute()
            st.metric("Total memòries", total_mem.count if hasattr(total_mem, 'count') else 0)
    with col_test3:
        if st.button("📋 Veure memòries"):
            all_mems = supabase.table("long_term_memories").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute()
            if all_mems.data:
                for i, mem in enumerate(all_mems.data):
                    st.text_area(f"📅 {mem['created_at'][:10]}", mem['content'], height=60, key=f"mem_{i}_{mem.get('id', i)}")
            else:
                st.info("Cap memòria guardada encara")

    st.markdown("### 📎 Adjuntar fitxers")
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        prompt = st.chat_input("Pregunta sobre running, lesions, objectius...")
    
    with col2:
        uploaded_image = st.file_uploader("Imatge", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    
    with col3:
        uploaded_file = st.file_uploader("CSV/Excel", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

    # Processar CSV/Excel
    if uploaded_file:
        with st.spinner(f"📊 Processant {uploaded_file.name}..."):
            if process_uploaded_file(uploaded_file):
                st.success("✅ Dades guardades a la memòria!")

    # Processar IMATGE amb OCR
    if uploaded_image:
        with st.spinner(" Llegint text de la imatge..."):
            ocr_text = extract_text_from_image(uploaded_image)
            if ocr_text and "Error" not in ocr_text and "⚠️" not in ocr_text:
                save_memory(f"IMATGE PUJADA (OCR): {ocr_text}")
                st.info(f"📄 Text detectat: {ocr_text[:200]}...")
            else:
                st.warning(f"️ {ocr_text}")

    # Mostrar missatges
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300, caption="📷 Imatge adjunta")
            st.markdown(m["content"])

    # =====================================================
    # PROCESSAR PROMPT AMB MEMÒRIA GLOBAL
    # =====================================================
    if prompt:
        image_url = None
        
        # Pujar imatge a Storage
        if uploaded_image:
            with st.spinner("Pujant imatge..."):
                ext = uploaded_image.name.split('.')[-1]
                fn = f"{user_id}/{st.session_state.conv_id}/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("chat-images").upload(fn, uploaded_image.getvalue())
                image_url = supabase.storage.from_("chat-images").get_public_url(fn)
                st.image(uploaded_image, width=300)

        # 1. Guardar missatge actual
        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user",
            "content": prompt,
            "image_url": image_url
        }).execute()

        # 2. Guardar automàticament a memòria a llarg termini (per si preguntes d'aquí un mes)
        auto_save_user_message(prompt)

        # 3. Obtenir Context Global (Altres converses)
        with st.spinner("🧠 Recuperant memòria d'altres converses..."):
            global_history = get_global_context(user_id, st.session_state.conv_id, limit=15)
            
            # Formatejar historial global
            global_context_text = ""
            if global_history:
                global_context_text = "HISTORIAL RECENT D'ALTRES CONVERSES:\n"
                for msg in global_history:
                    role_emoji = "👤" if msg['role'] == 'user' else "🤖"
                    global_context_text += f"{role_emoji} {msg['content']}\n"
            
            # 4. Construir Prompt del Sistema
            sys_msg = {
                "role": "system",
                "content": (
                    "Ets un assistent personal expert. "
                    "Tens accés a l'historial recent d'altres converses de l'usuari:\n\n"
                    f"{global_context_text}\n\n"
                    "INSTRUCCIONS: "
                    "1. Utilitza aquest historial per recordar coses que l'usuari ha dit abans. "
                    "2. Si l'usuari pregunta per alguna dada (edat, cotxe, preferències) i la veus a l'historial, RESPON UTILITZANT-LA. "
                    "3. Si l'usuari diu alguna cosa nova (ex: 'Tinc 32 anys'), recorda-ho per a la propera vegada. "
                    "4. Respon sempre en català."
                )
            }
            
            # Historial de la conversa ACTUAL (últims 8 missatges)
            current_history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.msgs[-8:]]
            
            # Combinar: System + Global Context (com a missatge d'usuari fictici) + Current History
            full_history = [sys_msg]
            if global_context_text:
                full_history.append({"role": "user", "content": "[MEMÒRIA DEL SISTEMA] Aquest és el teu historial recent d'altres xats:"})
                full_history.append({"role": "assistant", "content": global_context_text})
            
            full_history.extend(current_history)

        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                try:
                    res = client.chat.completions.create(
                        model="qwen-turbo",
                        messages=full_history,
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
                    
                except Exception as e:
                    st.error(f"❌ ERROR IA: {str(e)}")
