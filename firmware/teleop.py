#!/usr/bin/env python3
"""
Manual teleoperation controller for the lunar rover.

Opens a tkinter window (works over X11 forwarding) and lets you
drive the rover with WASD / arrow keys or on-screen buttons.

Usage:
    python teleop.py
"""

import tkinter as tk


def _create_robot():
    from gpiozero import Robot, PhaseEnableMotor
    from hal import LEFT_MOTOR_DIR_GPIO, LEFT_MOTOR_PWM_GPIO
    from hal import RIGHT_MOTOR_DIR_GPIO, RIGHT_MOTOR_PWM_GPIO

    return Robot(
        left=PhaseEnableMotor(LEFT_MOTOR_DIR_GPIO, LEFT_MOTOR_PWM_GPIO),
        right=PhaseEnableMotor(RIGHT_MOTOR_DIR_GPIO, RIGHT_MOTOR_PWM_GPIO),
    )


class TeleopApp:
    KEYS_FORWARD = {"w", "Up"}
    KEYS_BACKWARD = {"s", "Down"}
    KEYS_LEFT = {"a", "Left"}
    KEYS_RIGHT = {"d", "Right"}

    def __init__(self, robot) -> None:
        self._robot = robot
        self._speed: float = 0.5
        self._held: set[str] = set()

        self._root = tk.Tk()
        self._root.title("ROOMBA Teleop")
        self._root.configure(bg="#1e1e2e")
        self._root.resizable(False, False)

        self._build_ui()

        self._root.bind("<KeyPress>", self._on_key_press)
        self._root.bind("<KeyRelease>", self._on_key_release)
        self._root.protocol("WM_DELETE_WINDOW", self._quit)

    def _build_ui(self) -> None:
        style = {"bg": "#1e1e2e", "fg": "#cdd6f4"}
        btn_style = {
            "bg": "#313244",
            "fg": "#cdd6f4",
            "activebackground": "#45475a",
            "activeforeground": "#cdd6f4",
            "relief": "flat",
            "font": ("monospace", 14, "bold"),
            "width": 4,
            "height": 2,
        }

        title = tk.Label(
            self._root,
            text="ROOMBA Teleop",
            font=("monospace", 16, "bold"),
            **style,
        )
        title.pack(pady=(12, 4))

        hint = tk.Label(
            self._root,
            text="WASD / Arrow Keys to drive   |   Space = stop",
            font=("monospace", 10),
            **style,
        )
        hint.pack(pady=(0, 8))

        button_frame = tk.Frame(self._root, bg="#1e1e2e")
        button_frame.pack(pady=4)

        self._btn_fwd = tk.Button(button_frame, text="W\n▲", **btn_style)
        self._btn_fwd.grid(row=0, column=1, padx=4, pady=4)

        self._btn_left = tk.Button(button_frame, text="A\n◀", **btn_style)
        self._btn_left.grid(row=1, column=0, padx=4, pady=4)

        self._btn_stop = tk.Button(
            button_frame,
            text="STOP",
            bg="#f38ba8",
            fg="#1e1e2e",
            activebackground="#eba0ac",
            activeforeground="#1e1e2e",
            relief="flat",
            font=("monospace", 11, "bold"),
            width=4,
            height=2,
        )
        self._btn_stop.grid(row=1, column=1, padx=4, pady=4)

        self._btn_right = tk.Button(button_frame, text="D\n▶", **btn_style)
        self._btn_right.grid(row=1, column=2, padx=4, pady=4)

        self._btn_bwd = tk.Button(button_frame, text="S\n▼", **btn_style)
        self._btn_bwd.grid(row=2, column=1, padx=4, pady=4)

        for btn, press, release in [
            (self._btn_fwd, lambda: self._start("forward"), self._stop_motors),
            (self._btn_bwd, lambda: self._start("backward"), self._stop_motors),
            (self._btn_left, lambda: self._start("left"), self._stop_motors),
            (self._btn_right, lambda: self._start("right"), self._stop_motors),
            (self._btn_stop, self._stop_motors, None),
        ]:
            btn.bind("<ButtonPress-1>", lambda e, fn=press: fn())
            if release:
                btn.bind("<ButtonRelease-1>", lambda e, fn=release: fn())

        speed_frame = tk.Frame(self._root, bg="#1e1e2e")
        speed_frame.pack(pady=(8, 4))

        tk.Label(
            speed_frame, text="Speed:", font=("monospace", 11), **style
        ).pack(side="left", padx=(8, 4))

        self._speed_var = tk.DoubleVar(value=self._speed)
        speed_scale = tk.Scale(
            speed_frame,
            from_=0.1,
            to=1.0,
            resolution=0.05,
            orient="horizontal",
            variable=self._speed_var,
            command=self._on_speed_change,
            length=200,
            bg="#1e1e2e",
            fg="#cdd6f4",
            troughcolor="#313244",
            highlightthickness=0,
            font=("monospace", 10),
        )
        speed_scale.pack(side="left", padx=4)

        self._status_var = tk.StringVar(value="STOPPED")
        status = tk.Label(
            self._root,
            textvariable=self._status_var,
            font=("monospace", 12, "bold"),
            bg="#1e1e2e",
            fg="#a6e3a1",
        )
        status.pack(pady=(4, 12))

    def _direction_for_key(self, key: str) -> str | None:
        if key in self.KEYS_FORWARD:
            return "forward"
        if key in self.KEYS_BACKWARD:
            return "backward"
        if key in self.KEYS_LEFT:
            return "left"
        if key in self.KEYS_RIGHT:
            return "right"
        return None

    def _on_key_press(self, event: tk.Event) -> None:
        key = event.keysym
        if key == "space":
            self._held.clear()
            self._stop_motors()
            return
        if key == "q":
            self._quit()
            return
        direction = self._direction_for_key(key)
        if direction and key not in self._held:
            self._held.add(key)
            self._start(direction)

    def _on_key_release(self, event: tk.Event) -> None:
        key = event.keysym
        self._held.discard(key)
        if not self._held:
            self._stop_motors()
        else:
            remaining = next(iter(self._held))
            direction = self._direction_for_key(remaining)
            if direction:
                self._start(direction)

    def _start(self, direction: str) -> None:
        fn = getattr(self._robot, direction)
        fn(self._speed)
        label = direction.upper()
        self._status_var.set(f"{label}  ({self._speed:.2f})")

    def _stop_motors(self) -> None:
        self._robot.stop()
        self._status_var.set("STOPPED")

    def _on_speed_change(self, _value: str) -> None:
        self._speed = self._speed_var.get()

    def _quit(self) -> None:
        self._robot.stop()
        self._root.destroy()

    def run(self) -> None:
        self._root.mainloop()


def main() -> None:
    robot = _create_robot()
    app = TeleopApp(robot)
    app.run()


if __name__ == "__main__":
    main()
