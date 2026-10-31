"""Draw question/option boxes on a blank master page and print them as exam.yaml coordinates.

Opens a window: drag a box, press ENTER or SPACE to keep it, repeat; press ESC when done.
Boxes are numbered in the order drawn, and a preview image with the numbers is saved.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from .images import load_image


def define_regions(image_path: Path, max_w: int = 1400, max_h: int = 900) -> list[tuple[int, int, int, int]]:
    img = load_image(image_path)
    s = min(1.0, max_w / img.shape[1], max_h / img.shape[0])
    disp = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img.copy()
    title = "drag a box, ENTER to keep it, ESC when done"
    rois = cv2.selectROIs(title, disp, showCrosshair=False)
    cv2.destroyAllWindows()
    boxes = [tuple(round(v / s) for v in r) for r in rois] if len(rois) else []

    preview = img.copy()
    for i, (x, y, w, h) in enumerate(boxes, start=1):
        cv2.rectangle(preview, (x, y), (x + w, y + h), (255, 0, 255), 3)
        cv2.putText(preview, str(i), (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 255), 2)
    out = image_path.with_name(image_path.stem + "_regions.jpg")
    cv2.imwrite(str(out), preview)

    print(f"# {image_path.name}: {len(boxes)} boxes (preview: {out})")
    for i, b in enumerate(boxes, start=1):
        print(f"# {i}: [{b[0]}, {b[1]}, {b[2]}, {b[3]}]")
    return boxes
