# engine/main.py
import io
import os
import requests
from PIL import Image
from flask import Flask, request, jsonify

API_URL = os.environ.get("API_URL", "http://localhost:4000")  # NEXT_PUBLIC_API_URL corespunzător pentru server
ENGINE_SECRET = os.environ.get("ENGINE_SECRET", "")

def api_headers():
    return {
        "Content-Type": "application/json",
        "x-engine-secret": ENGINE_SECRET,  # AnyAuthGuard te marchează ca user 'engine'
    }

def log(run_id, level, message, payload=None):
    try:
        requests.post(
            f"{API_URL}/calc-events",
            json={"run_id": run_id, "level": level, "message": message, "payload": payload},
            headers=api_headers(),
            timeout=20,
        )
    except Exception:
        pass

def finish_ok(offer_id, run_id, result):
    requests.post(
        f"{API_URL}/offers/{offer_id}/result",
        json={"run_id": run_id, "result": result},
        headers=api_headers(),
        timeout=30,
    )

def finish_fail(offer_id, run_id, error_msg):
    requests.post(
        f"{API_URL}/offers/{offer_id}/fail",
        json={"run_id": run_id, "error": {"message": error_msg}},
        headers=api_headers(),
        timeout=30,
    )

def to_jpg_bytes(raw_bytes, mime_hint: str) -> bytes:
    """
    Transformă ce poate în JPG.
    - jpg/jpeg/png -> convertește cu PIL
    - pdf/dwg -> aici ai nevoie de pipeline suplimentar (ex: pdf2image pentru PDF; pentru DWG conversie externă)
      Dacă nu ai suport, poți loga WARN și sări conversia.
    """
    mime = (mime_hint or "").lower()

    if "jpeg" in mime or "jpg" in mime or "png" in mime:
        im = Image.open(io.BytesIO(raw_bytes))
        # convert to RGB (fără canal alfa) ca să salvăm JPEG valid
        if im.mode != "RGB":
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=90)
        return out.getvalue()

    if "pdf" in mime:
        # exemplu: dacă vrei să convertești prima pagină PDF -> JPG:
        # from pdf2image import convert_from_bytes
        # images = convert_from_bytes(raw_bytes, first_page=1, last_page=1, dpi=200)
        # out = io.BytesIO()
        # images[0].save(out, format='JPEG', quality=90)
        # return out.getvalue()
        # fallback:
        raise RuntimeError("PDF to JPG conversion not implemented (install pdf2image & poppler)")

    if "dwg" in mime:
        raise RuntimeError("DWG to JPG conversion not implemented")

    # fallback: încercăm cu PIL orbește
    try:
        im = Image.open(io.BytesIO(raw_bytes))
        if im.mode != "RGB":
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        raise RuntimeError(f"Unsupported MIME for JPG conversion: {mime}")

app = Flask(__name__)

@app.post("/run")
def run():
    body = request.get_json(force=True) or {}
    offer_id = body.get("offerId")
    run_id = body.get("run_id")

    if not (offer_id and run_id):
        return jsonify({"error": "missing params"}), 400

    try:
        log(run_id, "info", f"Start run for offer {offer_id}")

        # 1) cere exportul
        r = requests.get(f"{API_URL}/offers/{offer_id}/export", headers=api_headers(), timeout=60)
        r.raise_for_status()
        export = r.json()

        data = export.get("data") or {}
        plan = (export.get("files") or {}).get("plan") or None

        plan_jpg_b64 = None
        if plan and plan.get("download_url"):
            # 2) descarcă planul
            fr = requests.get(plan["download_url"], timeout=120)
            fr.raise_for_status()
            raw = fr.content
            mime = ((plan.get("meta") or {}).get("mime") or "")

            # 3) convertește în JPG dacă e cazul
            jpg_bytes = to_jpg_bytes(raw, mime_hint=mime)

            # opțional: salvează în supabase înapoi sau returnează ca b64 în result
            import base64
            plan_jpg_b64 = base64.b64encode(jpg_bytes).decode("ascii")

        # 4) compune rezultatul pentru backend (poți salva payloadul complet)
        result = {
            "merged_form": data,
            "plan_jpg_b64": plan_jpg_b64,   # sau un path/URL dacă preferi să re-uploadezi
        }

        # 5) done
        finish_ok(offer_id, run_id, result)
        log(run_id, "info", "Run finished successfully")
        return jsonify({"ok": True})
    except Exception as e:
        msg = str(e)
        log(run_id, "error", "Run failed", {"error": msg})
        finish_fail(offer_id, run_id, msg)
        return jsonify({"error": msg}), 500
