"""
Phone -> RPi MJPEG-over-WebSocket streaming server.

Phone opens /  -> grabs camera with getUserMedia, draws frames to a
canvas, encodes each as JPEG, ships them over a WebSocket.

The server decodes each JPEG into an OpenCV BGR ndarray and stores
it in `latest_frame` for the recognition pipeline to consume.

A debug viewer is served at /viewer as an MJPEG <img> stream.

HTTPS:
  getUserMedia requires a secure context on every browser except
  localhost. Generate a self-signed cert next to this file:

      openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem \
        -out cert.pem -days 365 -subj "/CN=lunar-bitch"

  Then trust it on the phone (Safari: Settings -> General ->
  About -> Certificate Trust Settings). If cert.pem and key.pem
  are present, the server runs HTTPS; otherwise plain HTTP.
"""

import asyncio
import os
import ssl
import threading
import time

import cv2
import numpy as np
from aiohttp import WSMsgType, web

ROOT = os.path.dirname(__file__)
CERT = os.path.join(ROOT, "cert.pem")
KEY = os.path.join(ROOT, "key.pem")

# Latest decoded frame, shared with the recognition pipeline.
_frame_lock = threading.Lock()
latest_frame: np.ndarray | None = None
latest_frame_ts: float = 0.0

# Detection overlay state (populated by enable_detection worker).
_det_lock = threading.Lock()
_latest_detection: dict | None = None

# Optional POST /go mission trigger (enabled by firmware/main.py --wait-go).
_go_runner = None
_mission_lock = threading.Lock()
_mission_busy = False
_pending_go_snapshot: np.ndarray | None = None


def set_go_runner(fn) -> None:
    """Register mission entry; None disables POST /go."""
    global _go_runner
    _go_runner = fn


def set_mission_busy(busy: bool) -> None:
    global _mission_busy
    with _mission_lock:
        _mission_busy = busy


def pop_go_snapshot() -> np.ndarray | None:
    global _pending_go_snapshot
    with _mission_lock:
        snap = _pending_go_snapshot
        _pending_go_snapshot = None
        return snap


def set_latest(img: np.ndarray) -> None:
    global latest_frame, latest_frame_ts
    with _frame_lock:
        latest_frame = img
        latest_frame_ts = time.time()


def get_latest() -> tuple[np.ndarray | None, float]:
    with _frame_lock:
        return latest_frame, latest_frame_ts


def enable_detection(profile: str = "irl") -> None:
    """Start a background thread running perception.detect() on new frames.

    Results are served at GET /detections as JSON.  Runs at most once per
    second so it adds very little overhead to the streaming pipeline."""
    t = threading.Thread(target=_detection_worker, args=(profile,),
                         name="detection-worker", daemon=True)
    t.start()


def _detection_worker(profile: str) -> None:
    import sys as _sys
    firmware_dir = os.path.dirname(ROOT)
    if firmware_dir not in _sys.path:
        _sys.path.insert(0, firmware_dir)
    import perception  # noqa: E402

    global _latest_detection
    last_ts = 0.0
    while True:
        frame, ts = get_latest()
        if frame is not None and ts != last_ts:
            last_ts = ts
            try:
                det = perception.detect(frame, profile=profile)
                result = {
                    "resources": [list(r) for r in det.resources_cm],
                    "deposit": list(det.deposit_cm) if det.deposit_cm else None,
                    "arena_bbox": list(det.arena_bbox),
                    "image_size": list(det.image_size),
                    "ts": ts,
                }
                with _det_lock:
                    _latest_detection = result
            except Exception as e:
                print(f"[detect] {e}")
        time.sleep(1.0)


async def index(request: web.Request) -> web.Response:
    with open(os.path.join(ROOT, "phone.html")) as f:
        return web.Response(content_type="text/html", text=f.read())


async def viewer(request: web.Request) -> web.Response:
    with open(os.path.join(ROOT, "viewer.html")) as f:
        return web.Response(content_type="text/html", text=f.read())


