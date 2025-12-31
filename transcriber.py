import os, queue, json, sqlite3, time, threading, wave
import sounddevice as sd
import vosk
from langdetect import detect
from google.cloud import translate_v2 as translate
import requests

# Paths to models
MODEL_PATHS = {
    "en": "vosk-model-small-en-us-0.15",
    "es": "vosk-model-small-es-0.42",
    "hi": "vosk-model-small-hi-0.22"
}

ALLOWED_LANGS = {"en", "es", "hi"}


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

    # enable concurrent reads/writes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            language TEXT,
            text TEXT,
            audio_file TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS unknown_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT,
            language TEXT,
            timestamp TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS learned_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT,
            detected_language TEXT,
            meaning TEXT,
            validated INTEGER DEFAULT 1,
            timestamp TEXT
        )
    """)

    conn.commit()
    return conn

conn = init_db()

LEARNED_CACHE = set()

def load_learned_cache():
    global LEARNED_CACHE
    rows = conn.execute("SELECT word FROM learned_words").fetchall()
    LEARNED_CACHE = {r[0].lower() for r in rows}
    print(f"Loaded {len(LEARNED_CACHE)} learned words into memory")

load_learned_cache()


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
    
def find_unknown_words(text):
    global LEARNED_CACHE
    
    base_known = {"hello", "hola", "namaste", "kaise", "ho"}

    words = text.split()
    unknown = []

    for w in words:
        wl = w.lower()

        if wl in base_known:
            continue

        if wl in LEARNED_CACHE:
            # print(f"[LEARNED] Skipping known word → {wl}")
            continue

        unknown.append(w)

    return unknown


def save_unknown_words(words, lang):
    if lang not in ALLOWED_LANGS:
        return

    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    for w in words:
        existing = conn.execute(
            "SELECT word FROM unknown_words WHERE word=? AND language=?",
            (w, lang)
        ).fetchone()

        if existing:
            continue

        conn.execute(
            "INSERT INTO unknown_words (word, language, timestamp) VALUES (?, ?, ?)",
            (w, lang, ts)
        )

    conn.commit()


def retry_validation_worker():
    print("Background retry worker started...")
    while True:
        try:
            validate_unknown_words()   # try moving unknown → learned
        except Exception as e:
            print("Retry worker error:", e)

        time.sleep(10)   # run every 10 seconds


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
                        unknown = find_unknown_words(text)
                        if unknown:
                            print("Unknown words:", unknown)
                            save_unknown_words(unknown, detected_lang)



TRANSLATE_SERVERS = [
    "http://127.0.0.1:5001/translate"
]

def translate_word(word):
    payload = {
        "q": word,
        "source": "auto",
        "target": "en",
        "format": "text"
    }

    headers = {"Content-Type": "application/json"}

    for url in TRANSLATE_SERVERS:
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=8)

            if "application/json" not in res.headers.get("Content-Type", ""):
                print("Non JSON from:", url)
                continue

            data = res.json()
            return data.get("translatedText", "N/A")

        except Exception as e:
            print("Translation Error with", url, "=>", e)

    return "N/A"




def validate_and_store_word(word, lang):

    if lang not in ALLOWED_LANGS:
        return
    
    # avoid duplicates
    existing = conn.execute(
        "SELECT word FROM learned_words WHERE word=? AND detected_language=?",
        (word, lang)
    ).fetchone()

    if existing:
        return

    meaning = translate_word(word)

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO learned_words (word, detected_language, meaning, timestamp) VALUES (?, ?, ?, ?)",
        (word, lang, meaning, ts)
    )
    conn.commit()

    LEARNED_CACHE.add(word.lower())
    print("Learned new word:", word)



def internet_available():
    try:
        requests.get("https://www.google.com", timeout=2)
        return True
    except:
        return False


def validate_unknown_words():
    if not internet_available():
        return

    cursor = conn.execute("SELECT id, word, language FROM unknown_words")
    rows = cursor.fetchall()

    for rid, word, lang in rows:
        validate_and_store_word(word, lang)
        conn.execute("DELETE FROM unknown_words WHERE id=?", (rid,))

    conn.commit()


def start_transcriber():
    t = threading.Thread(target=transcribe_loop, daemon=True)
    t.start()

    r = threading.Thread(target=retry_validation_worker, daemon=True)
    r.start()

    print("Transcriber + Retry worker running...")
