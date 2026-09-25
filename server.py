import os, re, uuid, subprocess, asyncio, shutil, requests
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
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

# Piped provides an unauthenticated /streams/:videoId API and proxy URLs.
# We try several current public instances; no cookies/login/API key are used.
PIPED_APIS = [
    "https://pipedapi.ducks.party",
    "https://api.piped.private.coffee",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.leptons.xyz",
    "https://api-piped.mha.fi",
    "https://piped-api.garudalinux.org",
]

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-3000:] or "Command failed")
    return p.stdout

def video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    if not m:
        raise ValueError("YouTube link မမှန်ပါ။")
    return m.group(1)

def piped_streams(vid):
    errors = []
    for api in PIPED_APIS:
        try:
            r = requests.get(f"{api}/streams/{vid}", timeout=20)
            r.raise_for_status()
            data = r.json()
            if data.get("videoStreams") or data.get("audioStreams"):
                return api, data
            errors.append(f"{api}: empty streams")
        except Exception as e:
            errors.append(f"{api}: {e}")
    raise RuntimeError(
        "Piped public instances တွေထဲက လက်ရှိအလုပ်လုပ်တဲ့ stream မရပါ။\n"
        + "\n".join(errors)
    )

def download_streams(vid, output):
    api, data = piped_streams(vid)
    videos = [
        x for x in data.get("videoStreams", [])
        if x.get("url") and x.get("mimeType","").startswith("video/mp4")
    ]
    # Prefer a combined MP4 stream (videoOnly=false), <=720p.
    combined = [x for x in videos if not x.get("videoOnly", True)]
    combined.sort(key=lambda x: (x.get("height", 0) <= 720, x.get("height", 0)), reverse=True)

    if combined:
        s = combined[0]
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", s["url"],
             "-t", "900", "-c", "copy", str(output)])
        if output.exists() and output.stat().st_size > 10000:
            return f"Piped: {api}"

    # Fallback: mux separate video + audio streams.
    videos.sort(key=lambda x: x.get("height", 0), reverse=True)
    v = next((x for x in videos if x.get("height", 0) <= 720), videos[0] if videos else None)
    audios = [x for x in data.get("audioStreams", []) if x.get("url")]
    audios.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
    a = audios[0] if audios else None
    if not v or not a:
        raise RuntimeError("Piped က video/audio stream မပြည့်စုံပါ။")
    run(["ffmpeg", "-y", "-loglevel", "error",
         "-i", v["url"], "-i", a["url"],
         "-t", "900", "-map", "0:v:0", "-map", "1:a:0",
         "-c", "copy", str(output)])
    if not output.exists() or output.stat().st_size <= 10000:
        raise RuntimeError("Video file download မအောင်မြင်ပါ။")
    return f"Piped: {api}"

def ocr(video):
    frames = WORK / (video.stem + "_frames")
    frames.mkdir(exist_ok=True)
    try:
        run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
            "-vf", "fps=1,crop=iw:ih*0.5:0:ih*0.5,scale=iw*1.5:-1",
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

def google_translate_chunk(text):
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
        if len(cur) + len(line) + 1 > 2500:
            chunks.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line).strip()
    if cur:
        chunks.append(cur)
    return "\n".join(google_translate_chunk(c) for c in chunks)

async def tts(text, path, voice):
    await edge_tts.Communicate(text, voice).save(str(path))

@app.get("/api/health")
def health():
    return {"ok": True, "mode": "piped-no-cookie"}

@app.post("/api/process")
def process(req: Req):
    vid = video_id(req.youtube_url)
    job = uuid.uuid4().hex[:10]
    video = WORK / f"{job}.mp4"
    mp3 = AUDIO / f"{job}.mp3"
    try:
        source = download_streams(vid, video)
        eng = ocr(video)
        if not eng:
            raise RuntimeError(
                "English on-screen text မတွေ့ပါ။ Video ထဲက စာက သေးလွန်းတာ/အောက်ခြေမဟုတ်တာ ဖြစ်နိုင်ပါတယ်။"
            )
        my = translate(eng)
        asyncio.run(tts(my, mp3, req.voice))
        return {
            "text": my,
            "english_ocr": eng,
            "audio_url": f"/audio/{mp3.name}",
            "source": source
        }
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        video.unlink(missing_ok=True)

app.mount("/", StaticFiles(directory=BASE, html=True), name="web")
