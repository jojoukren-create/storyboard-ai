# app.py
import streamlit as st
import requests
import json
import base64
import io
import zipfile
import time
import re
import wave
from datetime import timedelta

# PAGE CONFIG
st.set_page_config(page_title="Storyboard AI Pro", page_icon="🎬", layout="wide")

# CSS MOBILE
st.markdown("""
<style>
.block-container { padding-top: 1rem; padding-bottom: 5rem; }
div[data-testid="stVerticalBlock"] > button { width: 100%; height: 3em; }
.stTextArea textarea { font-size: 16px !important; }
div[data-testid="stSidebar"] .stTextInput input { background-color: #0e1117; border: 1px solid #ff4b4b; color: white; }
div[data-testid="stSidebar"] .stTextInput input:valid { border: 1px solid #4caf50; }
</style>
""", unsafe_allow_html=True)

# SESSION STATE
if "api_key_value" not in st.session_state: st.session_state.api_key_value = ""
if "generated_images" not in st.session_state: st.session_state.generated_images = {}
if "script_data" not in st.session_state: st.session_state.script_data = {}
if "open_vo_panel" not in st.session_state: st.session_state.open_vo_panel = False
if "last_audio_data" not in st.session_state: st.session_state.last_audio_data = None

# HELPERS
GEMINI_VOICES_MAPPED = ["Puck (Male)", "Charon (Male)", "Kore (Female)", "Fenrir (Male)", "Aoede (Female)", "Zephyr (Female)"]

def prepare_auth(url, key):
    return url, {"Content-Type": "application/json", "Authorization": f"Bearer {key.strip()}"} if "Bearer" not in key else key

def stitch_audio_pcm(pcm_chunks):
    try:
        combined_data = io.BytesIO()
        first_params = None
        for i, chunk_bytes in enumerate(pcm_chunks):
            try:
                with wave.open(io.BytesIO(chunk_bytes), 'rb') as w:
                    if i == 0: first_params = w.getparams()
                    combined_data.write(w.readframes(w.getnframes()))
            except: pass 
        if not first_params: return None
        final_wav = io.BytesIO()
        with wave.open(final_wav, 'wb') as w:
            w.setparams(first_params)
            w.writeframes(combined_data.getvalue())
        return final_wav.getvalue()
    except: return None

def split_text_smart(text):
    chunks = []; current_chunk = ""; sentences = re.split(r'(?<=[.!?])\s+', text)
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < 1500: current_chunk += sentence + " "
        else: chunks.append(current_chunk.strip()); current_chunk = sentence + " "
    if current_chunk: chunks.append(current_chunk.strip())
    return chunks

# API CALLS
def call_gemini_text(key, prompt):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    url, headers = prepare_auth(url, key)
    try:
        r = requests.post(url, headers=headers, json={"contents":[{"parts":[{"text":prompt}]}], "generationConfig":{"responseMimeType":"application/json"}}, timeout=45)
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = raw.replace("```json", "").replace("```", "")
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except: return None

def call_gemini_tts_chunk(key, text, voice_full):
    voice = voice_full.split(" (")[0]
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    url, headers = prepare_auth(url, key)
    try:
        r = requests.post(url, headers=headers, json={"contents":[{"parts":[{"text":text}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":voice}}}}}, timeout=30)
        if r.status_code == 200: return base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except: pass
    return None

def call_imagen(key, prompt):
    models = ["imagen-3.0-generate-001", "image-generation-002"]
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:predict"
        url, headers = prepare_auth(url, key)
        try:
            r = requests.post(url, headers=headers, json={"instances":[{"prompt":prompt}], "parameters":{"sampleCount":1,"aspectRatio":"9:16"}}, timeout=60)
            if r.status_code == 200: return base64.b64decode(r.json()["predictions"][0]["bytesBase64Encoded"])
        except: pass
    return None

def generate_audio_full(text, voice, key):
    chunks = split_text_smart(text)
    pcm_coll = []
    for c in chunks:
        pcm = call_gemini_tts_chunk(key, c, voice)
        if pcm: pcm_coll.append(pcm); time.sleep(0.2)
    return stitch_audio_pcm(pcm_coll)

# UI
with st.sidebar:
    st.title("📱 Storyboard AI")
    api_val = st.text_input("🔑 API Key", type="password")
    if api_val: st.session_state.api_key_value = api_val
    
    if st.session_state.api_key_value: st.success("API OK")
    else: st.error("API Kosong")

    st.markdown("### Setting")
    voice = st.selectbox("Suara", GEMINI_VOICES_MAPPED, index=5)
    lang = st.selectbox("Bahasa", ["Indonesia", "English"])
    story = st.text_area("Cerita", height=150)
    char = st.text_area("Karakter", height=70)
    
    if st.button("✨ BUILD", type="primary"):
        if not st.session_state.api_key_value: st.error("API Key!")
        else:
            with st.spinner("Processing..."):
                char_ins = f"Include: {char}" if char else ""
                prompt = f"""Create JSON storyboard. Story: {story}. Lang: {lang}. RULES: script={lang}, image_prompt=ENGLISH {char_ins}, camera=ENGLISH. Output JSON: {{ "scenes": [ {{ "id": 1, "script_text": "", "image_prompt": "", "camera_movement": "" }} ] }}"""
                data = call_gemini_text(st.session_state.api_key_value, prompt)
                if data:
                    st.session_state.script_data = data
                    st.session_state.generated_images = {}
                    st.session_state.last_audio_data = None
                    st.session_state.open_vo_panel = True
                    st.experimental_rerun()

if st.session_state.script_data:
    if st.session_state.open_vo_panel:
        sc = st.session_state.script_data.get("scenes", [])
        full_text = " ".join([s.get("script_text","") for s in sc])
        if st.button("🔊 Generate Audio"):
            wav = generate_audio_full(full_text, voice, st.session_state.api_key_value)
            if wav: st.session_state.last_audio_data = wav; st.success("Done!")
        
        if st.session_state.last_audio_data:
            st.audio(st.session_state.last_audio_data, format="audio/wav")
            st.download_button("⬇️ Audio", st.session_state.last_audio_data, "audio.wav", "audio/wav")
    
    for idx, s in enumerate(st.session_state.script_data.get("scenes", [])):
        st.markdown(f"**Scene {s['id']}**")
        st.caption(s.get('script_text'))
        st.code(s.get('image_prompt'))
        k = f"s_{idx}"
        if st.button(f"🎨 Gambar {s['id']}", key=f"g_{idx}"):
            img = call_imagen(st.session_state.api_key_value, s.get('image_prompt'))
            if img: st.session_state.generated_images[k] = [img]; st.experimental_rerun()
        if k in st.session_state.generated_images:
            st.image(st.session_state.generated_images[k][0])
            st.download_button("⬇️", st.session_state.generated_images[k][0], f"s{s['id']}.png")
        st.divider()
