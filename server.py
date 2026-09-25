import os, re, uuid, subprocess, asyncio, shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import edge_tts

BASE = Path(__file__).parent
WORK = BASE / "work"
AUDIO = BASE / "audio"
WORK.mkdir(exist_ok=True)
AUDIO.mkdir(exist_ok=True)

app = FastAPI(title="Link2MM")
app.mount("/audio", StaticFiles(directory=AUDIO), name="audio")

class Req(BaseModel):
    youtube_url: str
    voice: str = "my-MM-NilarNeural"

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2200:] or "Command failed")
    return p.stdout

def download_youtube(url, output):
    # No cookies, account login, PO token, or API key.
    # Try YouTube clients that can work without account cookies.
    clients = ["web_embedded", "web_safari", "tv"]
    errors = []
    for client in clients:
        if output.exists():
            output.unlink()
        try:
            cmd = [
                "yt-dlp", "--no-playlist",
                "--extractor-args", f"youtube:player_client={client}",
                "--js-runtimes", "deno",
                "-f", "bv*[height<=720]+ba/b[height<=720]/b",
                "--merge-output-format", "mp4",
                "--no-warnings",
                "-o", str(output), url
            ]
            run(cmd)
            if output.exists() and output.stat().st_size > 10000:
                return client
        except Exception as e:
            errors.append(f"{client}: {e}")
    raise RuntimeError(
        "YouTube က ဒီ server ကို video download ခွင့်မပေးသေးပါ။ "
        "No-cookie mode နဲ့ စမ်းထားတဲ့ client 3 မျိုးလုံး မအောင်မြင်ပါ။\n" +
        "\n".join(errors)
    )

def ocr(video):
    frames = WORK / (video.stem + "_frames")
    frames.mkdir(exist_ok=True)
    try:
        run([
            "ffmpeg", "-y", "-i", str(video),
            "-vf", "fps=1,crop=iw:ih*0.5:0:ih*0.5,scale=iw*1.5:-1",
            str(frames / "%06d.png")
        ])
        texts = []
        for f in sorted(frames.glob("*.png")):
            s = re.sub(
                r"\s+", " ",
                run(["tesseract", str(f), "stdout", "-l", "eng", "--psm", "6"])
            ).strip()
            if len(s) >= 3 and not any(
                s == x or s in x or x in s for x in texts[-3:]
            ):
                texts.append(s)
        return "\n".join(texts)
    finally:
        shutil.rmtree(frames, ignore_errors=True)

def google_translate_chunk(text):
    r = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "en", "tl": "my", "dt": "t", "q": text},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return "".join(part[0] for part in data[0] if part and part[0])

def translate(text):
    chunks, cur = [], ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(cur) + len(line) + 1 > 2500:
            if cur:
                chunks.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line).strip()
    if cur:
        chunks.append(cur)

    out = []
    for chunk in chunks:
        try:
            out.append(google_translate_chunk(chunk))
        except Exception:
            url = os.getenv("LIBRETRANSLATE_URL", "").rstrip("/")
            key = os.getenv("LIBRETRANSLATE_API_KEY", "")
            if not url:
                raise
            payload = {"q": chunk, "source": "en", "target": "my", "format": "text"}
            if key:
                payload["api_key"] = key
            rr = requests.post(url + "/translate", json=payload, timeout=120)
            rr.raise_for_status()
            out.append(rr.json()["translatedText"])
    return "\n".join(out)

async def tts(text, path, voice):
    await edge_tts.Communicate(text, voice).save(str(path))

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/process")
def process(req: Req):
    if not re.match(r"https?://(www\.)?(youtube\.com|youtu\.be)/", req.youtube_url):
        raise HTTPException(400, "YouTube link မမှန်ပါ။")
    job = uuid.uuid4().hex[:10]
    video = WORK / f"{job}.mp4"
    mp3 = AUDIO / f"{job}.mp3"
    try:
        used_client = download_youtube(req.youtube_url, video)
        eng = ocr(video)
        if not eng:
            raise RuntimeError("English on-screen text မတွေ့ပါ။")
        my = translate(eng)
        asyncio.run(tts(my, mp3, req.voice))
        return {
            "text": my,
            "english_ocr": eng,
            "audio_url": f"/audio/{mp3.name}",
            "download_client": used_client
        }
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        if video.exists():
            video.unlink(missing_ok=True)

app.mount("/", StaticFiles(directory=BASE, html=True), name="web")
