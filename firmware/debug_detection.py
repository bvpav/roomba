#!/usr/bin/env python3
"""Interactive debug visualizer for image detection.

Takes an image and displays it with detection overlays:
  - Green squares around detected resources
  - Red marker for the starting position
  - Orange cross for the deposit pit

Usage:
    python firmware/debug_detection.py path/to/image.jpg

Press 'q' or ESC to close the window.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import perception  # noqa: E402
from planner import Pose  # noqa: E402

# Robot start pose from main.py
START_POSE = Pose(x=10.0, y=115.0, heading=0.0)
RESOURCE_SIZE_CM = 2.5  # visual size for drawing squares


def visualize_detection(image_path: str) -> None:
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"error: could not read {image_path}", file=sys.stderr)
        sys.exit(2)

    print(f"loaded image: {frame.shape[1]}x{frame.shape[0]} px")
    det = perception.detect(frame)
    print(f"detected: {len(det.resources_cm)} resources, "
          f"deposit at {det.deposit_cm}, "
          f"arena bbox {det.arena_bbox}")

    # Create visualization
    out = frame.copy()
    bx, by, bw, bh = det.arena_bbox
    sx_cm = perception.ARENA_W_CM / bw
    sy_cm = perception.ARENA_H_CM / bh

    def cm_to_px(x_cm: float, y_cm: float) -> tuple[int, int]:
        return int(bx + x_cm / sx_cm), int(by + y_cm / sy_cm)

    # Draw arena bounding box
    cv2.rectangle(out, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)

    # Draw resources as squares
    for x_cm, y_cm in det.resources_cm:
        px, py = cm_to_px(x_cm, y_cm)
        half_size = int((RESOURCE_SIZE_CM / 2) / sx_cm)
        cv2.rectangle(
            out,
            (px - half_size, py - half_size),
            (px + half_size, py + half_size),
            (0, 255, 0),
            2,
        )

    # Draw starting position
    start_px, start_py = cm_to_px(START_POSE.x, START_POSE.y)
    cv2.drawMarker(
        out,
        (start_px, start_py),
        (0, 0, 255),
        markerType=cv2.MARKER_CROSS,
        markerSize=20,
        thickness=3,
    )
    cv2.putText(
        out,
        "START",
        (start_px + 14, start_py - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 255),
        2,
    )

    # Draw deposit pit
    if det.deposit_cm is not None:
        pit_px, pit_py = cm_to_px(*det.deposit_cm)
        cv2.drawMarker(
            out,
            (pit_px, pit_py),
            (0, 165, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=24,
            thickness=3,
        )
        cv2.putText(
            out,
            "PIT",
            (pit_px + 14, pit_py - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 165, 255),
            2,
        )

    # Draw info text
    cv2.putText(
        out,
        f"Resources: {len(det.resources_cm)}",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )
    cv2.putText(
        out,
        f"Image: {det.image_size[0]}x{det.image_size[1]} px",
        (10, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (200, 200, 200),
        2,
    )
    cv2.putText(
        out,
        f"Arena bbox: ({bx},{by})-({bx+bw},{by+bh})",
        (10, 76),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255),
        2,
    )

    # Display
    cv2.imshow("Detection Debug", out)
    print("displaying image... press 'q' or ESC to close")
    while True:
        key = cv2.waitKey(0) & 0xFF
        if key == ord("q") or key == 27:  # 'q' or ESC
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: debug_detection.py <image>", file=sys.stderr)
        sys.exit(2)
    visualize_detection(sys.argv[1])
