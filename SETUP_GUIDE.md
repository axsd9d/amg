# PartFinder — Step‑by‑Step Deployment Guide (GitHub + Render)

This guide walks you from zero to a **live, always‑logged‑in** Maintenance
Utility System where you:

1. Store supplier passwords **securely** (encrypted on Render — never in Git).
2. Have the server **auto‑log‑in** to each supplier portal and keep sessions warm.
3. **Upload a nameplate photo** → the server runs **OCR** on the raw image →
   extracts model/serial → composes a part number → **searches every portal**
   for live pricing & availability.

> ⚠️ **Security rule #1:** Never commit real passwords to GitHub. This project
> keeps `suppliers.json` password‑free and reads the real logins from Render
> **Secret environment variables** at runtime.

---

## 0. What's in this package

```
partfinder-deploy/
├── Dockerfile              # Playwright + Tesseract image for Render
├── render.yaml             # One‑click Render Blueprint (defines the secrets)
├── .gitignore              # Keeps secrets & login sessions OUT of Git
├── .env.example            # Template for LOCAL testing only
├── SETUP_GUIDE.md          # ← you are here
├── frontend/
│   └── index.html          # The mobile web app (already points at same origin)
└── backend/
    ├── serve_all.py        # FastAPI: OCR + search + serves the app
    ├── scraper.py          # Playwright auto‑login + portal search (persistent sessions)
    ├── credentials.py      # Reads passwords from env / encrypted vault at runtime
    ├── suppliers.json      # Supplier metadata — NO passwords
    ├── make_secrets.py     # Optional: build one encrypted password blob
    └── requirements.txt
```

---

## 1. Install the prerequisites (one time)

- A **GitHub** account → <https://github.com/join>
- A **Render** account → <https://dashboard.render.com/register> (sign in with GitHub)
- **Git** on your computer → <https://git-scm.com/downloads>
  - Verify: open a terminal and run `git --version`

---

## 2. Put the code on GitHub

### 2a. Create an empty repository
1. Go to <https://github.com/new>.
2. **Repository name:** `partfinder` (anything is fine).
3. Choose **Private** (recommended — this is internal tooling).
4. Do **not** add a README/gitignore (we already have them).
5. Click **Create repository**. Leave the page open — you'll need the URL.

### 2b. Push this folder to that repo
Open a terminal **inside the `partfinder-deploy` folder** and run:

```bash
git init
git add .
git commit -m "Initial PartFinder deploy"
git branch -M main
# Replace with YOUR repo URL from step 2a:
git remote add origin https://github.com/YOUR-USER/partfinder.git
git push -u origin main
```

> ✅ **Double‑check before pushing:** run `git status` and confirm you do **not**
> see a `.env`, `pf_sessions/`, or any `*.secret.json` file. The `.gitignore`
> already blocks them, but verify. `suppliers.json` is safe (no passwords).

If GitHub asks for a password, use a **Personal Access Token** instead of your
account password: GitHub → Settings → Developer settings → Personal access
tokens → *Generate new token (classic)* → scope `repo`.

---

## 3. Deploy on Render (Docker web service)

We use Docker because the auto‑login (Playwright/Chromium) and OCR (Tesseract)
need system libraries. The included `Dockerfile` handles all of that.

### Option A — Blueprint (easiest, uses `render.yaml`)
1. Render dashboard → **New +** → **Blueprint**.
2. **Connect** your GitHub account and pick the `partfinder` repo.
3. Render reads `render.yaml`, sees the Docker service and the list of secret
   env vars, and shows a form.
4. Click **Apply**. It creates the service. (You'll fill the secrets in Step 4.)

### Option B — Manual web service
1. Render dashboard → **New +** → **Web Service**.
2. Connect the `partfinder` repo.
3. Settings:
   - **Environment:** `Docker`
   - **Dockerfile Path:** `./Dockerfile`
   - **Health Check Path:** `/api/suppliers`
   - **Instance Type:** **Standard** or higher (Chromium needs RAM; the Free
     tier will crash on browser launch).
4. Click **Create Web Service**.

---

## 4. Store the supplier passwords securely (2 ways)

You only need **ONE** of these. Both store passwords **encrypted at rest** on
Render and inject them at runtime. Nothing is ever written to Git.

### Way 1 — Individual secret env vars (simplest)
In your Render service → **Environment** → **Add Environment Variable**, add a
pair for each portal you want auto‑login on:

| Key              | Example value                | Notes                         |
|------------------|------------------------------|-------------------------------|
| `FERGUSON_USER`  | `danielv@a-mg.com`           | portal login email            |
| `FERGUSON_PASS`  | `••••••••`                   | portal password (Secret)      |
| `GRAINGER_USER`  | `customerservice@a-mg.com`   |                               |
| `GRAINGER_PASS`  | `••••••••`                   |                               |
| `PARTSTOWN_USER` | `customerservice@a-mg.com`   |                               |
| `PARTSTOWN_PASS` | `••••••••`                   |                               |
| `ALLPOINTS_USER` | …                            |                               |
| `ALLPOINTS_PASS` | …                            |                               |
| `AMAZON_USER`    | …                            |                               |
| `AMAZON_PASS`    | …                            |                               |
| `JOHNSTONE_USER` | …                            |                               |
| `JOHNSTONE_PASS` | …                            |                               |

- The var **names** are already mapped in `backend/suppliers.json`
  (`"login_password_env": "FERGUSON_PASS"`), so you only edit values.
- Leave a pair **blank** to skip that portal's auto‑login (it falls back to a
  deep link).
