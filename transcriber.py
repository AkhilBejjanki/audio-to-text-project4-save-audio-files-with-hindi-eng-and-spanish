import os
import queue
import json
import sqlite3
import time
import threading
import wave
import requests
import sounddevice as sd
import vosk
from langdetect import detect

# CONFIG

MODEL_PATHS = {
    "en": "vosk-model-small-en-us-0.15",
    "es": "vosk-model-small-es-0.42",
    "hi": "vosk-model-small-hi-0.22"
}

ALLOWED_LANGS = {"en", "es", "hi"}
DB_FILE = "transcriptions.db"
AUDIO_DIR = "audio_clips"
TRANSLATE_SERVERS = ["http://127.0.0.1:5001/translate"]

GENERATION_RULES = {
    "en": [
        ("plural", lambda w: w + "s"),
        ("past", lambda w: w + "ed"),
        ("continuous", lambda w: w + "ing")
    ],
    "es": [
        ("plural", lambda w: w + "s"),
        ("plural_alt", lambda w: w + "es")
    ],
    "hi": [
        ("infinitive", lambda w: w + "ना"),
        ("present_m", lambda w: w + " रहा"),
        ("present_f", lambda w: w + " रही")
    ]
}


os.makedirs(AUDIO_DIR, exist_ok=True)
q = queue.Queue()


# LOAD SPEECH MODELS

recognizers = {}
for lang, path in MODEL_PATHS.items():
    if not os.path.exists(path):
        raise FileNotFoundError(f"Download model for {lang}: https://alphacephei.com/vosk/models")

    model = vosk.Model(path)
    recognizers[lang] = vosk.KaldiRecognizer(model, 16000)


# DATABASE INIT

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS generated_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_word TEXT,
            generated_word TEXT,
            language TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()
    return conn


conn = init_db()


# LEARNED WORD CACHE

LEARNED_CACHE = set()

def load_learned_cache():
    rows = conn.execute("SELECT word FROM learned_words").fetchall()
    for r in rows:
        LEARNED_CACHE.add(r[0].lower())
    print(f"Loaded {len(LEARNED_CACHE)} learned words into memory")

load_learned_cache()


# AUDIO + TRANSCRIPT

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


def save_transcript(text, lang, audio_path):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO transcripts (timestamp, language, text, audio_file) VALUES (?, ?, ?, ?)",
        (ts, lang, text, audio_path)
    )
    conn.commit()


# LANGUAGE + WORD HANDLING

def detect_language_from_text(text):
    try:
        return detect(text)
    except:
        return "unknown"


def find_unknown_words(text):
    base_known = {"hello", "hola", "namaste", "kaise", "ho"}
    unknown = []

    for w in text.split():
        wl = w.lower()
        if wl in base_known:
            continue
        if wl in LEARNED_CACHE:
            continue
        unknown.append(w)

    return unknown


def save_unknown_words(words, lang):
    if lang not in ALLOWED_LANGS:
        return

    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    for w in words:
        exists = conn.execute(
            "SELECT 1 FROM unknown_words WHERE word=? AND language=?",
            (w, lang)
        ).fetchone()

        if not exists:
            conn.execute(
                "INSERT INTO unknown_words (word, language, timestamp) VALUES (?, ?, ?)",
                (w, lang, ts)
            )

    conn.commit()


# TRANSLATION

def translate_word(word):
    payload = {
        "q": word,
        "source": "auto",
        "target": "en",
        "format": "text"
    }

    for url in TRANSLATE_SERVERS:
        try:
            res = requests.post(url, json=payload, timeout=8)
            if res.headers.get("Content-Type", "").startswith("application/json"):
                return res.json().get("translatedText", "N/A")
        except:
            pass

    return "N/A"


def internet_available():
    try:
        requests.get("https://www.google.com", timeout=2)
        return True
    except:
        return False


# INCREMENTAL LEARNING

def generate_variations(word, lang):
    variations = []

    rules = GENERATION_RULES.get(lang, [])

    for rule_name, rule_fn in rules:
        try:
            gen_word = rule_fn(word)
            variations.append((gen_word, rule_name))
        except:
            pass

    return variations



def save_generated_word(base, generated, lang, gen_type):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    existing = conn.execute("""
        SELECT 1 FROM generated_words
        WHERE base_word=? AND generated_word=? AND language=?
    """, (base, generated, lang)).fetchone()

    if existing:
        return

    conn.execute("""
        INSERT INTO generated_words
        (base_word, generated_word, generation_type, language, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (base, generated, gen_type, lang, ts))

    conn.commit()



def generate_from_learned(word, lang):
    variations = generate_variations(word, lang)

    if len(variations) < 2:
        return  # safety

    for gen_word, gen_type in variations:
        save_generated_word(word, gen_word, lang, gen_type)

    print(f"Generated {len(variations)} words from → {word}")



# VALIDATION PIPELINE

def validate_and_store_word(word, lang):
    if lang not in ALLOWED_LANGS:
        return

    exists = conn.execute(
        "SELECT 1 FROM learned_words WHERE word=? AND detected_language=?",
        (word, lang)
    ).fetchone()

    if exists:
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

    generate_from_learned(word, lang)


def validate_unknown_words():
    if not internet_available():
        return

    rows = conn.execute("SELECT id, word, language FROM unknown_words").fetchall()

    for rid, word, lang in rows:
        validate_and_store_word(word, lang)
        conn.execute("DELETE FROM unknown_words WHERE id=?", (rid,))

    conn.commit()


def retry_validation_worker():
    print("Background retry worker started...")
    while True:
        try:
            validate_unknown_words()
        except Exception as e:
            print("Retry error:", e)
        time.sleep(10)


# AUDIO LOOP

def audio_callback(indata, frames, time_info, status):
    if status:
        print(status)
    q.put(bytes(indata))


def transcribe_loop():
    with sd.RawInputStream(
        samplerate=16000,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=audio_callback
    ):
        print("🎤 Listening... (EN / ES / HI)")
        while True:
            data = q.get()
            for lang, rec in recognizers.items():
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        detected_lang = detect_language_from_text(text)
                        audio_path = save_audio_chunk(data, lang)
                        save_transcript(text, detected_lang, audio_path)

                        unknown = find_unknown_words(text)
                        if unknown:
                            print("Unknown words:", unknown)
                            save_unknown_words(unknown, detected_lang)


# START

def start_transcriber():
    threading.Thread(target=transcribe_loop, daemon=True).start()
    threading.Thread(target=retry_validation_worker, daemon=True).start()
    print("Transcriber + Retry worker running...")
