from flask import Flask, render_template, jsonify, Response, send_from_directory, request
import sqlite3
import csv
import io
import os
import transcriber

app = Flask(__name__)

# Start background transcriber
transcriber.start_transcriber()

DB_FILE = "transcriptions.db"
AUDIO_DIR = "audio_clips"

def get_transcripts(limit=None, lang=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if lang and lang != "all":
        query = "SELECT timestamp, language, text, audio_file FROM transcripts WHERE language=? ORDER BY id DESC"
        params = (lang,)
    else:
        query = "SELECT timestamp, language, text, audio_file FROM transcripts ORDER BY id DESC"
        params = ()
    if limit:
        query += f" LIMIT {limit}"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    return [{"timestamp": r[0], "language": r[1], "text": r[2], "audio_file": r[3]} for r in rows]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/data")
def data():
    lang = request.args.get("lang", "all")
    return jsonify(get_transcripts(limit=20, lang=lang))

# 🔹 Download TXT
@app.route("/download/txt")
def download_txt():
    transcripts = get_transcripts()
    output = io.StringIO()
    for t in transcripts:
        output.write(f"{t['timestamp']} [{t['language']}] - {t['text']}\n")
    return Response(output.getvalue(),
                    mimetype="text/plain",
                    headers={"Content-Disposition": "attachment;filename=transcripts.txt"})

# 🔹 Download CSV
@app.route("/download/csv")
def download_csv():
    transcripts = get_transcripts()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Language", "Transcript", "AudioFile"])
    for t in transcripts:
        writer.writerow([t['timestamp'], t['language'], t['text'], t['audio_file']])
    return Response(output.getvalue(),
                    mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=transcripts.csv"})


# offline words
@app.route('/offline')
def get_offline():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, word, language, timestamp 
        FROM unknown_words
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "word": r[1],
            "language": r[2],
            "timestamp": r[3]
        } for r in rows
    ])

# unknown words 
@app.route("/unknown")
def get_unknown():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, word, language, timestamp 
        FROM unknown_words 
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "word": r[1],
            "language": r[2],
            "timestamp": r[3]
        } for r in rows
    ])


# learned words
@app.route("/learned")
def get_learned():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, word, detected_language, meaning, timestamp
        FROM learned_words
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "word": r[1],
            "language": r[2],
            "meaning": r[3],
            "timestamp": r[4]
        } for r in rows
    ])

@app.route("/generated")
def get_generated():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT base_word, generated_word, generation_type, language, timestamp
        FROM generated_words
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "base_word": r[0],
            "generated_word": r[1],
            "type": r[2],
            "language": r[3],
            "timestamp": r[4]
        } for r in rows
    ])


# 🔹 Serve audio files
@app.route("/audio_clips/<path:filename>")
def download_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
