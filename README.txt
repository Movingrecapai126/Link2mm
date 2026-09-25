Link2MM — Stable YouTube mode

ဒီ version က အရင် No-Cookie/Piped versions ထက် YouTube အတွက် ပိုပြည့်စုံတဲ့ setup ဖြစ်ပါတယ်။

ပါဝင်တာ:
- yt-dlp + EJS JavaScript runtime (Node 22)
- official bgutil-ytdlp-pot-provider 2.0.0
- per-video PO token ကို server ထဲမှာ အလိုအလျောက် generate လုပ်ခြင်း
- YouTube cookies / login / API key မလို
- mweb -> web_safari -> tv -> android_vr fallback
- English on-screen OCR
- English -> Myanmar translation
- Myanmar TTS MP3

yt-dlp ရဲ့ 2026 PO Token Guide က automated PO-token provider ကို အကြံပြုထားပြီး
bgutil-ytdlp-pot-provider ကို featured provider အဖြစ် ဖော်ပြထားပါတယ်။

သတိ:
PO token provider တစ်ခုတည်းနဲ့ 403/bot check ကို 100% အာမခံမရပါ။
YouTube က server IP ကို တိုက်ရိုက် block ထားရင် hosting provider/IP ပြောင်းရန်
လိုနိုင်ပါတယ်။ ဒါပေမယ့် အခု setup က YouTube download အတွက် လက်ရှိ
yt-dlp recommendation နဲ့ အနီးဆုံးဖြစ်ပါတယ်။

Source:
https://github.com/Brainicism/bgutil-ytdlp-pot-provider
https://github.com/yt-dlp/yt-dlp/wiki/Po-Token-Guide
