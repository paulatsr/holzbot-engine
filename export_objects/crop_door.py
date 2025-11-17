from PIL import Image
from pathlib import Path
import json, argparse
from typing import Dict, Any, List, Tuple
from ui_export import record_image

def cxcywh_to_xyxy(xc, yc, w, h):
    return int(xc - w/2), int(yc - h/2), int(xc + w/2), int(yc + h/2)

def clamp_xyxy(x1, y1, x2, y2, W, H):
    return max(0, x1), max(0, y1), min(W, x2), min(H, y2)

def crop_from_pred(img, pred):
    x1, y1, x2, y2 = cxcywh_to_xyxy(pred["x"], pred["y"], pred["width"], pred["height"])
    x1, y1, x2, y2 = clamp_xyxy(x1, y1, x2, y2, *img.size)
    return img.crop((x1, y1, x2, y2))

def export_rotations(crop, out_dir, base_name):
    out_dir.mkdir(parents=True, exist_ok=True)
    angles = [0, 90, 180, 270]
    flips = {
        "none": None,
        "flipH": Image.FLIP_LEFT_RIGHT,
        "flipV": Image.FLIP_TOP_BOTTOM,
        "flipHV": ("both",)
    }

    for ang in angles:
        rot = crop.rotate(ang, expand=True)
        for flip_name, flip_mode in flips.items():
            if flip_mode is None:
                img_out = rot
            elif flip_mode == ("both",):
                img_out = rot.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM)
            else:
                img_out = rot.transpose(flip_mode)
            img_out.save(out_dir / f"{base_name}_{ang}_{flip_name}.png")

            try:
                if ang in (0, 90) and flip_name in ("none", "flipH"):
                    record_image(out_dir / f"{base_name}_{ang}_{flip_name}.png",
                                stage="export_objects",
                                caption=f"Template {base_name} (aug: ang={ang}, flip={flip_name}).")
            except Exception:
                pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--out-root", default=".")
    args = ap.parse_args()

    img = Image.open(args.image)
    preds = json.load(open(args.json))["predictions"]

    out_dir = Path(args.out_root) / "door"
    for i, p in enumerate([
        p for p in preds
        if (
            ("door" in str(p["class"]).lower()) and
            ("double" not in str(p["class"]).lower())
        )
    ]):
        crop = crop_from_pred(img, p)
        export_rotations(crop, out_dir, f"door_{i}")

if __name__ == "__main__":
    main()
