"""Media Converter - Flask backend.

- បម្លែងឯកសារ (វីដេអូ/សំឡេង/ថតសំឡេង) ទៅជា MP3, WAV ឬ MP4 (ffmpeg)
- បម្លែងតំណ Facebook / YouTube (សម្រាប់មាតិកាដែលអ្នកមានសិទ្ធិទាញយក) ទៅជា MP3, WAV ឬ MP4 (yt-dlp + ffmpeg)
- រក្សាទុកក្នុងថត library/ ព្រមទាំងបញ្ជី index.json (រួមទាំងតំណដើម)
"""
import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

BASE = Path(__file__).resolve().parent
LIB = BASE / "library"
TMP = BASE / "tmp"
LIB.mkdir(exist_ok=True)
TMP.mkdir(exist_ok=True)
INDEX = LIB / "index.json"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB

lock = threading.Lock()
jobs = {}  # job_id -> {"status", "message", "item"}

MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "mp4": "video/mp4"}
FACEBOOK_HOSTS = ("facebook.com", "fb.watch", "fb.com")
YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


# ---------- library helpers ----------
def load_index():
    if not INDEX.exists():
        return []
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_index(items):
    INDEX.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add_item(title, src_path, fmt, source, url=None):
    item_id = uuid.uuid4().hex[:12]
    dest = LIB / f"{item_id}.{fmt}"
    shutil.move(str(src_path), dest)
    item = {
        "id": item_id,
        "title": title,
        "format": fmt,
        "size": dest.stat().st_size,
        "source": source,
        "url": url,
        "created": int(time.time()),
    }
    with lock:
        items = load_index()
        items.insert(0, item)
        save_index(items)
    return item


def clean_title(name):
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", name).strip()
    return (name or "media")[:120]


def host_matches(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def link_source(url):
    """Return 'facebook' / 'youtube' or None if the URL is not supported."""
    try:
        p = urlparse(url)
    except Exception:
        return None
    if p.scheme not in ("http", "https"):
        return None
    host = (p.hostname or "").lower()
    if host_matches(host, FACEBOOK_HOSTS):
        return "facebook"
    if host_matches(host, YOUTUBE_HOSTS):
        return "youtube"
    return None


# ---------- jobs ----------
def set_job(job_id, **kw):
    with lock:
        jobs.setdefault(job_id, {}).update(kw)


def has_video(src):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True,
    )
    return "video" in p.stdout


def run_ffmpeg(src, out, fmt):
    if fmt == "mp3":
        args = ["-vn", "-codec:a", "libmp3lame", "-b:a", "192k"]
    elif fmt == "wav":
        args = ["-vn", "-acodec", "pcm_s16le", "-ar", "44100"]
    else:  # mp4
        if not has_video(src):
            raise RuntimeError("ឯកសារនេះគ្មានវីដេអូទេ មិនអាចបម្លែងទៅជា MP4 បានទេ។ សូមជ្រើស MP3 ឬ WAV។")
        args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    p = subprocess.run(["ffmpeg", "-y", "-i", str(src), *args, str(out)], capture_output=True, text=True)
    if p.returncode != 0 or not out.exists():
        raise RuntimeError("ឯកសារនេះមិនមានសំឡេង ឬទ្រង់ទ្រាយមិនគាំទ្រ។")


