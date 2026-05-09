# lunar-bitch firmware

Proof-of-concept autonomy stack for the rover. A phone (or laptop) films the
arena from above, ships frames to the RPi over Wi-Fi, the RPi detects every
resource and the deposit pit, plans a path, and drives the motors. Open-loop
dead reckoning — no rover localization, no real grasper. This is the smallest
thing that could plausibly play a round.

## Pipeline

```
[browser camera or test image]
        │  JPEG/PNG over WebSocket
        ▼
[streaming/server.py]   aiohttp on the RPi
        │  get_latest()  ->  np.ndarray (BGR)
        ▼
[perception.py]         OpenCV: HSV thresholds for the spec colors
        │  resources_cm: list[(x,y)]  +  deposit_cm
        ▼
[main.py]               trip-by-trip orchestration
        │  Pose  +  goals
        ▼
[planner.Navigator]     turn-then-forward, dead reckoning
        │  forward / turn_left / turn_right
        ▼
[controller.BaseDriver]
        ├── MockDriver        prints to stdout
        ├── TurtleDriver      Python turtle visualization (X11)
        └── HardwareDriver    gpiozero PhaseEnableRobot, real motors
```

Everything runs in **one process** started by `main.py`. The aiohttp server
lives on a daemon thread, the detection + navigation loop on the main thread.

## Files

| Path | What it is |
| --- | --- |
| `main.py` | Entry point. Hosts the server, waits for a frame, runs the mission. |
| `perception.py` | Pure-function arena detector (run standalone for HSV tuning). |
| `planner.py` | `Pose`, `Navigator`, `calculate_best_path` (nearest-neighbor TSP). |
| `controller.py` | `BaseDriver` strategy + the three concrete drivers + `make_driver()`. |
| `hal.py` | GPIO pin assignments. Edit these if the wiring changes. |
| `motor_sequence.py` | Standalone hardware smoke test — drives the motors with no perception/planning. |
| `streaming/server.py` | aiohttp WebSocket ingest, MJPEG viewer, `/static/`. |
| `streaming/phone.html` | Phone-side capture page (camera or test image). |
| `streaming/viewer.html` | Debug viewer that consumes `/mjpeg`. |
| `streaming/static/field.png` | Spec arena image, used as the no-camera test source. |
| `streaming/gen_cert.sh` | Generates self-signed cert for `getUserMedia` over LAN. |

## Hardware

Motors are wired through a phase/enable driver. Pins are in `hal.py`:

| Side | Direction (PHASE) | PWM (ENABLE) |
| --- | --- | --- |
| Left | GPIO 16 | GPIO 12 |
| Right | GPIO 20 | GPIO 13 |

The RPi needs to reach the camera device (phone or laptop) over the local
network. No internet required for the mission itself.

## Software setup

Python 3.11+. Dependencies: `aiohttp`, `opencv-python`, `numpy`, `gpiozero`
(only for `HardwareDriver`).

There's an existing venv at `firmware/webrtc/.venv` (legacy from the WebRTC
attempt) that already has `aiohttp`, `opencv-python`, and `numpy`. The
examples below reuse it:

```bash
firmware/webrtc/.venv/bin/python firmware/main.py ...
```

If you'd rather make a fresh one:

```bash
python -m venv firmware/.venv
firmware/.venv/bin/pip install aiohttp opencv-python numpy gpiozero
```

## Running on the RPi

The same binary handles everything; you pick behavior with flags.

### 1. Without the rover (visualization only)

Drives the turtle on an X-forwarded display. Good for verifying the
perception → planner → driver pipeline before touching motors.

```bash
firmware/webrtc/.venv/bin/python firmware/main.py --driver=turtle --capacity=5
```

Now open `http://<rpi-ip>:8080/` in any browser:

- **test image (field.png)** — sends the spec arena image; you should see
  exactly 40 resources detected. Use this for sanity checks.
- **phone camera** — uses `getUserMedia`. **Requires HTTPS or localhost** (see
  HTTPS section below).

Hit **start streaming**. After ~3 frames the turtle window pops up, the
rover starts working.

### 2. With the rover (real motors)

Same command, different driver:

```bash
firmware/webrtc/.venv/bin/python firmware/main.py --driver=hardware --capacity=5
```

`HardwareDriver` lives in `controller.py:138`. Two calibration constants
matter — both currently guesses, both must be measured before the rover
actually goes anywhere useful:

```python
SECONDS_PER_UNIT = 1.0           # seconds to travel 1 cm at SPEED=0.5
SECONDS_PER_DEGREE = 0.5 / 45.0  # seconds for 1° of in-place rotation
```

