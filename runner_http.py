# engine/runner_http.py (REFACUT: detectare planuri înainte de cadrane)
# =====================================================================

from flask import Flask, request, jsonify
import os, subprocess, io, json, requests, sys, shutil
from pathlib import Path
from PIL import Image
from datetime import datetime

def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def trace(msg: str):
    print(f"[{ts()}] [TRACE] {msg}", flush=True)

# --- .env local -------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    trace("dotenv încărcat (runner_http)")
except Exception:
    trace("dotenv runner_http: nu pot încărca (ignor)")

app = Flask(__name__)

API_URL        = os.getenv("API_URL", "").rstrip("/")
ENGINE_SECRET  = os.getenv("ENGINE_SECRET", "")
PORT           = int(os.getenv("PORT", "5000"))
REUPLOAD       = (os.getenv("REUPLOAD_TO_STORAGE", "false").lower() == "true")

_WORKDIR_ENV = os.getenv("WORKDIR", "").strip()
if _WORKDIR_ENV and not os.path.isabs(_WORKDIR_ENV):
    WORKDIR = str((Path(__file__).resolve().parent / _WORKDIR_ENV).resolve())
else:
    WORKDIR = _WORKDIR_ENV
trace(f"WORKDIR={WORKDIR or '(unset)'}")

def api_headers():
    return {"Content-Type": "application/json", "x-engine-secret": ENGINE_SECRET}

def ensure_dir(p: str | Path):
    if not p:
        return
    Path(p).mkdir(parents=True, exist_ok=True)

def save_bytes(path: Path, data: bytes):
    ensure_dir(path.parent)
    path.write_bytes(data)

def save_jsonf(path: Path, obj: dict):
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def to_jpg_bytes(raw: bytes) -> bytes:
    im = Image.open(io.BytesIO(raw))
    if im.mode != "RGB":
        im = im.convert("RGB")
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=90)
    return out.getvalue()

