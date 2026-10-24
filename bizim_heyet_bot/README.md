# Bizim həyət — WhatsApp Cloud API bot

The bot receives WhatsApp text messages via Meta Webhooks, checks license plates in a private Google Sheet, and answers in Azerbaijani. It only reveals resident information to approved WhatsApp numbers.

## Spreadsheet

Headers in the first row (case insensitive):

`avtomobil nömrəsi | sakin | geyri-sakin | telefon nömrəsi | mənzil nömrəsi | qeyd | adı`

`sakin` and `geyri-sakin` are Google Sheets checkboxes (TRUE/FALSE). The code also understands `qeyri-sakin`.

## Deploy on Railway

1. Create a **separate** Railway project/service; do not modify the working Telegram bot.
2. Upload this folder to a private GitHub repository and connect the repository to Railway. Set the start command to `uvicorn main:app --host 0.0.0.0 --port $PORT` (or use the Procfile).
3. Create a Google Cloud service account with Sheets API access, share the existing **Bizim həyət** Sheet with its `client_email` as **Viewer**.
4. Add variables to Railway (not to GitHub):

```
GOOGLE_SHEET_ID=<ID from spreadsheet URL>
GOOGLE_WORKSHEET_NAME=<worksheet tab name; optional, uses first tab by default>
GOOGLE_SERVICE_ACCOUNT_JSON=<entire JSON string from Google Cloud service account>
AUTHORIZED_WA_NUMBERS=994XXXXXXXXX,994YYYYYYYYY
WHATSAPP_VERIFY_TOKEN=<your own long random secret>
WHATSAPP_ACCESS_TOKEN=<Meta permanent system-user access token>
WHATSAPP_PHONE_NUMBER_ID=<Meta WhatsApp phone-number ID, NOT the phone number>
META_APP_SECRET=<Meta App Secret>
META_API_VERSION=v23.0
```

5. Generate a public Railway HTTPS domain. In Meta Webhooks, use `https://your-domain.up.railway.app/webhook` and the exact `WHATSAPP_VERIFY_TOKEN` value. Subscribe to the WhatsApp `messages` field and link the business WhatsApp account where required.
6. Meta App must be properly configured/published and the WhatsApp business phone number enabled to receive **real** messages. In development mode, Meta may send only test webhooks.

Never send API tokens, verification codes, `META_APP_SECRET`, or Google service account JSON to anyone in chat.

## Example

Message: `10-AA-123`

Resident response:
```
🚗 10-AA-123
Status: Sakin
Adı: Ramin
Mənzil nömrəsi: 12
Telefon nömrəsi: +994...
Qeyd: ...
```

Nonresident with missing name/phone:
```
🚗 10-AA-123
Status: Qeyri-sakin
```

Unknown plate: `Bu avtomobil barədə bazada məlumat tapılmadı.`

## Important before live deployment

- Ask residents for permission before collecting and sharing phone numbers and apartment numbers. Keep the allowlist limited to authorized residents.
- Handle Meta webhook retries and duplicate message IDs (e.g., using Redis or a database) before high-volume production use.
- A Google Sheets service account needs explicit Sheet access; the application does not create or overwrite the existing spreadsheet.
- This is starter code, not yet configured with real credentials or deployed.
