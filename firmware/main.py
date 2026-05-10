#!/usr/bin/env python3
"""Full proof-of-concept entry point.

Pipeline:
    browser camera/test image -> streaming server (this process)
    -> perception.detect()    -> arena-cm goals
    -> planner.Navigator      -> driver (mock | turtle | hardware)

Usage:
    python firmware/main.py --driver=turtle    # press Go in viewer/phone to start
    python firmware/main.py --driver=mock      # headless dry run
    python firmware/main.py --driver=hardware  # on the rover
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "streaming"))

import perception  # noqa: E402
from controller import make_driver  # noqa: E402
from planner import Navigator, Pose, calculate_best_path  # noqa: E402
from streaming import server as stream_server  # noqa: E402


def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def run_mission(frame, driver_name: str, capacity: int, profile: str = "irl") -> None:
    det = perception.detect(frame, profile=profile)
    if det.deposit_cm is None and profile == "endurosat":
        raise RuntimeError("could not locate deposit pit (no yellow blob found)")
    if det.deposit_cm is not None:
        print(f"[mission] {len(det.resources_cm)} resources, deposit at "
              f"({det.deposit_cm[0]:.1f}, {det.deposit_cm[1]:.1f}) cm, "
              f"capacity={capacity}")
    else:
        print(f"[mission] {len(det.resources_cm)} resources, no deposit pit, "
              f"capacity={capacity}")

    start = Pose(x=60.0, y=115.0, heading=0.0)

    print(f"[mission] driver = {driver_name}")
    driver = make_driver(driver_name)
    driver.setup_view(perception.ARENA_W_CM, perception.ARENA_H_CM, start)
    nav = Navigator(driver, start)
    points = list(det.resources_cm)
    if det.deposit_cm is not None:
        points.append(det.deposit_cm)
    driver.draw_points(points)

    remaining = list(det.resources_cm)
    total = len(remaining)
    collected = 0
    trip = 0
    while remaining:
        trip += 1
        ordered_rest = calculate_best_path(nav.pose, remaining)
        batch = ordered_rest[:capacity]
        batch_set = set(batch)
        remaining = [r for r in remaining if r not in batch_set]
        print(f"[mission] trip {trip}: collect {len(batch)} "
              f"({collected + len(batch)}/{total} after dropoff)")
        for gx, gy in batch:
            nav.move_to_goal(gx, gy)
            collected += 1
            print(f"[mission]   picked up #{collected} ({gx:.1f}, {gy:.1f})")
        if det.deposit_cm is not None:
            nav.move_to_goal(*det.deposit_cm)
            print(f"[mission] trip {trip}: dropped {len(batch)} at pit "
                  f"({collected}/{total})")

    driver.stop()
    print(f"[mission] done in {trip} trip(s). final {nav.pose}")

    if driver_name == "turtle":
        print("close the turtle window to exit.")
        import turtle
        try:
            turtle.done()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver", default="turtle", choices=["mock", "turtle", "hardware"])
    ap.add_argument("--port", type=int, default=None,
                    help="server port (default 8443 if cert.pem present, else 8080)")
    ap.add_argument("--capacity", type=int, default=5,
                    help="resources to carry per trip before returning to the pit")
    ap.add_argument("--profile", default=perception.DEFAULT_PROFILE,
                    choices=perception.PROFILES,
                    help="perception color profile")
    args = ap.parse_args()

    stream_server.set_go_runner(
        lambda f: run_mission(f, args.driver, args.capacity, profile=args.profile)
    )

    ssl_ctx = stream_server.load_ssl_context()
    scheme = "https" if ssl_ctx else "http"
    port = args.port if args.port is not None else (8443 if ssl_ctx else 8080)
    if not ssl_ctx:
        print("[!] no cert.pem/key.pem - serving plain HTTP (use the test image"
              " or localhost; phones-on-LAN need HTTPS for getUserMedia)")

    stream_server.start_in_thread(port=port, ssl_context=ssl_ctx)
    stream_server.enable_detection(profile=args.profile)
    ip = _local_ip()
    print(f"[stream] phone:  {scheme}://{ip}:{port}/")
    print(f"[stream] viewer: {scheme}://{ip}:{port}/viewer")
    print("[stream] mission: POST /go or Go in viewer / phone")

    if args.capacity < 1:
        ap.error("--capacity must be >= 1")
    try:
        while True:
            frame = stream_server.pop_go_snapshot()
            if frame is None:
                time.sleep(0.1)
                continue
            stream_server.set_mission_busy(True)
            try:
                run_mission(frame, args.driver, args.capacity, profile=args.profile)
            except Exception as e:
                print(f"[mission] failed: {e}")
            finally:
                stream_server.set_mission_busy(False)
            if args.driver == "turtle":
                print("[main] turtle window closed; exiting.")
                return
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