Calibration procedure: tape-measure on the floor, run
`motor_sequence.py` (which drives raw forward/turn sequences), time the
result, divide.

### 3. Headless dry-run (CI, debugging)

No display, no motors — just prints the move sequence. Useful when SSH'd
into the RPi without X forwarding.

```bash
firmware/webrtc/.venv/bin/python firmware/main.py --driver=mock --capacity=5
```

### Flags

```
--driver={mock|turtle|hardware}   default: turtle
--capacity N                      resources per trip before dropoff (default 5)
--port N                          server port (default 8443 if cert.pem else 8080)
--wait-frames N                   skip first N frames so JPEG is stable (default 3)
--timeout S                       give up if no frames arrive in S seconds (default 120)
```

## HTTPS / phones-on-LAN

`navigator.mediaDevices.getUserMedia` is gated behind a secure context. On a
phone connected over Wi-Fi, plain `http://<rpi-ip>:8080/` will throw — every
browser enforces this regardless of vendor (and on iOS, every browser is
Safari/WebKit underneath, so "switch to Chrome" doesn't help). Three options:

1. **Self-signed cert** (good for race day, no internet needed):
   ```bash
   ./firmware/streaming/gen_cert.sh
   ```
   Trust the cert on the phone (one-time pain on iOS, easier on Android).
   Server auto-detects `cert.pem` + `key.pem` next to `server.py` and serves
   on `:8443` instead of `:8080`.

2. **Tunnel** (good for development): `cloudflared tunnel --url http://localhost:8080`
   gives you a real HTTPS URL with a real cert. Requires internet.

3. **Test image** (no camera at all): pick *test image (field.png)* in the
   browser. No `getUserMedia` involved, plain HTTP works. This is the
   primary way to verify the pipeline without dealing with certs.

4. **Android escape hatch**: `chrome://flags` → "Insecure origins treated as
   secure" → add `http://<rpi-ip>:8080`. Not available on iOS.

## Debugging individual layers

Each module runs standalone for layer-by-layer verification.

**Perception** — sanity-check HSV thresholds against any image:
```bash
firmware/webrtc/.venv/bin/python firmware/perception.py path/to/frame.jpg
# prints detected coordinates, writes field_debug.jpg with overlays
```

**Streaming server** — without the planner stack:
```bash
firmware/webrtc/.venv/bin/python firmware/streaming/server.py
# open http://<rpi-ip>:8080/viewer to see the live MJPEG stream
```

**Planner only** — fixed test goals, no perception, no streaming:
```bash
firmware/webrtc/.venv/bin/python firmware/planner.py --driver=turtle
```

**Controller only** — runs `Rover.run_test_sequence()`, hits the driver
directly:
```bash
firmware/webrtc/.venv/bin/python firmware/controller.py --driver=mock
firmware/webrtc/.venv/bin/python firmware/controller.py --driver=hardware
```

**Motors only** — bypasses everything else, drives a hardcoded sequence:
```bash
firmware/webrtc/.venv/bin/python firmware/motor_sequence.py
```

## Coordinate frame

Defined by `perception.py` and the field overhead view:

- `(0, 0)` is the **top-left corner** of the play area, against the
  deposit-pit-side wall.
- `+x` extends 480 cm into the resource field.
- `+y` extends 230 cm down the wall (image-down convention; matches the
  overhead camera).
- Headings are degrees, math convention (`0° = +x`, increases counter-
  clockwise in the *math* sense — appears clockwise on the turtle window
  because we render y-down).
- Robot start pose is hardcoded in `main.py:74` as `Pose(x=10, y=115, 0)` —
  just inside the wall, vertically centered, facing into the field.

`perception.find_arena_bbox()` locates the play area inside the camera
frame (largest non-matte-black contour) and scales pixels → cm relative to
that, so the same code works for `field.png` (with its built-in margin) and
a real overhead camera shot (with whatever crop/perspective the phone
gives you).

## Known limits

These are POC scope, not bugs:

- **No rover localization.** Errors in heading and distance compound. After
  a few meters of driving the planner's pose and the actual rover pose will
  diverge. Closed-loop tracking via the same overhead camera is the obvious
  next step.
- **One-shot detection at mission start.** Resources don't move, so this is
  fine — but if the rover gets bumped, the arena detection isn't re-run.
- **No grasper.** Pickup is a `print("picked up")`. The rover currently
  drives over each resource and then drives to the pit; whatever happens
  to the resource physically is undefined.
- **HardwareDriver timing is uncalibrated.** See the calibration procedure
  above.
- **Visit-then-deposit policy.** Each trip carries up to `--capacity`
  resources back to the pit. Greedy nearest-neighbor with the trip start
  re-anchored at the pit between trips. Not provably optimal — fine for POC.
