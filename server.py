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
        raise RuntimeError(p.stderr[-3500:] or "Command failed")
    return p.stdout

def get_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    if not m:
        raise ValueError("YouTube link မမှန်ပါ။")
    return m.group(1)

def download_youtube(url, output):
    # The container starts the official bgutil PO-token provider locally.
    # No user cookies, account login, or API key are used.
    attempts = [
        ["mweb"],
        ["web_safari"],
        ["tv"],
        ["android_vr"],
    ]
    errors = []
    for clients in attempts:
        if output.exists():
            output.unlink()
        client = clients[0]
        try:
            cmd = [
                "yt-dlp", "--no-playlist",
                "--js-runtimes", "node",
                "--extractor-args", f"youtube:player_client={client}",
                "-f", "bv*[height<=720]+ba/b[height<=720]/b",
                "--merge-output-format", "mp4",
                "--no-warnings",
                "-o", str(output),
                url
            ]
            run(cmd)
            if output.exists() and output.stat().st_size > 10000:
                return client
        except Exception as e:
            errors.append(f"{client}: {e}")
    raise RuntimeError(
        "YouTube က ဒီ server/IP ကို download ခွင့် မပေးသေးပါ။ "
        "PO-token provider ပါတဲ့ client မျိုးစုံနဲ့ စမ်းပြီး မအောင်မြင်ပါ။\n" +
        "\n".join(errors)
    )

def ocr(video):
    frames = WORK / (video.stem + "_frames")
    frames.mkdir(exist_ok=True)
    try:
        run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
            "-vf", "fps=1,crop=iw:ih*0.55:0:ih*0.45,scale=iw*1.7:-1",
            str(frames / "%06d.png")
        ])
        texts = []
        for f in sorted(frames.glob("*.png")):
            p = subprocess.run(
                ["tesseract", str(f), "stdout", "-l", "eng", "--psm", "6"],
                capture_output=True, text=True
            )
            s = re.sub(r"\s+", " ", p.stdout).strip()
            if len(s) >= 3 and not any(
                s == x or s in x or x in s for x in texts[-3:]
            ):
                texts.append(s)
        return "\n".join(texts)
    finally:
        shutil.rmtree(frames, ignore_errors=True)

def translate_chunk(text):
    r = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client":"gtx","sl":"en","tl":"my","dt":"t","q":text},
        timeout=60
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
        if len(cur) + len(line) + 1 > 2200:
            if cur:
                chunks.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line).strip()
    if cur:
        chunks.append(cur)
    return "\n".join(translate_chunk(c) for c in chunks)

async def make_tts(text, path, voice):
    await edge_tts.Communicate(text, voice).save(str(path))

@app.get("/api/health")
def health():
    return {"ok": True, "mode": "yt-dlp-bgutil-po-token"}

@app.post("/api/process")
def process(req: Req):
    vid = get_video_id(req.youtube_url)
    job = uuid.uuid4().hex[:10]
    video = WORK / f"{job}.mp4"
    mp3 = AUDIO / f"{job}.mp3"
    try:
        client = download_youtube(req.youtube_url, video)
        eng = ocr(video)
        if not eng:
            raise RuntimeError("English on-screen text မတွေ့ပါ။")
        my = translate(eng)
        asyncio.run(make_tts(my, mp3, req.voice))
        return {
            "text": my,
            "english_ocr": eng,
            "audio_url": f"/audio/{mp3.name}",
            "client": client
        }
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        video.unlink(missing_ok=True)

app.mount("/", StaticFiles(directory=BASE, html=True), name="web")
