#!/usr/bin/env python3
"""Top-down arena perception.

Takes a single BGR frame of the arena (overhead orthographic view, tight
crop, deposit-pit-side wall on the left) and returns:

    resources_cm   : list[(x_cm, y_cm)]   - dodecahedra positions
    deposit_cm     : (x_cm, y_cm) | None  - center of the yellow pit

Coordinate frame (per the spec sheet & the user's mapping):
  (0, 0)       = top-left arena corner (deposit-pit-side wall, top)
  (W, H)       = bottom-right corner; W = ARENA_W_CM, H = ARENA_H_CM
  Y is image-down (this matches the source image; planner accepts it).

Two detection profiles are available:

  endurosat  — competition spec colors (bright-blue resources, yellow pit,
               matte-black penalty walls).
  irl        — real-world testing with gray PLA stand-in resources on a
               dark surface.  No pit / arena border detection.

Spec colors (from EnduroSat-Endurance-Space-Race-2026.pdf):
  resources           bright blue   #067EC8
  deposit pit         yellow        #EDA600
  deposit pit border  red           #B30000
  base / resource     grey          #5A5A5A
  penalty walls       matte black   #131313
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import cv2
import numpy as np

ARENA_W_CM = 480.0
ARENA_H_CM = 230.0

PROFILES = ("endurosat", "irl")
DEFAULT_PROFILE = "irl"

# --- endurosat profile -------------------------------------------------
# OpenCV HSV: H in [0, 179], S/V in [0, 255].
BLUE_HSV_LO = np.array([90, 140, 60], dtype=np.uint8)    # ~#067EC8
BLUE_HSV_HI = np.array([115, 255, 255], dtype=np.uint8)

YELLOW_HSV_LO = np.array([15, 140, 120], dtype=np.uint8)  # ~#EDA600
YELLOW_HSV_HI = np.array([30, 255, 255], dtype=np.uint8)

# --- irl profile --------------------------------------------------------
GRAY_HSV_LO = np.array([0, 0, 140], dtype=np.uint8)
GRAY_HSV_HI = np.array([179, 60, 255], dtype=np.uint8)

RESOURCE_AREA_FRAC_MIN = 0.00005
RESOURCE_AREA_FRAC_MAX = 0.02


@dataclass
class Detection:
    resources_cm: list[tuple[float, float]]
    deposit_cm: tuple[float, float] | None
    image_size: tuple[int, int]   # (width_px, height_px)
    arena_bbox: tuple[int, int, int, int]  # (x, y, w, h) in pixels


def find_arena_bbox(frame_bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    """Locate the play-area bounding box.

    The arena floor (grey + white border + colored markings) sits inside a
    matte-black penalty perimeter (#131313). Largest non-black contour =
    the play area, which is exactly the 480x230 cm surface per the spec.
    """
    H, W = frame_bgr.shape[:2]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    black = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([179, 80, 60]))
    non_black = cv2.bitwise_not(black)
    non_black = cv2.morphologyEx(
        non_black, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))
    contours, _ = cv2.findContours(non_black, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(biggest)
    if w * h < 0.3 * W * H:
        return None  # not plausibly the arena
    return x, y, w, h


def _centroid(contour) -> tuple[float, float] | None:
    m = cv2.moments(contour)
    if m["m00"] <= 0:
        return None
    return m["m10"] / m["m00"], m["m01"] / m["m00"]


def _detect_resources_endurosat(
    frame_bgr: np.ndarray,
    arena_area: int,
    px_to_cm,
) -> list[tuple[float, float]]:
    blurred = cv2.GaussianBlur(frame_bgr, (3, 3), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, BLUE_HSV_LO, BLUE_HSV_HI)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    resources: list[tuple[float, float]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if not (4 <= area <= 0.01 * arena_area):
            continue
        ctr = _centroid(c)
        if ctr is not None:
            resources.append(px_to_cm(ctr[0], ctr[1]))
    return resources


def _detect_resources_irl(
    frame_bgr: np.ndarray,
    arena_area: int,
    img_w: int,
    img_h: int,
    px_to_cm,
) -> list[tuple[float, float]]:
    blurred = cv2.GaussianBlur(frame_bgr, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    gray_mask = cv2.inRange(hsv, GRAY_HSV_LO, GRAY_HSV_HI)
    gray_mask = cv2.morphologyEx(gray_mask, cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    gray_mask = cv2.morphologyEx(gray_mask, cv2.MORPH_CLOSE,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    contours, _ = cv2.findContours(gray_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    area_min = RESOURCE_AREA_FRAC_MIN * arena_area
    area_max = RESOURCE_AREA_FRAC_MAX * arena_area

    resources: list[tuple[float, float]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if not (area_min <= area <= area_max):
            continue
        perim = cv2.arcLength(c, True)
        if perim == 0:
            continue
        circularity = 4 * np.pi * area / (perim * perim)
        if circularity < 0.4:
            continue
        rx, ry, rw, rh = cv2.boundingRect(c)
        if min(rw, rh) / max(rw, rh) < 0.5:
            continue
        if rx == 0 or ry == 0 or rx + rw >= img_w or ry + rh >= img_h:
            continue
        ctr = _centroid(c)
        if ctr is not None:
            resources.append(px_to_cm(ctr[0], ctr[1]))
    return resources


def detect(frame_bgr: np.ndarray, profile: str = DEFAULT_PROFILE) -> Detection:
    """Return resources + deposit pit center in arena cm."""
    img_h, img_w = frame_bgr.shape[:2]
    bbox = find_arena_bbox(frame_bgr)
    if bbox is None:
        bbox = (0, 0, img_w, img_h)
    bx, by, bw, bh = bbox
    sx_cm = ARENA_W_CM / bw
    sy_cm = ARENA_H_CM / bh
    arena_area = bw * bh

    def px_to_cm(px: float, py: float) -> tuple[float, float]:
        return (px - bx) * sx_cm, (py - by) * sy_cm

    if profile == "endurosat":
        resources = _detect_resources_endurosat(frame_bgr, arena_area, px_to_cm)
    elif profile == "irl":
        resources = _detect_resources_irl(frame_bgr, arena_area, img_w, img_h, px_to_cm)
    else:
        raise ValueError(f"unknown profile {profile!r}, expected one of {PROFILES}")

    # --- deposit pit (yellow) — only meaningful for endurosat ---
    deposit_cm: tuple[float, float] | None = None
    if profile == "endurosat":
        hsv = cv2.cvtColor(cv2.GaussianBlur(frame_bgr, (3, 3), 0),
                           cv2.COLOR_BGR2HSV)
        yellow_mask = cv2.inRange(hsv, YELLOW_HSV_LO, YELLOW_HSV_HI)
        yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_CLOSE,
                                       cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        y_contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if y_contours:
            biggest = max(y_contours, key=cv2.contourArea)
            if cv2.contourArea(biggest) >= 20:
                ctr = _centroid(biggest)
                if ctr is not None:
                    deposit_cm = px_to_cm(ctr[0], ctr[1])

    return Detection(resources, deposit_cm, (img_w, img_h), bbox)


def annotate(frame_bgr: np.ndarray, det: Detection) -> np.ndarray:
    """Draw detections back onto a copy of the frame, for tuning."""
    out = frame_bgr.copy()
    bx, by, bw, bh = det.arena_bbox
    sx_cm = ARENA_W_CM / bw
    sy_cm = ARENA_H_CM / bh

    def cm_to_px(x_cm, y_cm):
        return int(bx + x_cm / sx_cm), int(by + y_cm / sy_cm)

    cv2.rectangle(out, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
    for x_cm, y_cm in det.resources_cm:
        cv2.circle(out, cm_to_px(x_cm, y_cm), 8, (0, 255, 0), 2)
    if det.deposit_cm is not None:
        cv2.drawMarker(out, cm_to_px(*det.deposit_cm), (0, 165, 255),
                       markerType=cv2.MARKER_CROSS, markerSize=24, thickness=3)
        px, py = cm_to_px(*det.deposit_cm)
        cv2.putText(out, "PIT", (px + 14, py - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
    cv2.putText(out, f"resources={len(det.resources_cm)}", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(out, f"arena bbox=({bx},{by})-({bx+bw},{by+bh})",
                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return out


def _cli(path: str, profile: str) -> None:
    frame = cv2.imread(path)
    if frame is None:
        print(f"could not read {path}", file=sys.stderr)
        sys.exit(2)
    det = detect(frame, profile=profile)
    print(f"[{profile}] image: {det.image_size[0]}x{det.image_size[1]} px "
          f"-> arena {ARENA_W_CM:.0f}x{ARENA_H_CM:.0f} cm")
    print(f"resources ({len(det.resources_cm)}):")
    for i, (x, y) in enumerate(det.resources_cm):
        print(f"  {i:2d}: ({x:6.1f}, {y:6.1f}) cm")
    print(f"deposit pit: {det.deposit_cm}")
    out_path = "field_debug.jpg"
    cv2.imwrite(out_path, annotate(frame, det))
    print(f"annotated -> {out_path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, choices=PROFILES)
    args = ap.parse_args()
    _cli(args.image, args.profile)
