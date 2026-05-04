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
        return "⚠️ pytesseract no instal·lat. Afegeix-lo a requirements.txt"
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
        """Versió simplificada i amb DEBUG"""
        try:
            extraction = client.chat.completions.create(
                model="qwen-turbo",
                messages=[{
                    "role": "user",
                    "content": f"""Extreu NOMÉS fets personals rellevants (edat, vehicle, lesions, objectius, dades físiques).
Si no hi ha cap fet, respon "CAP".
Si n'hi ha, respon amb una llista separada per comes.

Exemple: "Tinc 32 anys" -> "32 anys"
Exemple: "Vull córrer" -> "Objectiu: córrer"

Text a analitzar:
{user_message}
"""
                }],
                temperature=0,
                max_tokens=100
            )
            
            content = extraction.choices[0].message.content.strip()
            
            # DEBUG: Mostrar què ha detectat la IA
            st.info(f"🔍 IA detecta fets: '{content}'")

            if content.upper() != "CAP" and content:
                # Separar per comes o salts de línia
                facts = [f.strip() for f in content.replace(',', '\n').split('\n') if f.strip()]
                for fact in facts:
                    if fact:
                        save_memory(fact)
                        st.success(f"💾 Guardat: {fact}")
                
        except Exception as e:
            st.error(f"❌ Error extracció memòria: {str(e)}")

    # =====================================================
    # 🔍 FUNCIÓ DE MEMÒRIA CORREGIDA (CÀRREGA DIRECTA)
    # =====================================================
    def get_relevant_memories(query_text, limit=50):
        """CARREGA TOTES LES MEMÒRIES DE L'USUARI (solució definitiva)"""
        try:
            # Obtenim TOTES les memòries ordenades per data (les més recents primer)
            all_memories = supabase.table("long_term_memories").select("*").eq(
                "user_id", user_id
            ).order("created_at", desc=True).limit(limit).execute()
            
            if all_memories.data:
                memories = [row["content"] for row in all_memories.data]
                st.info(f"📚 Carregades {len(memories)} memòries de la BD")
                return memories
            else:
                st.warning("⚠️ Cap memòria trobada a la BD")
                return []
                
        except Exception as e:
            st.error(f"❌ ERROR carregant memòries: {str(e)}")
            return []

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

    st.title("💬 Xat IA - Entrenador de Running")
    st.caption("Memòria intel·ligent activa: recordo el teu historial + llegeixo imatges 📸")

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
        if st.button(" Provar Memòria"):
            save_memory("Tinc 32 anys")
            save_memory("El meu cotxe és un Toyota amb matrícula ABC-1234")
            st.info("✅ Memòries de prova guardades!")
    with col_test2:
        if st.button("📊 Veure Estadístiques"):
            total_mem = supabase.table("long_term_memories").select("*", count="exact").eq("user_id", user_id).execute()
            st.metric("Total memòries", total_mem.count if hasattr(total_mem, 'count') else 0)
    with col_test3:
        if st.button("📋 Veure memòries"):
            all_mems = supabase.table("long_term_memories").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(20).execute()
            if all_mems.data:
                for i, mem in enumerate(all_mems.data):
                    st.text_area(
                        f" {mem['created_at'][:10]}", 
                        mem['content'], 
                        height=80,
                        key=f"mem_{i}_{mem.get('id', i)}"
                    )
            else:
                st.info("Cap memòria guardada encara")

    st.markdown("###  Adjuntar fitxers")
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
        with st.spinner("🔍 Llegint text de la imatge..."):
            ocr_text = extract_text_from_image(uploaded_image)
            if ocr_text and "Error" not in ocr_text and "⚠️" not in ocr_text:
                save_memory(f"IMATGE PUJADA (OCR): {ocr_text}")
                st.info(f"📄 Text detectat: {ocr_text[:200]}{'...' if len(ocr_text) > 200 else ''}")
            else:
                st.warning(f"⚠️ {ocr_text}")

    # Mostrar missatges
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            if m.get("image_url"):
                st.image(m["image_url"], width=300, caption="📷 Imatge adjunta")
            st.markdown(m["content"])

    # =====================================================
    # PROCESSAR PROMPT AMB MEMÒRIA GARANTIDA
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

        st.session_state.msgs.append({"role": "user", "content": prompt, "image_url": image_url})
        supabase.table("messages").insert({
            "conversation_id": st.session_state.conv_id,
            "role": "user",
            "content": prompt,
            "image_url": image_url
        }).execute()

        # 🔍 CARREGAR TOTES LES MEMÒRIES
        memories = get_relevant_memories(prompt, limit=50)

        if memories:
            context = "HISTORIAL COMPLET DE L'USUARI (dades més recents primer):\n\n"
            for i, m in enumerate(memories):
                context += f"{i+1}. {m}\n"
            
            with st.expander("👁️ Veure dades que rep la IA"):
                st.text(context[:2000])
        else:
            context = "No hi ha historial previ de l'usuari."

        sys_msg = {
            "role": "system",
            "content": (
                "Ets un assistent personal expert. "
                f"Tens accés a l'historial COMPLET de l'usuari:\n\n{context}\n\n"
                "INSTRUCCIONS CRÍTIQUES:\n"
                "1. LLEGEIX atentament TOTES les dades de dalt. Les primeres són les més recents.\n"
                "2. Si hi ha dades CONTRADICTÒRIES (ex: '30 anys' i '32 anys'), UTILITZA LA MÉS RECENT (la que apareix primer).\n"
                "3. Si l'usuari pregunta per 'cotxe', 'matrícula', 'multa', 'anys', 'cabell', etc., BUSCA AQUESTES PARAULES a l'historial.\n"
                "4. Si trobes la informació, RESPON UTILITZANT LES DADES CONCRETES de l'historial.\n"
                "5. Cita la font: 'Segons les teves dades guardades el [data]...'\n"
                "6. Si no hi ha informació rellevant, digues 'No tinc aquesta informació guardada'.\n"
                "7. Respon sempre en català, de forma clara i directa."
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
                temperature=0.3
            )
            ans = res.choices[0].message.content
            st.markdown(ans)
            
            st.session_state.msgs.append({"role": "assistant", "content": ans, "image_url": None})
            supabase.table("messages").insert({
                "conversation_id": st.session_state.conv_id,
                "role": "assistant",
                "content": ans
            }).execute()
            
            # Intentar extreure memòries (amb el debug ara visible)
            extract_and_save_memories(prompt, ans)
            
        except Exception as e:
            st.error(f"❌ ERROR IA: {str(e)}")

    # =====================================================
    # BOTÓ EXTRA PER FORÇAR GUARDAR (DEBUG)
    # =====================================================
    if prompt:
        if st.button("💾 Forçar guardar text actual com a memòria"):
            save_memory(prompt)
            st.success("✅ Text guardat manualment!")
            st.rerun()
