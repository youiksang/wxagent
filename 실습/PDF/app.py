import os
import uuid
import json
from io import BytesIO
from flask import Flask, request, jsonify, Response, render_template
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)
# =========================
# Flask 설정
# =========================
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.config["JSON_AS_ASCII"] = False

jobs = {}
CHUNK_MAX_CHARS = 3000

# =========================
# OpenAI Client
# =========================
def get_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)

# =========================
# PDF 텍스트 추출
# =========================
def extract_pdf(file_bytes: bytes):
    reader = PdfReader(BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    full_text = "\n".join(pages).strip()
    return full_text, pages

# =========================
# chunk 분리
# =========================
def split_chunks(page_texts):
    chunks = []
    buffer = ""
    for t in page_texts:
        t = t.strip()
        if not t:
            continue
        if len(t) > CHUNK_MAX_CHARS:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            for i in range(0, len(t), CHUNK_MAX_CHARS):
                chunks.append(t[i:i + CHUNK_MAX_CHARS])
        elif len(buffer) + len(t) > CHUNK_MAX_CHARS:
            chunks.append(buffer)
            buffer = t
        else:
            buffer = buffer + "\n" + t if buffer else t
    if buffer:
        chunks.append(buffer)
    return chunks

# =========================
# 번역
# =========================
def translate(text, direction):
    if direction == "en-ko":
        prompt = "Translate English to Korean. Keep formatting."
    else:
        prompt = "Translate Korean to English. Keep formatting."
    
    client = get_client()
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.3
    )
    return res.choices[0].message.content or ""

# =========================
# UI
# =========================
@app.route("/")
def home():
    return render_template("index.html")

# =========================
# 업로드 + 분석
# =========================
@app.route("/api/start", methods=["POST"])
def start():
    if "pdf" not in request.files:
        return jsonify({"error": "PDF 파일 없음"}), 400
    
    f = request.files["pdf"]
    if not f.filename.endswith(".pdf"):
        return jsonify({"error": "PDF만 가능"}), 400
        
    direction = request.form.get("direction", "en-ko")
    file_bytes = f.read()
    
    try:
        full_text, pages = extract_pdf(file_bytes)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
        
    if not full_text:
        return jsonify({"error": "텍스트 없음"}), 400
        
    chunks = split_chunks(pages)
    job_id = str(uuid.uuid4())
    
    jobs[job_id] = {
        "filename": secure_filename(f.filename),
        "direction": direction,
        "chunks": chunks,
        "translated": "",
        "status": "ready"
    }
    
    return jsonify({
        "job_id": job_id,
        "total_chunks": len(chunks),
        "extracted_text": full_text
    })

# =========================
# 스트리밍 (SSE)
# =========================
@app.route("/api/stream/<job_id>")
def stream(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job 없음"}), 404

    def generate():
        job["status"] = "running"
        results = []
        try:
            total = len(job["chunks"])
            for i, chunk in enumerate(job["chunks"]):
                translated = translate(chunk, job["direction"])
                results.append(translated)
                job["translated"] = "\n\n".join(results)
                
                data = {
                    "progress": int((i + 1) / total * 100),
                    "current": i + 1,
                    "total": total,
                    "text": translated,
                    "done": i == total - 1
                }
                
                # ASCII 인코딩 오류 방지를 위해 utf-8 문자열 변환 후 bytes로 직접 전송
                json_str = json.dumps(data, ensure_ascii=False)
                yield f"data: {json_str}\n\n".encode('utf-8')

            job["status"] = "done"
        except Exception as e:
            job["status"] = "error"
            error_data = {'error': str(e)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n".encode('utf-8')

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )

# =========================
# 다운로드
# =========================
@app.route("/api/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job 없음"}), 404
    if job["status"] != "done":
        return jsonify({"error": "아직 완료 안됨"}), 400
        
    filename = os.path.splitext(job["filename"])[0] + ".txt"
    return Response(
        job["translated"],
        mimetype="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

# =========================
# 실행
# =========================
if __name__ == "__main__":
    app.run(debug=True, port=5001)
