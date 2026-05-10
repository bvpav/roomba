#!/usr/bin/env python3
"""
Motor sequence test for the lunar rover.
This script runs on Raspberry Pi 4 (roomba.local).
"""

from gpiozero import Robot, PhaseEnableMotor
from time import sleep

from hal import *

# --- CONFIGURATION / TUNING ---
# Adjust these values based on physical testing
SPEED = 1.0           # Motor speed (0.0 to 1.0)
SHORT_MOVE = 1.0      # Duration for forward/back bits (seconds)
TURN_45 = 0.5         # Estimated duration for a 45-degree turn (seconds)

# --- INITIALIZATION ---
# Workaround for gpiozero 2.0.1 bug in PhaseEnableRobot
robot = Robot(
    left=PhaseEnableMotor(LEFT_MOTOR_DIR_GPIO, LEFT_MOTOR_PWM_GPIO),
    right=PhaseEnableMotor(RIGHT_MOTOR_DIR_GPIO, RIGHT_MOTOR_PWM_GPIO),
)

def run_sequence():
    print("Starting sequence: Up a bit...")
    while True:
        robot.forward(SPEED)
        sleep(SHORT_MOVE)

    robot.stop()

if __name__ == "__main__":
    try:
        run_sequence()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Stopping motors.")
        robot.stop()