async def ws_ingest(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(max_msg_size=8 * 1024 * 1024)
    await ws.prepare(request)
    peer = request.remote
    print(f"[ws] {peer} connected")

    count = 0
    t0 = time.time()
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                buf = np.frombuffer(msg.data, dtype=np.uint8)
                img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                set_latest(img)
                count += 1
                if count == 1:
                    cv2.imwrite(os.path.join(ROOT, "first_frame.jpg"), img)
                    h, w = img.shape[:2]
                    print(f"[ws] first frame {w}x{h}, saved first_frame.jpg")
                if count % 30 == 0:
                    dt = time.time() - t0
                    print(f"[ws] {count} frames, {count/dt:.1f} fps")
            elif msg.type == WSMsgType.ERROR:
                print(f"[ws] error: {ws.exception()}")
    finally:
        print(f"[ws] {peer} disconnected after {count} frames")
    return ws


async def detections_handler(request: web.Request) -> web.Response:
    with _det_lock:
        data = _latest_detection
    if data is None:
        return web.json_response(None)
    return web.json_response(data)


async def go_handler(request: web.Request) -> web.Response:
    global _pending_go_snapshot
    if _go_runner is None:
        return web.json_response(
            {"ok": False, "error": "run main.py with --wait-go"},
            status=503,
        )
    frame, _ = get_latest()
    if frame is None:
        return web.json_response({"ok": False, "error": "no frame yet"}, status=400)
    snap = frame.copy()
    with _mission_lock:
        if _mission_busy:
            return web.json_response(
                {"ok": False, "error": "mission already running"},
                status=409,
            )
        if _pending_go_snapshot is not None:
            return web.json_response(
                {"ok": False, "error": "mission already queued"},
                status=409,
            )
        _pending_go_snapshot = snap
    return web.json_response({"ok": True})


async def mjpeg(request: web.Request) -> web.StreamResponse:
    boundary = "frame"
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": f"multipart/x-mixed-replace; boundary={boundary}",
            "Cache-Control": "no-cache, private",
            "Pragma": "no-cache",
        },
    )
    await resp.prepare(request)

    last_ts = 0.0
    try:
        while True:
            img, ts = get_latest()
            if img is None or ts == last_ts:
                await asyncio.sleep(0.03)
                continue
            last_ts = ts
            ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                continue
            data = jpg.tobytes()
            await resp.write(
                b"--" + boundary.encode() + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n"
                + data + b"\r\n"
            )
            await asyncio.sleep(0.03)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    return resp


def _build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/viewer", viewer)
    app.router.add_get("/detections", detections_handler)
    app.router.add_post("/go", go_handler)
    app.router.add_get("/mjpeg", mjpeg)
    app.router.add_get("/ws", ws_ingest)
    app.router.add_static("/static/", os.path.join(ROOT, "static"))
    return app


def start_in_thread(port: int = 8080, ssl_context: ssl.SSLContext | None = None) -> threading.Thread:
    """Run the streaming server on a daemon thread with its own event loop.

    Lets a single-process orchestrator (firmware/main.py) host the server
    alongside the detection/navigation logic. Returns once the socket is
    bound (an `is_ready` Event blocks until then)."""
    is_ready = threading.Event()
    startup_error: list[BaseException] = []

    def run() -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            app = _build_app()
            runner = web.AppRunner(app)
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, host="0.0.0.0", port=port, ssl_context=ssl_context)
            loop.run_until_complete(site.start())
        except BaseException as e:
            startup_error.append(e)
            return
        finally:
            is_ready.set()
        loop.run_forever()

    t = threading.Thread(target=run, name="streaming-server", daemon=True)
    t.start()
    is_ready.wait(timeout=5.0)
    if startup_error:
        raise startup_error[0]
    return t


def load_ssl_context() -> ssl.SSLContext | None:
    if os.path.exists(CERT) and os.path.exists(KEY):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT, KEY)
        return ctx
    return None


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--detect", action="store_true",
                    help="enable live detection overlay on /viewer")
    ap.add_argument("--profile", default="irl", choices=("endurosat", "irl"))
    args = ap.parse_args()

    if args.detect:
        enable_detection(args.profile)

    app = _build_app()

    ssl_ctx = load_ssl_context()
    scheme = "https" if ssl_ctx else "http"
    if not ssl_ctx:
        print("[!] cert.pem/key.pem not found - serving plain HTTP.")
        print("    getUserMedia will only work on localhost without HTTPS.")

    port = 8443 if ssl_ctx else 8080
    print(f"Streaming server on {scheme}://0.0.0.0:{port}")
    print(f"  phone:  {scheme}://<rpi-ip>:{port}/")
    print(f"  viewer: {scheme}://<rpi-ip>:{port}/viewer")
    web.run_app(app, port=port, ssl_context=ssl_ctx)


if __name__ == "__main__":
    main()
