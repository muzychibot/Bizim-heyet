import hashlib
import hmac
import json
import logging
import os
import re
import unicodedata
from functools import lru_cache

import gspread
import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Bizim həyət WhatsApp Bot")


def env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"Missing Railway variable: {name}")
    return val


def normalized_phone(value: str) -> str:
    return re.sub(r"\D", "", value)


def allowed_sender(sender: str) -> bool:
    allowlist = {normalized_phone(x) for x in env("AUTHORIZED_WA_NUMBERS").split(",") if x.strip()}
    return normalized_phone(sender) in allowlist


def normalize_plate(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value).upper()
    return re.sub(r"[^0-9A-ZƏÖĞÜŞÇİ]", "", cleaned)


def value(row: dict, *names: str) -> str:
    normalized = {str(k).strip().casefold().replace("ı", "i"): v for k, v in row.items()}
    for name in names:
        v = normalized.get(name.casefold().replace("ı", "i"))
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def checked(v: str) -> bool:
    return str(v).strip().lower() in {"true", "yes", "1", "bəli", "beli", "✓", "✔", "так"}


@lru_cache(maxsize=1)
def sheet():
    credentials_json = json.loads(env("GOOGLE_SERVICE_ACCOUNT_JSON"))
    creds = Credentials.from_service_account_info(
        credentials_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    book = gc.open_by_key(env("GOOGLE_SHEET_ID"))
    tab = os.getenv("GOOGLE_WORKSHEET_NAME", "").strip()
    return book.worksheet(tab) if tab else book.sheet1


def lookup_plate(text: str) -> str:
    plate = normalize_plate(text)
    if not (5 <= len(plate) <= 12):
        return "Zəhmət olmasa, avtomobilin nömrəsini yazın. Məsələn: 10-AA-123."
    try:
        rows = sheet().get_all_records()
    except Exception:
        logging.exception("Failed reading Google Sheet")
        return "Hazırda məlumat bazasına qoşulmaq mümkün deyil. Bir az sonra yenidən yoxlayın."
    for row in rows:
        stored = normalize_plate(value(row, "avtomobil nömrəsi", "avtomobil nomresi"))
        if not stored or stored != plate:
            continue
        is_resident = checked(value(row, "sakin"))
        is_nonresident = checked(value(row, "geyri-sakin", "qeyri-sakin", "geyri sakin", "qeyri sakin"))
        if is_resident == is_nonresident:
            return f"🚗 {text.strip()}\nStatus: məlumat dəqiqləşdirilir."
        result = [f"🚗 {text.strip()}", f"Status: {'Sakin' if is_resident else 'Qeyri-sakin'}"]
        fields = [
            ("Adı", value(row, "adı", "adi")),
            ("Mənzil nömrəsi", value(row, "mənzil nömrəsi", "menzil nomresi") if is_resident else ""),
            ("Telefon nömrəsi", value(row, "telefon nömrəsi", "telefon nomresi", "telfon nömrəsi")),
            ("Qeyd", value(row, "qeyd", "geyd")),
        ]
        result.extend(f"{label}: {item}" for label, item in fields if item)
        return "\n".join(result)
    return f"🚗 {text.strip()}\nBu avtomobil barədə bazada məlumat tapılmadı."



async def send_message(to: str, text: str):
    url = f"https://graph.facebook.com/{env('META_API_VERSION')}/{env('WHATSAPP_PHONE_NUMBER_ID')}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text[:4096]},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {env('WHATSAPP_ACCESS_TOKEN')}"},
            json=payload,
        )
        if resp.is_error:
            logging.error(
                "WhatsApp API error: status=%s body=%s",
                resp.status_code,
                resp.text,
            )
        resp.raise_for_status()



async def process_event(event: dict):
    try:
        if event.get("object") != "whatsapp_business_account":
            return
        for entry in event.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                for msg in change.get("value", {}).get("messages", []):
                    if msg.get("type") != "text":
                        continue
                    sender = msg.get("from", "")
                    if not sender:
                        continue
                    if not allowed_sender(sender):
                        # Do not disclose whether the plate is registered to unauthorized users.
                        await send_message(sender, "Bu xidmət yalnız təsdiqlənmiş həyət sakinləri üçündür.")
                        continue
                    answer = lookup_plate(msg.get("text", {}).get("body", ""))
                    await send_message(sender, answer)
    except Exception:
        logging.exception("Failed processing WhatsApp event")


@app.get("/")
async def home():
    return {"service": "bizim-heyet", "status": "ok"}


@app.get("/webhook")
async def verify_webhook(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), env("WHATSAPP_VERIFY_TOKEN")):
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(env("META_APP_SECRET").encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")
    background_tasks.add_task(process_event, json.loads(raw))
    return {"status": "received"}
