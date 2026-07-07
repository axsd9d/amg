# PartFinder — Maintenance Utility System (Full Stack, Deploy‑Ready)

Upload a nameplate photo → server runs **OCR** → extracts model/serial →
**auto‑logs into supplier portals** → searches the part number → returns live
pricing & availability. Passwords are stored **securely** (encrypted on Render,
never in Git).

## 🚀 Deploy in 4 steps

1. **Push to GitHub** — `git init && git add . && git commit -m init && git push`
2. **Render → New + → Blueprint** — pick the repo (uses `render.yaml`).
3. **Add your supplier passwords** as Render **Secret** env vars
   (e.g. `FERGUSON_USER` / `FERGUSON_PASS`). See the table in `SETUP_GUIDE.md`.
4. **Open the Render URL** → upload a photo → **Search All Suppliers**.

👉 **Full instructions:** [`SETUP_GUIDE.md`](./SETUP_GUIDE.md)

## How the pieces fit

| Layer | File | Job |
|---|---|---|
| Web app | `frontend/index.html` | Mobile UI (camera, OCR fields, results). Auto‑targets same‑origin backend. |
| API + OCR | `backend/serve_all.py` | `/api/extract-base64`, `/api/search`, `/api/suppliers`, serves the app. |
| Auto‑login | `backend/scraper.py` | Playwright logs into portals, keeps sessions warm, scrapes prices. |
| Secrets | `backend/credentials.py` | Loads passwords from env vars / encrypted vault at runtime. |
| Config | `backend/suppliers.json` | Supplier metadata + env‑var names (**no passwords**). |
| Deploy | `Dockerfile`, `render.yaml` | Docker image (Playwright+Tesseract) + Render blueprint. |
| Safety | `.gitignore` | Keeps `.env`, sessions, and secret files out of Git. |

## 🔐 Security at a glance
- Passwords → Render **Secret** env vars (encrypted at rest), or one encrypted
  blob via `backend/make_secrets.py`.
- Nothing sensitive is committed: `.env`, `pf_sessions/`, `*.secret.json` are
  git‑ignored.
- `/api/suppliers` exposes metadata only — never credentials.

## 🖥️ Run locally
```bash
cp .env.example .env      # add a couple real logins
docker build -t partfinder . && docker run -p 8000:8000 --env-file .env partfinder
# open http://localhost:8000
```
(Non‑Docker instructions are in `SETUP_GUIDE.md` §8.)

## GPT-Vision extraction

Uploaded nameplate photos are now processed by GPT-Vision first when `OPENAI_API_KEY` is configured. The backend requests structured JSON fields for `model_number`, `serial_number`, `part_number`, `brand`, `mfr_date`, `age_years`, `raw_text`, and `confidence`. If the OpenAI key is missing or the request fails, the backend falls back to the existing Tesseract OCR extraction path.

Required Render environment variables for GPT-Vision:

- `OPENAI_API_KEY` — secret OpenAI API key.
- `OPENAI_VISION_MODEL` — defaults to `gpt-4o-mini`.
