LINK2MM — RENDER READY

Flow:
YouTube URL -> download -> OCR English text visible in video -> Myanmar translation -> Myanmar MP3

Files:
- server.py
- index.html
- requirements.txt
- Dockerfile

Deploy:
1. Create a Render Web Service from this GitHub repository.
2. Runtime/Language: Docker
3. Branch: main
4. Plan: Free (for testing)
5. Create Web Service.

Notes:
- This reads English text visibly embedded in video frames; it does not use YouTube subtitle tracks.
- OCR checks the lower half of the video at about 1 frame/second.
- Free hosting can sleep when idle and has usage limits.
- Only process videos you have permission to download/process.
