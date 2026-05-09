#!/usr/bin/env python3
"""
Motor sequence test for the lunar rover.
This script runs on Raspberry Pi 4 (roomba.local).
"""

from gpiozero import PhaseEnableRobot
from time import sleep

from hal import *

# --- CONFIGURATION / TUNING ---
# Adjust these values based on physical testing
SPEED = 0.5           # Motor speed (0.0 to 1.0)
SHORT_MOVE = 1.0      # Duration for forward/back bits (seconds)
TURN_45 = 0.5         # Estimated duration for a 45-degree turn (seconds)

# --- INITIALIZATION ---
# PhaseEnableRobot expects (phase, enable) for each motor
# In our setup: phase=DIR, enable=PWM
robot = PhaseEnableRobot(left=(LEFT_MOTOR_DIR_GPIO, LEFT_MOTOR_PWM_GPIO), right=(RIGHT_MOTOR_DIR_GPIO, RIGHT_MOTOR_PWM_GPIO))

def run_sequence():
    print("Starting sequence: Up a bit...")
    robot.forward(SPEED)
    sleep(SHORT_MOVE)

    print("Back a bit...")
    robot.backward(SPEED)
    sleep(SHORT_MOVE)

    print("45 degree turn...")
    # Using robot.right() for the turn; robot.left() is also available
    robot.right(SPEED)
    sleep(TURN_45)

    print("Back a bit...")
    robot.backward(SPEED)
    sleep(SHORT_MOVE)

    print("Forwards a bit...")
    robot.forward(SPEED)
    sleep(SHORT_MOVE)

    print("Sequence complete. Stopping.")
    robot.stop()

if __name__ == "__main__":
    try:
        run_sequence()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Stopping motors.")
        robot.stop()
