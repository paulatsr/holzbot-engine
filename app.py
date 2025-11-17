import os
import io
import json
import base64
import logging
import pathlib
import requests
from flask import Flask, request, jsonify
from PIL import Image
from dotenv import load_dotenv

# ================== Config ==================
load_dotenv()

API_URL = os.environ.get("API_URL", "http://localhost:4000")
ENGINE_SECRET = os.environ.get("ENGINE_SECRET", "")
PORT = int(os.environ.get("PORT", "5001"))
HOST = os.environ.get("HOST", "0.0.0.0")

# opțional: salvează artefacte local pentru debug
WORKDIR = os.environ.get("WORKDIR", "").strip()  # e.g. "./runs" (dacă e gol => nu salvează)

# opțional: în loc de base64 în result, reîncarcă plan.jpg în Storage și trimite doar path-ul
REUPLOAD_TO_STORAGE = (os.environ.get("REUPLOAD_TO_STORAGE", "false").lower() == "true")

# ================== Helpers ==================
def api_headers():
    return {
        "Content-Type": "application/json",
        "x-engine-secret": ENGINE_SECRET,
    }

def ensure_dir(path: str):
    if not path:
        return
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)

def save_bytes(path: str, data: bytes):
    if not path:
        return
    ensure_dir(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(data)

def save_json(path: str, obj: dict):
    if not path:
        return
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def log_event(run_id, level, message, payload=None):
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
        timeout=60,
    )

def finish_fail(offer_id, run_id, error_msg):
    requests.post(
        f"{API_URL}/offers/{offer_id}/fail",
        json={"run_id": run_id, "error": {"message": error_msg}},
        headers=api_headers(),
        timeout=60,
    )

def to_jpg_bytes(raw_bytes: bytes) -> bytes:
    """Convertește orice imagine suportată de PIL în JPEG (RGB)."""
    im = Image.open(io.BytesIO(raw_bytes))
    if im.mode != "RGB":
        im = im.convert("RGB")
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=90)
    return out.getvalue()

def upload_to_storage(offer_id: str, filename: str, content_type: str, data: bytes):
    """Flux engine -> presign -> PUT -> register; întoarce storage_path + file_id."""
    presign = requests.post(
        f"{API_URL}/offers/{offer_id}/file/presign",
        json={"filename": filename, "contentType": content_type, "size": len(data)},
        headers=api_headers(),
        timeout=30,
    )
    presign.raise_for_status()
    pjson = presign.json()
    upload_url = pjson["uploadUrl"]
    storage_path = pjson["storagePath"]

    put = requests.put(upload_url, data=data, headers={"Content-Type": content_type}, timeout=120)
    put.raise_for_status()

    reg = requests.post(
        f"{API_URL}/offers/{offer_id}/file",
        json={
            "storagePath": storage_path,
            "meta": {"filename": filename, "kind": "planJpg", "mime": content_type, "size": len(data)},
        },
        headers=api_headers(),
        timeout=30,
    )
    reg.raise_for_status()
    rjson = reg.json()
    return {"storage_path": storage_path, "file_id": rjson.get("file_id")}

# ================== App ==================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

@app.get("/health")
def health():
    return {"ok": True, "api": API_URL}

@app.post("/run")
def run():
    body = request.get_json(force=True) or {}
    offer_id = body.get("offerId")
    run_id = body.get("run_id")

    if not ENGINE_SECRET:
        return jsonify({"error": "ENGINE_SECRET missing in env"}), 500

    if not (offer_id and run_id):
        return jsonify({"error": "missing offerId/run_id"}), 400

    run_dir = os.path.join(WORKDIR, str(run_id)) if WORKDIR else ""

    try:
        app.logger.info(f"[run {run_id}] start for offer {offer_id}")
        log_event(run_id, "info", f"Engine start for offer {offer_id}")

        # 1) Trage exportul (JSON cu form + link semnat pentru plan)
        r = requests.get(f"{API_URL}/offers/{offer_id}/export", headers=api_headers(), timeout=90)
        r.raise_for_status()
        export = r.json()

        # Salvare debug: export.json
        if run_dir:
            save_json(os.path.join(run_dir, "export.json"), export)

        data = export.get("data") or {}
        plan = (export.get("files") or {}).get("plan")

        # Salvare debug: merged_form.json
        if run_dir:
            save_json(os.path.join(run_dir, "merged_form.json"), data)

        plan_jpg_b64 = None
        plan_jpg_ref = None  # dacă reîncărcăm în Storage

        if plan and plan.get("download_url"):
            meta = plan.get("meta") or {}
            filename = meta.get("filename") or "plan.bin"
            mime = meta.get("mime") or "application/octet-stream"

            # 2) Descarcă planul
            fr = requests.get(plan["download_url"], timeout=180)
            fr.raise_for_status()
            raw = fr.content

            # Debug: salvează originalul
            if run_dir:
                save_bytes(os.path.join(run_dir, f"plan_original_{filename}"), raw)

            try:
                # 3) Convertește în JPG (dacă e deja JPG/PNG funcționează direct; PDF/DWG vor eșua aici)
                jpg_bytes = to_jpg_bytes(raw)

                # Debug: salvează plan.jpg local
                if run_dir:
                    save_bytes(os.path.join(run_dir, "plan.jpg"), jpg_bytes)

                app.logger.info(f"[run {run_id}] plan.jpg ready ({len(jpg_bytes)} bytes)")

                if REUPLOAD_TO_STORAGE:
                    # 4A) Re-urcă în Storage și trimite doar referința
                    app.logger.info(f"[run {run_id}] reuploading plan.jpg to Storage")
                    ref = upload_to_storage(offer_id, "plan.jpg", "image/jpeg", jpg_bytes)
                    plan_jpg_ref = ref  # {'storage_path': ..., 'file_id': ...}
                else:
                    # 4B) Trimite ca base64 (atenție la limitele de body; vezi setările din Nest main.ts)
                    plan_jpg_b64 = base64.b64encode(jpg_bytes).decode("ascii")

            except Exception as e:
                # PDF / DWG / alte formate nesuportate → marchează WARN (poți implementa pdf2image dacă vrei)
                msg = f"Plan conversion failed (maybe PDF/DWG): {e}"
                app.logger.warning(f"[run {run_id}] {msg}")
                log_event(run_id, "warn", "Plan conversion failed (maybe PDF/DWG).", {"error": str(e)})

        # 5) Aici pui calculele tale propriu-zise...
        # Pentru exemplu, trimitem doar payload-ul:
        result_payload = {
            "merged_form": data,
            # Unul din cele două de mai jos, în funcție de opțiune:
            "plan_jpg_b64": plan_jpg_b64,     # dacă REUPLOAD_TO_STORAGE = false
            "plan_jpg_ref": plan_jpg_ref,     # dacă REUPLOAD_TO_STORAGE = true
        }

        # 6) Finalizează
        finish_ok(offer_id, run_id, result_payload)
        log_event(run_id, "info", "Engine finished successfully")
        app.logger.info(f"[run {run_id}] done")
        return jsonify({"ok": True})
    except Exception as e:
        msg = str(e)
        app.logger.error(f"[run {run_id}] failed: {msg}")
        log_event(run_id, "error", "Run failed", {"error": msg})
        finish_fail(offer_id, run_id, msg)
        return jsonify({"error": msg}), 500

if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