- Click **Save Changes** → Render redeploys automatically.

### Way 2 — One encrypted vault string (all passwords in one blob)
1. Locally: `pip install cryptography`.
2. Edit `backend/make_secrets.py` and fill in the real logins.
3. Run `python backend/make_secrets.py`. It prints two values.
4. In Render → Environment, add:
   - `SECRETS_KEY` = the printed key
   - `SECRETS_ENC` = the printed encrypted blob
5. Save. `credentials.py` decrypts them at boot.

> 🔐 Both ways: passwords are encrypted at rest, hidden in the UI, and never in
> your Git history. To rotate a password, just edit the env var and save.

---

## 5. Confirm it's live

1. Render shows a URL like `https://partfinder.onrender.com`.
2. Open it — the **Maintenance Utility System** app loads.
3. The app auto‑detects the backend (it uses the same origin), so no config is
   needed. To point a different frontend at it, open **⚙ Backend Settings** and
   paste the Render URL.
4. Check logins are warming: open `https://partfinder.onrender.com/api/session-status`
   → you'll see each portal marked `credentials-set` or `no-credentials`.

---

## 6. Use it: photo → OCR → auto‑login search

1. Tap **Take Photo** or **Browse** and upload a nameplate image.
2. The server runs **OCR on the raw image bytes** (`/api/extract-base64`) and
   fills in **Model / Serial / Brand / Part** (all editable — fix any misread).
3. It **composes the part number** (`PART` if present, else `MODEL-SERIAL`).
4. Tap **🔍 Search All Suppliers**. The backend:
   - ensures each portal session is **logged in** (persistent cookies),
   - opens each supplier's search URL for that part number,
   - scrapes **price + stock**, and returns ranked results.
5. Results show live pricing where available; portals without credentials show
   a deep link; call/text‑only suppliers show tap‑to‑call / tap‑to‑text.

> The server keeps a **heartbeat** that re‑logs‑in every hour so the portals
> stay "always logged in".

---

## 7. Tune the portal selectors (important)

Every portal's login form and results page use different HTML. Open
`backend/scraper.py` and edit `PORTAL_SELECTORS` for each supplier:

```python
"Ferguson": {
    "user": "#username",          # login email/username field
    "pass": "#password",          # password field
    "submit": "button[type=submit]",
    "logged_in": "text=Sign Out", # element that proves you're logged in
    "result_price": ".product-price",
    "result_stock": ".availability",
},
```

How to find the right selectors:
1. Open the portal in Chrome, right‑click the field → **Inspect**.
2. Note its `id`, `name`, or a stable CSS class.
3. Put a matching CSS selector in the dict, commit, and Render redeploys.

If a portal blocks bots or a selector is wrong, that supplier gracefully falls
back to a deep link — the rest of the search still works.

---

## 8. Run it locally first (recommended before deploying)

```bash
cd partfinder-deploy
cp .env.example .env          # fill in a few real logins to test
# System deps: Tesseract + Chromium
#   macOS:  brew install tesseract
#   Ubuntu: sudo apt-get install -y tesseract-ocr
pip install -r backend/requirements.txt
playwright install chromium
set -a; source .env; set +a    # load env vars (Linux/macOS)
cd backend && python serve_all.py
# open http://localhost:8000
```

Or just build the Docker image (matches Render exactly):

```bash
cd partfinder-deploy
docker build -t partfinder .
docker run -p 8000:8000 --env-file .env partfinder
# open http://localhost:8000
```

---

## 9. Updating later

Any code change → push to GitHub → Render auto‑deploys:

```bash
git add .
git commit -m "Update selectors / add supplier"
git push
```

To add a supplier: add an entry to `backend/suppliers.json` (with
`login_*_env` names), add those env vars in Render, add its selectors to
`scraper.py`, and push.

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| App loads but search says "Backend offline" | You opened the **static** site, not the Render URL. Use the Render URL, or set it in **⚙ Backend Settings**. |
| Service crashes on start / OOM | Use **Standard** instance or higher — Chromium needs RAM. |
| A portal never logs in | Check its `*_USER`/`*_PASS` env vars and fix the login selectors in `scraper.py`. Portal may also require MFA/captcha. |
| OCR returns blank fields | Retake the photo (flat, well‑lit, fill the frame). Fields are editable — just type the values and search. |
| `/api/session-status` shows `no-credentials` | The env vars for that portal are empty or misnamed. Names must match `suppliers.json`. |
| Git push rejected / asks password | Use a GitHub Personal Access Token (scope `repo`) as the password. |

---

## Security summary

- ✅ Passwords live only in Render **Secret** env vars (encrypted at rest).
- ✅ `.gitignore` blocks `.env`, `pf_sessions/`, and `*.secret.json`.
- ✅ `/api/suppliers` returns metadata only — never passwords.
- ✅ Login **sessions** (cookies) are stored on the server's ephemeral disk
  (`/tmp/pf_sessions`), not in Git.
- 🔁 Rotate any password anytime by editing its env var and saving.
