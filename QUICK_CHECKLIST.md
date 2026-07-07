# ✅ Quick Checklist (print this)

## GitHub
- [ ] Create **private** repo at github.com/new (name: `partfinder`)
- [ ] In the `partfinder-deploy` folder, run:
      `git init && git add . && git commit -m "init" && git branch -M main`
- [ ] `git remote add origin https://github.com/YOU/partfinder.git`
- [ ] `git status` → confirm **no** `.env` / `pf_sessions/` / `*.secret.json`
- [ ] `git push -u origin main`

## Render
- [ ] Sign in at dashboard.render.com with GitHub
- [ ] **New + → Blueprint →** select the `partfinder` repo → **Apply**
- [ ] (Manual alt: New + → Web Service → Docker → Dockerfile `./Dockerfile`
      → instance **Standard**)

## Passwords (pick ONE method)
- [ ] **A:** Add pairs in Render → Environment:
      `FERGUSON_USER`/`FERGUSON_PASS`, `GRAINGER_USER`/`GRAINGER_PASS`, …
- [ ] **B:** `python backend/make_secrets.py` → add `SECRETS_KEY` + `SECRETS_ENC`
- [ ] Save → Render redeploys

## Verify
- [ ] Open the Render URL → app loads
- [ ] Visit `/api/session-status` → portals show `credentials-set`
- [ ] Tune login/result selectors in `backend/scraper.py` per portal

## Use
- [ ] Upload nameplate photo → OCR fills fields → fix any misreads
- [ ] **Search All Suppliers** → live prices + stock returned
