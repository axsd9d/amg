"""
PartFinder — Combined Backend + Frontend Server
────────────────────────────────────────────────
Serves the mobile web app and all API endpoints:

  POST /api/extract-base64   OCR a base64 image  -> model/serial/brand/part
  POST /api/extract          OCR an uploaded file -> same
  POST /api/search           Auto-login + live part-number search across suppliers
  GET  /api/suppliers        Public supplier metadata (NO passwords)
  GET  /api/session-status   Which portals have credentials configured
  GET  /                     The mobile web app (frontend/index.html)

Passwords are read at runtime from environment variables via credentials.py.
"""

import io
import os
import re
import json
import base64
import asyncio
import logging
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from scraper import (
    scrape_all_suppliers,
    warm_all_sessions,
    shutdown_scraper,
    session_status,
)
from credentials import has_credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("partfinder")

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
SUPPLIERS_FILE = BASE_DIR / "suppliers.json"

with open(SUPPLIERS_FILE) as f:
    SUPPLIERS = json.load(f)

app = FastAPI(title="PartFinder", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────
class ExtractedData(BaseModel):
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    part_number: Optional[str] = None
    brand: Optional[str] = None
    mfr_date: Optional[str] = None
    age_years: Optional[float] = None
    raw_text: str = ""
    confidence: float = 0.0


# ── Session lifecycle: keep portal logins warm ─────────────────────────────
@app.on_event("startup")
async def _startup():
    logger.info("Startup: warming supplier sessions in background...")
    asyncio.create_task(_warm_and_heartbeat())


async def _warm_and_heartbeat():
    try:
        await warm_all_sessions(SUPPLIERS)
        logger.info("Initial session warming complete.")
    except Exception as e:  # noqa: BLE001
        logger.error("Session warming error: %s", e)
    while True:
        try:
            await asyncio.sleep(3600)
            await warm_all_sessions(SUPPLIERS)
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001
            logger.error("Heartbeat error: %s", e)


@app.on_event("shutdown")
async def _shutdown():
    await shutdown_scraper()


# ── Image extraction: GPT-Vision first, Tesseract fallback ─────────────────────
def _ocr_image_bytes(img_bytes: bytes) -> str:
    from PIL import Image
    import pytesseract
    img = Image.open(io.BytesIO(img_bytes))
    return pytesseract.image_to_string(img)


def _clean_json_object(text: str) -> dict:
    """Best-effort JSON extraction for model responses that include fences/text."""
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


def _normalize_vision_result(data: dict, raw_text: str = "") -> ExtractedData:
    def val(*names):
        for name in names:
            v = data.get(name)
            if v not in (None, "", "null"):
                return str(v).strip().upper() if name != "raw_text" else str(v).strip()
        return None

    mfr_date = val("mfr_date", "manufacture_date", "mfg_date")
    age = data.get("age_years")
    try:
        age = float(age) if age not in (None, "", "null") else None
    except (TypeError, ValueError):
        age = None
    if age is None:
        age = calculate_age_years(mfr_date)

    raw = str(data.get("raw_text") or raw_text or "").strip()
    model = val("model_number", "model", "mod_no")
    serial = val("serial_number", "serial", "serial_no")
    part = val("part_number", "part", "part_no")
    brand = val("brand", "manufacturer", "make")

    # Preserve the proven Trane OCR correction even for GPT output.
    if model and re.fullmatch(r"AT[A-Z]{2}[0-9]{4}[A-Z][0-9]{4}[A-Z]{2}", model):
        model = "4" + model[1:]
        brand = brand or "TRANE"

    conf = data.get("confidence", 0.0)
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.0
    if conf <= 0:
        conf = 0.95 if (model or serial or mfr_date) else 0.0

    return ExtractedData(
        model_number=model,
        serial_number=serial,
        part_number=part,
        brand=brand,
        mfr_date=mfr_date,
        age_years=age,
        raw_text=raw,
        confidence=round(min(max(conf, 0.0), 1.0), 2),
    )


async def _gpt_vision_extract(img_bytes: bytes) -> ExtractedData | None:
    """Use OpenAI vision when OPENAI_API_KEY is configured; return None on fallback."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    image_b64 = base64.b64encode(img_bytes).decode("ascii")
    prompt = (
        "You are extracting HVAC/commercial kitchen equipment nameplate data. "
        "Read the image carefully and return ONLY valid JSON with these keys: "
        "model_number, serial_number, part_number, brand, mfr_date, age_years, "
        "raw_text, confidence. Use MOD NO./MODEL NO. for model_number, "
        "SERIAL NO./S/N for serial_number, and MFR Date/MFG Date for mfr_date. "
        "If a value is not visible use null. mfr_date should be M/YYYY or MM/YYYY when possible. "
        "Do not guess; preserve exact letters/numbers. For Trane models that look like ATWB... "
        "but are actually 4TWB..., return the leading character as 4 when the nameplate supports it."
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        )
        content = resp.choices[0].message.content or "{}"
        data = _clean_json_object(content)
        if not data:
            return None
        extracted = _normalize_vision_result(data)
        if extracted.model_number or extracted.serial_number or extracted.mfr_date or extracted.raw_text:
            extracted.raw_text = extracted.raw_text or content
            return extracted
    except Exception as e:  # noqa: BLE001
        logger.warning("GPT-Vision extraction failed; falling back to Tesseract: %s", e)
    return None


async def extract_image_bytes(img_bytes: bytes) -> ExtractedData:
    vision = await _gpt_vision_extract(img_bytes)
    if vision:
        return vision
    raw = _ocr_image_bytes(img_bytes)
    return extract_fields_from_text(raw)


def calculate_age_years(mfr_date: str | None) -> float | None:
    if not mfr_date:
        return None
    from datetime import date
    m = re.search(r"(\d{1,2})\s*[/.-]\s*(\d{2,4})", mfr_date)
    if not m:
        return None
    month = int(m.group(1))
    year = int(m.group(2))
    if year < 100:
        year += 2000 if year < 70 else 1900
    if not 1 <= month <= 12:
        return None
    today = date.today()
    return round((today.year - year) + (today.month - month) / 12, 1)


def extract_fields_from_text(raw_text: str) -> ExtractedData:
    text = raw_text.upper()
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    model = serial = brand = part = mfr_date = None

    brands = ["CARRIER", "TRANE", "LENNOX", "YORK", "DAIKIN", "GOODMAN", "AMANA",
              "RHEEM", "RUUD", "HEIL", "TEMPSTAR", "BRYANT", "PAYNE",
              "AMERICAN STANDARD", "HOSHIZAKI", "TRUE", "TURBOAIR", "BOHN",
              "HEATCRAFT", "COPELAND", "EMERSON", "MANITOWOC", "SCOTSMAN",
              "HOBART", "TAYLOR", "VULCAN", "GROEN", "GARLAND", "SOUTHBEND"]
    for b in brands:
        if re.search(r"\b" + re.escape(b) + r"\b", text):
            brand = b
            break

    # Trane and similar nameplates often print model as MOD. NO. / MOD NO.
    model_pats = [
        r"(?:MOD\.?\s*NO\.?|MODEL\s*#|MODEL\s*NO\.?|MODEL\s+NUMBER|M/N|MOD)[:\s.]*([A-Z0-9][\w\-]{3,30})",
        r"\b([0-9]{2,3}[A-Z]{1,3}[0-9]{3,6})\b",
        r"\b([A-Z]{2,4}[0-9]{3,6}[A-Z]?)\b",
    ]
    for p in model_pats:
        m = re.search(p, text)
        if m and len(m.group(1)) >= 4 and not re.fullmatch(r"\d{4,}", m.group(1)):
            model = m.group(1)
            break

    # Trane fallback: model numbers like 4TWB3036C1000AB are sometimes OCR'd
    # as ATWB3036C1000AB because the leading 4 looks like an A.
    if not model:
        m = re.search(r"\b([A4]T[A-Z]{2}[0-9]{4}[A-Z][0-9]{4}[A-Z]{2})\b", text)
        if m:
            model = m.group(1)
            if model.startswith("A"):
                model = "4" + model[1:]
            if not brand:
                brand = "TRANE"

    # Accept SERIAL NO., SERIALNO., S/N, SN and OCR spacing variants.
    serial_pats = [
        r"(?:SERIAL\s*NO\.?|SERIALNO\.?|SERIAL\s*#|SERIAL\s+NUMBER|S/N|SN|SERIAL)[:\s.]*([A-Z0-9][\w\-]{4,20})",
        r"\b([0-9]{4,5}[A-Z][0-9]{3,5})\b",
    ]
    for p in serial_pats:
        m = re.search(p, text)
        if m and m.group(1) != model and len(m.group(1)) >= 5:
            serial = m.group(1)
            break

    part_pats = [
        r"(?:PART|PART\s*#|PART\s*NO|P/N)[:\s]*([A-Z0-9][\w\-.]{3,30})",
        r"PART\s+NUMBER[:\s]*([A-Z0-9][\w\-.]{3,30})",
    ]
    for p in part_pats:
        m = re.search(p, text)
        if m:
            part = m.group(1)
            break

    mfr_pats = [
        r"(?:MFR\s*DATE|MFG\s*DATE|MANUFACTURE\s*DATE|MANUFACTURED)[:\s.]*([0-9]{1,2}\s*[/.-]\s*[0-9]{2,4})",
        r"\b([0-9]{1,2}\s*[/.-]\s*[0-9]{4})\b",
    ]
    for p in mfr_pats:
        m = re.search(p, text)
        if m:
            mfr_date = re.sub(r"\s+", "", m.group(1))
            break
    age_years = calculate_age_years(mfr_date)

    conf = 0.0
    if model:  conf += 0.4
    if serial: conf += 0.3
    if brand:  conf += 0.1
    if part:   conf += 0.1
    if mfr_date: conf += 0.1
    return ExtractedData(model_number=model, serial_number=serial,
                         part_number=part, brand=brand,
                         mfr_date=mfr_date, age_years=age_years,
                         raw_text=raw_text, confidence=round(min(conf, 1.0), 2))


def compose_part_number(d: ExtractedData) -> str:
    if d.part_number:
        return d.part_number
    if d.model_number and d.serial_number:
        return f"{d.model_number}-{d.serial_number}"
    return d.model_number or ""


@app.post("/api/extract", response_model=ExtractedData)
async def extract_from_image(file: UploadFile = File(...)):
    try:
        return await extract_image_bytes(await file.read())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Bad image: {e}")


@app.post("/api/extract-base64", response_model=ExtractedData)
async def extract_from_base64(data: dict):
    img = data.get("image", "")
    if "," in img:
        img = img.split(",", 1)[1]
    try:
        return await extract_image_bytes(base64.b64decode(img))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Bad image: {e}")


# ── Search ──────────────────────────────────────────────────────────────────
@app.post("/api/search")
async def search_suppliers(data: dict):
    extracted = ExtractedData(
        model_number=data.get("model_number"),
        serial_number=data.get("serial_number"),
        part_number=data.get("part_number"),
        brand=data.get("brand"),
        mfr_date=data.get("mfr_date"),
        age_years=data.get("age_years"),
    )
    part = compose_part_number(extracted)
    if not part:
        raise HTTPException(400, "No model/part number provided")
    results = await scrape_all_suppliers(SUPPLIERS, part)
    in_stock = sum(1 for r in results if "in stock" in str(r.get("stock_status", "")).lower())
    live = sum(1 for r in results if r.get("has_live_price"))
    return {
        "part_number": part,
        "brand": extracted.brand or "",
        "suppliers": results,
        "in_stock_count": in_stock,
        "live_price_count": live,
    }


# ── Metadata ─────────────────────────────────────────────────────────────────
@app.get("/api/suppliers")
async def list_suppliers():
    """Public supplier info only — passwords are never exposed."""
    out = []
    for s in SUPPLIERS:
        out.append({
            "name": s["name"],
            "account_number": s.get("account_number", ""),
            "rep_name": s.get("rep_name", ""),
            "email": s.get("email", ""),
            "phone": s.get("phone", ""),
            "cell": s.get("cell", ""),
            "portal_url": s.get("portal_url", ""),
            "search_url": s.get("search_url", ""),
            "type": s.get("type", "portal"),
            "notes": s.get("notes", ""),
            "has_credentials": has_credentials(s),
        })
    return out


@app.get("/api/session-status")
async def api_session_status():
    return session_status(SUPPLIERS)


# ── Frontend ──────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("serve_all:app", host="0.0.0.0", port=port, log_level="info")