def mirror_front_payload_to_runs(offer_id: str, run_id: str):
    """
    Descarcă exportul pentru ofertă și salvează local:
      - runs/<run_id>/export.json
      - runs/<run_id>/merged_form.json
      - runs/<run_id>/plan.jpg (și plan_original_*)
      - runs/<run_id>/segment_input.<ext>  (input determinist pentru segmentare)
      - engine/plan.jpg (copie pentru compatibilitate)
      - roof/selected_roof.json (dacă există)
    """
    if not API_URL or not ENGINE_SECRET:
        raise RuntimeError("API_URL/ENGINE_SECRET lipsesc în env")

    runs_root = Path(WORKDIR) if WORKDIR else None
    run_dir = (runs_root / run_id) if runs_root else None
    if run_dir:
        ensure_dir(run_dir)
        trace(f"mirror: run_dir set la {run_dir}")

    trace(f"GET {API_URL}/offers/{offer_id}/export")
    r = requests.get(f"{API_URL}/offers/{offer_id}/export", headers=api_headers(), timeout=90)
    r.raise_for_status()
    export = r.json()
    trace("export JSON primit")

    if run_dir:
        save_jsonf(run_dir / "export.json", export)
        trace("salvat runs/<id>/export.json")

    data = export.get("data") or {}
    if run_dir:
        save_jsonf(run_dir / "merged_form.json", data)
        trace("salvat runs/<id>/merged_form.json")

    tip_acoperis = ((data.get("sistemConstructiv") or {}).get("tipAcoperis") or "").strip()
    if tip_acoperis:
        ensure_dir(Path("roof"))
        Path("roof/selected_roof.json").write_text(
            json.dumps({"tipAcoperis": tip_acoperis}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        trace(f"roof/selected_roof.json scris (tipAcoperis={tip_acoperis})")

    segment_input_path: Path | None = None

    plan = (export.get("files") or {}).get("plan")
    if plan and plan.get("download_url"):
        meta = plan.get("meta") or {}
        original_name = meta.get("filename") or "plan.bin"
        trace(f"download plan: {original_name}")
        fr = requests.get(plan["download_url"], timeout=180)
        fr.raise_for_status()
        raw = fr.content

        ext = Path(original_name).suffix.lower() or ".bin"

        if run_dir:
            save_bytes(run_dir / f"plan_original_{original_name}", raw)
            trace("salvat plan_original_*")

            segment_input_path = run_dir / f"segment_input{ext}"
            save_bytes(segment_input_path, raw)
            trace(f"salvat segment_input la {segment_input_path}")

        dst_root = Path(__file__).resolve().parent / "plan.jpg"
        try:
            jpg = to_jpg_bytes(raw)
            if run_dir:
                save_bytes(run_dir / "plan.jpg", jpg)
            save_bytes(dst_root, jpg)
            trace("plan convertit în JPG și salvat la runs/<id>/plan.jpg + engine/plan.jpg")
        except Exception as e:
            trace(f"convert JPG eșuat, fallback dacă e deja JPG: {original_name}")
            if original_name.lower().endswith((".jpg", ".jpeg")):
                if run_dir:
                    save_bytes(run_dir / "plan.jpg", raw)
                save_bytes(dst_root, raw)

    return {
        "run_dir": str(run_dir) if run_dir else None,
        "segment_input": str(segment_input_path) if segment_input_path else None,
    }

def run_blocking_stream(cmd: list[str], cwd: Path, env: dict) -> int:
    """Rulează un proces *blocking* cu streaming live al stdout/stderr."""
    trace(f"EXEC: {' '.join(cmd)} | cwd={cwd}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()

@app.post("/run")
def run():
    """
    Flow nou:
      1) mirror payload (export + fișiere)
      2) rulează **detect_plans.py** (blocking, cu streaming) → scrie runs/<RUN_ID>/plans_list.json
      3) rulează **run_all_cadrans.py** (non-blocking pentru server, dar stdout e în terminalul engine)
    """
    if request.headers.get("x-engine-secret") != ENGINE_SECRET:
        trace("request fără x-engine-secret valid -> 403")
        return ("forbidden", 403)

    body = request.get_json() or {}
    offer = body.get("offerId")
    run_id = body.get("run_id")
    if not offer or not run_id:
        trace("body invalid (lipsă offerId/run_id) -> 400")
        return ("bad request", 400)

    trace(f"RUN request primit: offerId={offer}, run_id={run_id}")

    # 0) mirror date
    mirror_info = None
    try:
        mirror_info = mirror_front_payload_to_runs(offer, run_id)
    except Exception as e:
        app.logger.error(f"[runner] mirror failed: {e}")
        trace(f"mirror_front_payload_to_runs EROARE: {e}")

    # 1) env comun pentru detectare + cadrane
    env = os.environ.copy()
    env["API_URL"] = API_URL
    env["PUBLIC_BUCKET_URL"] = os.getenv("PUBLIC_BUCKET_URL") or ""
    env["ENGINE_SECRET"] = ENGINE_SECRET
    env["OFFER_ID"] = offer
    env["RUN_ID"] = run_id
    env["PYTHONUNBUFFERED"] = "1"
    env["WORKDIR"] = WORKDIR or ""
    env["RUNS_ROOT"] = WORKDIR or ""

    seg_path = ""
    if isinstance(mirror_info, dict):
        seg_path = mirror_info.get("segment_input") or ""
    env["SEGMENT_INPUT_PATH"] = seg_path
    trace(f"SEGMENT_INPUT_PATH setat la: {seg_path or '(nesetat)'}")

    # 2) DETECTARE PLANURI (blocking)
    python_bin = str((Path(os.getcwd()) / ".venv" / "bin" / "python"))
    detect_cmd = [python_bin, "-u", "detect_plans.py"]
    if not Path(python_bin).exists():
        detect_cmd = ["python3", "-u", "detect_plans.py"]
    trace("Pornesc detect_plans.py (blocking)...")
    ret = run_blocking_stream(detect_cmd, cwd=Path(os.getcwd()), env=env)
    if ret != 0:
        trace(f"detect_plans.py a eșuat (exit={ret}) -> 500")
        return ("detect plans failed", 500)

    # 3) PORNEȘTE PIPELINE-UL (non-blocking pentru server)
    run_cmd = [python_bin, "-u", "run_all_cadrans.py"]
    if not Path(python_bin).exists():
        run_cmd = ["python3", "-u", "run_all_cadrans.py"]
    trace("Pornesc run_all_cadrans.py (non-blocking pentru HTTP)...")

    try:
        subprocess.Popen(
            run_cmd,
            cwd=os.getcwd(),
            env=env,
            stdout=None,
            stderr=None,
            close_fds=False,
            text=True
        )
    except FileNotFoundError:
        trace("fallback: python3 -u run_all_cadrans.py")
        subprocess.Popen(
            ["python3", "-u", "run_all_cadrans.py"],
            cwd=os.getcwd(),
            env=env,
            stdout=None,
            stderr=None,
            close_fds=False,
            text=True
        )

    return jsonify({"ok": True, "run_id": run_id})

if __name__ == "__main__":
    trace(f"Flask start pe 0.0.0.0:{PORT}, reloader=OFF")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
