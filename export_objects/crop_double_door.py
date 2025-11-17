from PIL import Image
from pathlib import Path
import json, argparse
from ui_export import record_image

def crop_from_pred(img, p):
    x1, y1 = int(p["x"] - p["width"]/2), int(p["y"] - p["height"]/2)
    x2, y2 = int(p["x"] + p["width"]/2), int(p["y"] + p["height"]/2)
    return img.crop((x1, y1, x2, y2))

def export_rotations(crop, out_dir, base_name):
    out_dir.mkdir(parents=True, exist_ok=True)
    for ang in [0, 90, 180, 270]:
        rot = crop.rotate(ang, expand=True)
        for flip_name, flip in [("none", None), ("flipH", Image.FLIP_LEFT_RIGHT),
                                ("flipV", Image.FLIP_TOP_BOTTOM), ("flipHV", ("both",))]:
            if flip == ("both",):
                img_out = rot.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM)
            elif flip:
                img_out = rot.transpose(flip)
            else:
                img_out = rot
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

    out_dir = Path(args.out_root) / "double_door"
    for i, p in enumerate([p for p in preds if "double-door" in str(p["class"]).lower()]):
        crop = crop_from_pred(img, p)
        export_rotations(crop, out_dir, f"double_door_{i}")

if __name__ == "__main__":
    main()
