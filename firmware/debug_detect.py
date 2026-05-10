#!/usr/bin/env python3
"""Visual debugger for perception.detect().

Opens an OpenCV window showing detection results overlaid on the input image:
  - Green rectangles around each detected resource
  - Orange cross + label for the deposit pit
  - Magenta diamond for the rover starting point
  - Yellow rectangle for the detected arena bounding box

Usage:
    python firmware/debug_detect.py <image> [<image> ...]
    python firmware/debug_detect.py --profile=endurosat <image>

Keys:
    Left/Right or A/D  — cycle through images (when multiple)
    Q or Escape         — quit
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cv2
import numpy as np

import perception

START_X_CM = 60.0
START_Y_CM = 115.0

WINDOW = "perception debug"


def draw_detections(frame_bgr: np.ndarray, det: perception.Detection) -> np.ndarray:
    out = frame_bgr.copy()
    bx, by, bw, bh = det.arena_bbox
    sx_cm = perception.ARENA_W_CM / bw
    sy_cm = perception.ARENA_H_CM / bh

    def cm_to_px(x_cm: float, y_cm: float) -> tuple[int, int]:
        return int(bx + x_cm / sx_cm), int(by + y_cm / sy_cm)

    cv2.rectangle(out, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)

    half = 10
    for i, (x_cm, y_cm) in enumerate(det.resources_cm):
        cx, cy = cm_to_px(x_cm, y_cm)
        cv2.rectangle(out, (cx - half, cy - half), (cx + half, cy + half), (0, 255, 0), 2)
        cv2.putText(out, str(i), (cx + half + 2, cy + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    if det.deposit_cm is not None:
        px, py = cm_to_px(*det.deposit_cm)
        cv2.drawMarker(out, (px, py), (0, 165, 255),
                       markerType=cv2.MARKER_CROSS, markerSize=24, thickness=3)
        cv2.putText(out, "PIT", (px + 14, py - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

    sx, sy = cm_to_px(START_X_CM, START_Y_CM)
    d = 12
    pts = np.array([[sx, sy - d], [sx + d, sy], [sx, sy + d], [sx - d, sy]], dtype=np.int32)
    cv2.polylines(out, [pts], isClosed=True, color=(255, 0, 255), thickness=2)
    cv2.putText(out, "START", (sx + d + 2, sy + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

    cv2.putText(out, f"resources: {len(det.resources_cm)}", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    if det.deposit_cm:
        cv2.putText(out, f"pit: ({det.deposit_cm[0]:.0f}, {det.deposit_cm[1]:.0f}) cm",
                    (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", metavar="image")
    ap.add_argument("--profile", default=perception.DEFAULT_PROFILE,
                    choices=perception.PROFILES)
    args = ap.parse_args()

    profile = args.profile
    frames: list[tuple[str, np.ndarray]] = []
    for p in args.images:
        img = cv2.imread(p)
        if img is None:
            print(f"warning: could not read {p}, skipping", file=sys.stderr)
            continue
        frames.append((p, img))

    if not frames:
        print("no valid images", file=sys.stderr)
        sys.exit(2)

    idx = 0
    dirty = True
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    while True:
        if dirty:
            name, frame = frames[idx]
            det = perception.detect(frame, profile=profile)
            vis = draw_detections(frame, det)
            label = f"[{idx + 1}/{len(frames)}] {Path(name).name} ({profile})"
            cv2.putText(vis, label, (10, vis.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow(WINDOW, vis)
            cv2.resizeWindow(WINDOW, min(vis.shape[1], 1400), min(vis.shape[0], 900))
            dirty = False

        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key in (ord("d"), 83) and len(frames) > 1:  # right arrow
            idx = (idx + 1) % len(frames)
            dirty = True
        elif key in (ord("a"), 81) and len(frames) > 1:  # left arrow
            idx = (idx - 1) % len(frames)
            dirty = True

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
