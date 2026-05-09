#!/usr/bin/env python3
"""
Turtle Motion Abstraction for the lunar rover.
Implements the Strategy Pattern to allow swapping between hardware and mock drivers.
"""

import time
from abc import ABC, abstractmethod
from typing import List, Tuple

# --- ABSTRACTION LAYER (STRATEGY INTERFACE) ---

class BaseDriver(ABC):
    @abstractmethod
    def forward(self, amount: float):
        pass

    @abstractmethod
    def backward(self, amount: float):
        pass

    @abstractmethod
    def turn_right(self, degrees: float):
        pass

    @abstractmethod
    def turn_left(self, degrees: float):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def draw_points(self, points: List[Tuple[float, float]]):
        """Draws target points on the visualization or logs them."""
        pass

# --- CONCRETE STRATEGIES ---

class MockDriver(BaseDriver):
    """Prints commands to the terminal for debugging without hardware."""
    def forward(self, amount):
        print(f"[MOCK] Forward: {amount} units")

    def backward(self, amount):
        print(f"[MOCK] Backward: {amount} units")

    def turn_right(self, degrees):
        print(f"[MOCK] Turn Right: {degrees}°")

    def turn_left(self, degrees):
        print(f"[MOCK] Turn Left: {degrees}°")

    def stop(self):
        print("[MOCK] Stop")

    def draw_points(self, points):
        print(f"[MOCK] Drawing {len(points)} points: {points}")

class TurtleDriver(BaseDriver):
    """Visualizes movement using Python's turtle library (requires X11)."""
    def __init__(self):
        import turtle
        self.screen = turtle.Screen()
        self.screen.title("Lunar Rover Visualization")
        # Disable automatic updates for perfect control over drawing buffer
        self.screen.tracer(0)
        
        self.t = turtle.Turtle()
        self.t.shape("turtle")
        self.t.color("green")
        self.t.pensize(2)
        
        # Persistent marker turtle for goals
        self.marker = turtle.Turtle()
        self.marker.hideturtle()
        self.marker.penup()
        self.marker.color("red")
        
        print("[TURTLE] Initialized X11 Visualization")
        self.screen.update()

    def draw_points(self, points):
        """Draws red dots at each goal point."""
        for x, y in points:
            self.marker.goto(x, y)
            self.marker.dot(10)
        self.screen.update()

    def forward(self, amount):
        # Animate forward move manually for tracer(0)
        step = 5
        moved = 0
        while moved < amount:
            current_step = min(step, amount - moved)
            self.t.forward(current_step)
            moved += current_step
            self.screen.update()
            time.sleep(0.01)

    def backward(self, amount):
        # Animate backward move manually
        step = 5
        moved = 0
        while moved < amount:
            current_step = min(step, amount - moved)
            self.t.backward(current_step)
            moved += current_step
            self.screen.update()
            time.sleep(0.01)

    def turn_right(self, degrees):
        # Animate rotation manually
        step = 2
        turned = 0
        while turned < degrees:
            current_step = min(step, degrees - turned)
            self.t.right(current_step)
            turned += current_step
            self.screen.update()
            time.sleep(0.01)

    def turn_left(self, degrees):
        # Animate rotation manually
        step = 2
        turned = 0
        while turned < degrees:
            current_step = min(step, degrees - turned)
            self.t.left(current_step)
            turned += current_step
            self.screen.update()
            time.sleep(0.01)

    def stop(self):
        self.screen.update()

class HardwareDriver(BaseDriver):
    """Controls the actual GPIO pins on the RPi4."""
    def __init__(self, left_pins=(16, 12), right_pins=(20, 13)):
        from gpiozero import PhaseEnableRobot
        self.robot = PhaseEnableRobot(left=left_pins, right=right_pins)
        
        # Tuning factors (adjust these after physical testing)
        self.SPEED = 0.5
        self.SECONDS_PER_UNIT = 1.0  # How many seconds to move 1 "unit"
        self.SECONDS_PER_DEGREE = 0.5 / 45.0  # Estimate: 0.5s for a 45° turn

    def forward(self, amount):
        print(f"[HW] Forward {amount}")
        self.robot.forward(self.SPEED)
        time.sleep(amount * self.SECONDS_PER_UNIT)
        self.robot.stop()

    def backward(self, amount):
        print(f"[HW] Backward {amount}")
        self.robot.backward(self.SPEED)
        time.sleep(amount * self.SECONDS_PER_UNIT)
        self.robot.stop()

    def turn_right(self, degrees):
        print(f"[HW] Turn Right {degrees}°")
        self.robot.right(self.SPEED)
        time.sleep(degrees * self.SECONDS_PER_DEGREE)
        self.robot.stop()

    def turn_left(self, degrees):
        print(f"[HW] Turn Left {degrees}°")
        self.robot.left(self.SPEED)
        time.sleep(degrees * self.SECONDS_PER_DEGREE)
        self.robot.stop()

    def stop(self):
        print("[HW] Stop")
        self.robot.stop()

    def draw_points(self, points):
        """Hardware doesn't draw points, so this is a no-op."""
        pass

# --- CONTEXT CLASS ---

class Rover:
    """The high-level interface for the robot."""
    def __init__(self, driver: BaseDriver):
        self.driver = driver

    def run_test_sequence(self):
        """Executes: up a bit, turn 45, forwards a bit, turn back, forwards a bit."""
        print("\n--- Executing Movement Sequence (FORWARD ONLY) ---")
        self.driver.forward(100.0)
        self.driver.turn_right(45)
        self.driver.forward(50.0)
        self.driver.turn_left(45)
        self.driver.forward(100.0)
        self.driver.stop()
        print("--- Sequence Complete ---\n")

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    import sys
    
    # 1. Driver Selection
    use_turtle = "--visualize" in sys.argv
    
    if use_turtle:
        print("Initializing Turtle Driver...")
        driver = TurtleDriver()
    else:
        print("Testing with Mock Driver (Debug Mode):")
        driver = MockDriver()

    # 2. Execute Sequence
    rover = Rover(driver)
    rover.run_test_sequence()

    # 3. Finalization
    if use_turtle:
        print("Done! Close the window to exit.")
        import turtle
        turtle.done()
    
    print("To test on hardware, initialize Rover with HardwareDriver().")
