# 🎤 Offline Multilingual Speech Transcription System

**Supports English • Spanish • Hindi | Works Offline | Learns New Words Over Time**

---

## 📌 Project Overview

This application records live microphone audio, performs offline speech recognition using VOSK, and supports:

- Real-time transcription (English, Spanish, Hindi)
- Offline recognition (No internet required)
- Stores transcripts + audio clips locally
- Detects unknown words
- When internet is available:
  - Fetches meaning using LibreTranslate
  - Moves words to a learned dictionary
  - Supports incremental learning
- Includes a web dashboard to monitor results

---

## 🛠️ Tech Stack

- **🗣️ Speech Recognition** — Vosk
- **🎧 Audio Input** — SoundDevice
- **🧠 Language Detection** — langdetect
- **🌍 Translation (online only)** — LibreTranslate API (self-hosted via Docker)
- **🗄 Database** — SQLite
- **🌐 Backend UI** — Flask
- **🎵 Audio Storage** — .wav

---

## ✔️ Features

### 🔹 Offline Features
- Real-time microphone listening
- Recognizes: English (en), Spanish (es), Hindi (hi)
- Saves: Text transcription, Language, Timestamp, Audio file

### 🔹 Unknown Word Handling
- Finds unknown words
- Stores in DB under `unknown_words`
- No internet needed

### 🔹 Online Validation (When Internet Available)
- Validates unknown words
- Translates meaning to English
- Moves to `learned_words`
- Deletes from `unknown_words`

### 🔹 Incremental Learning
- System remembers learned words
- Prevents repeating unknown words
- Only learns EN / ES / HI words

---

## 🚀 Setup Instructions (Run Locally)

### 1️⃣ Clone Repository
```bash
git clone https://github.com/AkhilBejjanki/audio-to-text-project4-save-audio-files-with-hindi-eng-and-spanish
cd audio-to-text-project
```

### 2️⃣ Install Dependencies
Make sure Python 3.8+ is installed:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3️⃣ Download Speech Models
Download these models and place in project root:

| Language | Model |
|----------|-------|
| English | `vosk-model-small-en-us-0.15` |
| Spanish | `vosk-model-small-es-0.42` |
| Hindi | `vosk-model-small-hi-0.22` |

**Download from:** https://alphacephei.com/vosk/models

**Folder structure should look like:**
```
project/
├── vosk-model-small-en-us-0.15/
├── vosk-model-small-es-0.42/
├── vosk-model-small-hi-0.22/
├── app.py
├── transcriber.py
├── templates/
│   └── index.html
├── requirements.txt
└── README.md
```

### 4️⃣ Setup Translation (Required for Online Learning)

We use **LibreTranslate Docker Container**. Start the Docker Translate Server:

```bash
docker run -it -p 5001:5000 libretranslate/libretranslate
```

This runs local translation endpoint: `http://127.0.0.1:5001/translate`

> **Note:** If port 5000 is busy, we already fixed it using `5001:5000`

### 5️⃣ Run Application
```bash
python app.py
```

You will see:
```
Transcriber + Retry worker running...
Listening...
Running on http://127.0.0.1:8000
```

**Open in browser:** http://127.0.0.1:8000

---

## 🖥 Web Dashboard Features

**Shows:**
- Live transcriptions
- Timestamp
- Language
- Audio playback

**Can:**
- ✔ Filter by language
- ✔ Download TXT
- ✔ Download CSV

---

## 🗄 Database Info

**SQLite DB file:** `transcriptions.db`

### Tables

**transcripts**
| Column | Description |
|--------|-------------|
| id | primary key |
| timestamp | recorded time |
| language | detected language |
| text | recognized sentence |
| audio_file | saved wav file path |

**unknown_words**
- Stores unrecognized or new vocabulary

**learned_words**
- Stores validated + translated vocabulary

---

## 📡 API Endpoints

- **Get Recent Transcriptions**
  ```
  GET /data?lang=all&limit=20
  ```

- **Download Text**
  ```
  GET /download/txt
  ```

- **Download CSV**
  ```
  GET /download/csv
  ```

- **View Learned Words (JSON)**
  ```
  GET /learned
  ```

- **View Unknown Words (JSON)**
  ```
  GET /unknown
  ```

---

## 🧪 Testing Guide

### ✅ Case 1 — Offline Mode
1. Turn OFF WiFi
2. Stop Docker translate
3. Speak phrases:
   - "Hello how are you"
   - "Hola amigo"
   - "नमस्ते दुनिया"

**Expected:**
- Transcripts stored
- `unknown_words` collected
- `learned_words` NOT updated

### 🌐 Case 2 — Online Mode
1. Turn ON Internet
2. Start Docker
3. System will:
   - Translate unknown words
   - Move them to `learned_words`
   - Clear `unknown_words`

**Expected output in terminal:**
```
Learned new word: hello
Learned new word: amigo
```

---

## ❗ Troubleshooting

### 🔴 Port Already in Use
**Docker error:** `address already in use`

**Solution:**
```bash
docker run -it -p 5001:5000 libretranslate/libretranslate
```

### 🔴 LibreTranslate slow / crashes
Happens first time while downloading models. **Wait.**

### 🔴 Database Locked
Rare. Restart app:
```bash
CTRL + C
python app.py
```

### 🔴 No microphone
Ensure permissions enabled on your system.

---

## 📝 License

MIT License - Feel free to use this project for educational and commercial purposes.

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

---

**Happy transcribing! 🎙️**
