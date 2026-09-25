import os, re, uuid, shutil, subprocess, asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import edge_tts

BASE=Path(__file__).parent
WORK=BASE/"work"; AUDIO=BASE/"audio"
WORK.mkdir(exist_ok=True); AUDIO.mkdir(exist_ok=True)
app=FastAPI(title="Link2MM Ready")
app.mount("/audio",StaticFiles(directory=AUDIO),name="audio")

class Req(BaseModel):
    youtube_url:str
    voice:str="my-MM-NilarNeural"

def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode: raise RuntimeError(p.stderr[-1800:])
    return p.stdout

def ocr(video):
    frames=WORK/video.stem+"_frames"; frames.mkdir(exist_ok=True)
    run(["ffmpeg","-y","-i",str(video),"-vf","fps=1,crop=iw:ih*0.5:0:ih*0.5,scale=iw*1.5:-1",str(frames/"%06d.png")])
    texts=[]
    for f in sorted(frames.glob("*.png")):
        s=re.sub(r"\s+"," ",run(["tesseract",str(f),"stdout","-l","eng","--psm","6"])).strip()
        if len(s)>=3 and not any(s==x or s in x or x in s for x in texts[-3:]): texts.append(s)
    return "\n".join(texts)

def translate(text):
    url=os.getenv("LIBRETRANSLATE_URL","http://libretranslate:5000").rstrip("/")
    key=os.getenv("LIBRETRANSLATE_API_KEY","")
    payload={"q":text,"source":"en","target":"my","format":"text"}
    if key: payload["api_key"]=key
    r=requests.post(url+"/translate",json=payload,timeout=180); r.raise_for_status()
    return r.json()["translatedText"]

async def tts(text,path,voice):
    await edge_tts.Communicate(text,voice).save(str(path))

@app.post("/api/process")
def process(req:Req):
    if not re.match(r"https?://(www\.)?(youtube\.com|youtu\.be)/",req.youtube_url):
        raise HTTPException(400,"YouTube link မမှန်ပါ။")
    job=uuid.uuid4().hex[:10]; video=WORK/f"{job}.mp4"; mp3=AUDIO/f"{job}.mp3"
    try:
        run(["yt-dlp","--no-playlist","-f","bv*[height<=720]+ba/b[height<=720]/b",
             "--merge-output-format","mp4","-o",str(video),req.youtube_url])
        eng=ocr(video)
        if not eng: raise RuntimeError("English on-screen text မတွေ့ပါ။")
        my=translate(eng)
        asyncio.run(tts(my,mp3,req.voice))
        return {"text":my,"english_ocr":eng,"audio_url":f"/audio/{mp3.name}"}
    except Exception as e: raise HTTPException(500,str(e))
    finally:
        if video.exists(): video.unlink(missing_ok=True)

app.mount("/",StaticFiles(directory=BASE/"web",html=True),name="web")
