# engine/net_bridge.py
import os, json, mimetypes, requests
from pathlib import Path

API_URL = os.getenv("API_URL", "").rstrip("/")
ENGINE_SECRET = os.getenv("ENGINE_SECRET", "")
PUBLIC_BUCKET_URL = os.getenv("PUBLIC_BUCKET_URL", "").rstrip("/")
OFFER_ID = os.getenv("OFFER_ID", "")
RUN_ID = os.getenv("RUN_ID", "")

def _post(path, json_payload):
    if not API_URL:
        raise RuntimeError("API_URL missing")
    r = requests.post(
        f"{API_URL}{path}",
        headers={"Content-Type": "application/json", "x-engine-secret": ENGINE_SECRET},
        json=json_payload,
        timeout=30
    )
    r.raise_for_status()
    return r.json()

def _upload_file(local_path: Path, name_hint: str):
    # 1) presign
    mime, _ = mimetypes.guess_type(str(local_path))
    presign = _post(f"/offers/{OFFER_ID}/file/presign", {
        "filename": name_hint or local_path.name
    })
    # 2) PUT direct în Storage
    with open(local_path, "rb") as f:
        pr = requests.put(
            presign["uploadUrl"],
            data=f.read(),
            headers={"Content-Type": mime or "application/octet-stream"},
            timeout=180
        )
        pr.raise_for_status()
    # 3) înregistrare în DB
    reg = _post(f"/offers/{OFFER_ID}/file", {
        "storagePath": presign["storagePath"],
        "meta": {"filename": name_hint or local_path.name, "mime": mime}
    })
    # 4) URL public (bucket public)
    public_url = f"{PUBLIC_BUCKET_URL}/{presign['storagePath']}" if PUBLIC_BUCKET_URL else ""
    return {
        "id": reg.get("file_id"),
        "url": public_url,
        "mime": mime or "application/octet-stream",
        "caption": name_hint or local_path.name,
    }

def post_event(message: str, files=None):
    files = files or []
    file_entries = []
    for p in files:
        pp = Path(p)
        try:
            file_entries.append(_upload_file(pp, pp.name))
        except Exception as e:
            file_entries.append({"url": "", "mime": "text/plain", "caption": f"upload failed: {pp.name} ({e})"})
    payload = {"files": file_entries} if file_entries else None
    try:
        _post("/calc-events", {
            "run_id": RUN_ID, "level": "info", "message": message, "payload": payload
        })
    except Exception:
        _post("/calc-events", {
            "run_id": RUN_ID, "level": "info", "message": message
        })
    return True