def job_file(job_id, saved_path, original_name, fmt):
    workdir = saved_path.parent
    try:
        set_job(job_id, status="running", message=f"កំពុងបម្លែងទៅជា {fmt.upper()}...")
        out = workdir / f"out.{fmt}"
        run_ffmpeg(saved_path, out, fmt)
        title = clean_title(Path(original_name).stem)
        source = "record" if original_name.startswith("ថតសំឡេង") else "upload"
        item = add_item(title, out, fmt, source)
        set_job(job_id, status="done", message="បម្លែងរួចរាល់", item=item)
    except Exception as e:  # noqa: BLE001
        set_job(job_id, status="error", message=str(e))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def job_link(job_id, url, fmt, source):
    workdir = TMP / job_id
    workdir.mkdir(exist_ok=True)
    try:
        import yt_dlp

        set_job(job_id, status="running", message="កំពុងទាញយក និងបម្លែង...")
        opts = {
            "outtmpl": str(workdir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        if fmt == "mp4":
            opts.update({
                "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
            })
        else:
            pp = {"key": "FFmpegExtractAudio", "preferredcodec": fmt}
            if fmt == "mp3":
                pp["preferredquality"] = "192"
            opts.update({"format": "bestaudio/best", "postprocessors": [pp]})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        files = list(workdir.glob(f"*.{fmt}"))
        if not files:
            raise RuntimeError("មិនអាចទាញយកមាតិកានេះបានទេ។")
        title = clean_title(info.get("title") or f"{source}-media")
        item = add_item(title, files[0], fmt, source, url)
        set_job(job_id, status="done", message="បម្លែងរួចរាល់", item=item)
    except Exception:  # noqa: BLE001
        set_job(
            job_id,
            status="error",
            message="មិនអាចទាញយកបានទេ។ មាតិកាអាចជា Private ឬមិនអនុញ្ញាតឱ្យទាញយក ឬតំណមិនត្រឹមត្រូវ។",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------- routes ----------
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/convert/file")
def convert_file():
    fmt = (request.form.get("format") or "mp3").lower()
    if fmt not in MIME:
        return jsonify(error="ទ្រង់ទ្រាយមិនត្រឹមត្រូវ។"), 400
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="សូមជ្រើសរើសឯកសារ។"), 400
    job_id = uuid.uuid4().hex
    workdir = TMP / job_id
    workdir.mkdir()
    saved = workdir / "input.bin"
    f.save(saved)
    set_job(job_id, status="queued", message="កំពុងរង់ចាំ...")
    threading.Thread(target=job_file, args=(job_id, saved, f.filename, fmt), daemon=True).start()
    return jsonify(job=job_id)


@app.post("/api/convert/link")
def convert_link():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    fmt = (data.get("format") or "mp3").lower()
    if fmt not in MIME:
        return jsonify(error="ទ្រង់ទ្រាយមិនត្រឹមត្រូវ។"), 400
    if not data.get("confirm"):
        return jsonify(error="សូមបញ្ជាក់ថាអ្នកមានសិទ្ធិទាញយកមាតិកានេះ។"), 400
    source = link_source(url)
    if not source:
        return jsonify(error="សូមបិទភ្ជាប់តំណ Facebook ឬ YouTube ឱ្យត្រឹមត្រូវ។"), 400
    job_id = uuid.uuid4().hex
    set_job(job_id, status="queued", message="កំពុងរង់ចាំ...")
    threading.Thread(target=job_link, args=(job_id, url, fmt, source), daemon=True).start()
    return jsonify(job=job_id)


@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    with lock:
        j = jobs.get(job_id)
    if not j:
        abort(404)
    return jsonify(j)


@app.get("/api/library")
def library():
    with lock:
        items = load_index()
    for i in items:  # compatibility with older entries
        i.setdefault("format", "mp3")
        i.setdefault("url", None)
    return jsonify(items)


@app.get("/files/<item_id>")
def get_file(item_id):
    if not re.fullmatch(r"[0-9a-f]{12}", item_id):
        abort(404)
    item = next((i for i in load_index() if i["id"] == item_id), None)
    if not item:
        abort(404)
    fmt = item.get("format", "mp3")
    return send_from_directory(
        LIB, f"{item_id}.{fmt}", mimetype=MIME.get(fmt),
        as_attachment=request.args.get("dl") == "1",
        download_name=f"{item['title']}.{fmt}",
    )


@app.delete("/api/library/<item_id>")
def delete_item(item_id):
    if not re.fullmatch(r"[0-9a-f]{12}", item_id):
        abort(404)
    with lock:
        items = load_index()
        gone = next((i for i in items if i["id"] == item_id), None)
        save_index([i for i in items if i["id"] != item_id])
    if gone:
        (LIB / f"{item_id}.{gone.get('format', 'mp3')}").unlink(missing_ok=True)
    return jsonify(ok=True)


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        print("⚠️  រកមិនឃើញ ffmpeg ទេ។ សូមដំឡើងជាមុន។")
    app.run(host="0.0.0.0", port=5000, debug=False)
