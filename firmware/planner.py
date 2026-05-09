#!/usr/bin/env python3
"""
Path Planner and Navigator for the lunar rover.
Uses a coordinate system (cm) and converts absolute goals into relative movements.
"""

import math
import sys
from typing import List, Tuple
from controller import BaseDriver, _parse_driver_arg, make_driver

class Pose:
    """Represents the position and heading of the rover."""
    def __init__(self, x: float, y: float, heading: float):
        self.x = x
        self.y = y
        self.heading = heading  # Degrees, 0 is along +X axis

    def __repr__(self):
        return f"Pose(x={self.x:.1f}, y={self.y:.1f}, head={self.heading:.1f}°)"

class Navigator:
    """Translates absolute goals into relative driver commands."""
    def __init__(self, driver: BaseDriver, start_pose: Pose):
        self.driver = driver
        self.pose = start_pose

    def move_to_goal(self, tx: float, ty: float):
        """Moves the rover to (tx, ty) by always turning to face it first."""
        # Validate Y-axis constraint: Goal must be above the starting point
        if ty < self.pose.y:
            print(f"[WARN] Goal ({tx}, {ty}) is below current Y ({self.pose.y}). Violates constraints.")

        dx = tx - self.pose.x
        dy = ty - self.pose.y
        
        # Calculate distance and angle
        distance = math.sqrt(dx**2 + dy**2)
        if distance < 0.1: # Already there
            return

        # Target angle in degrees (-180 to 180)
        target_angle = math.degrees(math.atan2(dy, dx))
        
        # Calculate relative turn
        relative_turn = target_angle - self.pose.heading
        
        # Normalize to [-180, 180] for shortest turn
        while relative_turn > 180: relative_turn -= 360
        while relative_turn < -180: relative_turn += 360

        print(f"Navigating to ({tx}, {ty}): Turn {relative_turn:.1f}°, Move Forward {distance:.1f}")

        # Execute Turn: Face the target
        if relative_turn > 0:
            self.driver.turn_left(relative_turn)
        elif relative_turn < 0:
            self.driver.turn_right(abs(relative_turn))

        # Execute Move: ONLY FORWARD
        self.driver.forward(distance)

        # Update Internal Pose
        self.pose.x = tx
        self.pose.y = ty
        self.pose.heading = target_angle

def calculate_best_path(start_pose: Pose, goals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Finds an efficient visitation order using Nearest Neighbor.
    Optimized by using squared distance for comparisons.
    """
    path = []
    unvisited = list(goals)
    current_x, current_y = start_pose.x, start_pose.y

    while unvisited:
        best_idx = -1
        min_dist_sq = float('inf')

        for i, (gx, gy) in enumerate(unvisited):
            dist_sq = (gx - current_x)**2 + (gy - current_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                best_idx = i
        
        next_goal = unvisited.pop(best_idx)
        path.append(next_goal)
        current_x, current_y = next_goal

    return path

if __name__ == "__main__":
    # 1. Setup
    start = Pose(x=0, y=0, heading=0) # Facing +X
    
    # 2. Define Goals
    test_goals = [(100, 100), (50, 200), (300, 50), (200, 150), (10, 10)]

    # 3. Plan Path
    ordered_path = calculate_best_path(start, test_goals)
    
    # 4. Driver Selection
    driver_name = _parse_driver_arg(sys.argv)
    driver = make_driver(driver_name)

    # 5. Execute Mission
    driver.setup_view(480.0, 230.0, start)
    navigator = Navigator(driver, start)
    driver.draw_points(ordered_path)

    for gx, gy in ordered_path:
        navigator.move_to_goal(gx, gy)

    # 6. Finalization
    if driver_name == "turtle":
        print("Done! Close the window to exit.")
        import turtle
        turtle.done()
    else:
        print(f"Final {navigator.pose}")
