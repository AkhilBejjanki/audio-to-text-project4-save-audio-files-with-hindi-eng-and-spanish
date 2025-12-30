import os, queue, json, sqlite3, time, threading, wave
import sounddevice as sd
import vosk
from langdetect import detect

# Paths to models
MODEL_PATHS = {
    "en": "vosk-model-small-en-us-0.15",
    "es": "vosk-model-small-es-0.42",
    "hi": "vosk-model-small-hi-0.22"
}

recognizers = {}
for lang, path in MODEL_PATHS.items():
    if not os.path.exists(path):
        raise FileNotFoundError(f"Download model for {lang} from: https://alphacephei.com/vosk/models")
    model = vosk.Model(path)
    recognizers[lang] = vosk.KaldiRecognizer(model, 16000)

DB_FILE = "transcriptions.db"
AUDIO_DIR = "audio_clips"
os.makedirs(AUDIO_DIR, exist_ok=True)

q = queue.Queue()

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            language TEXT,
            text TEXT,
            audio_file TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()

def save_transcript(text, lang, audio_path=None):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO transcripts (timestamp, language, text, audio_file) VALUES (?, ?, ?, ?)",
        (ts, lang, text, audio_path)
    )
    conn.commit()

def save_audio_chunk(raw_data, lang):
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{lang}_{ts}.wav"
    filepath = os.path.join(AUDIO_DIR, filename)
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(raw_data)
    return filepath

def detect_language_from_text(text):
    try:
        return detect(text)
    except:
        return "unknown"

def audio_callback(indata, frames, time, status):
    if status:
        print("Audio status:", status, flush=True)
    q.put(bytes(indata))

def transcribe_loop():
    with sd.RawInputStream(samplerate=16000, blocksize=8000,
                           dtype="int16", channels=1,
                           callback=audio_callback):
        print("🎤 Listening... (checking EN, ES, HI)")
        while True:
            data = q.get()
            for lang, rec in recognizers.items():
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        detected_lang = detect_language_from_text(text)
                        audio_path = save_audio_chunk(data, lang)
                        print(f"[{lang.upper()}] Detected: {detected_lang} → {text}  🎵 saved {audio_path}")
                        save_transcript(text, detected_lang, audio_path)

def start_transcriber():
    t = threading.Thread(target=transcribe_loop, daemon=True)
    t.start()
