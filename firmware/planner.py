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
        if ty < self.pose.y:
            print(f"[WARN] Goal ({tx}, {ty}) is below current Y ({self.pose.y}). Violates constraints.")

        dx = tx - self.pose.x
        dy = ty - self.pose.y

        distance = math.sqrt(dx**2 + dy**2)
        if distance < 0.1:
            return

        target_angle = math.degrees(math.atan2(dy, dx))

        relative_turn = target_angle - self.pose.heading
        while relative_turn > 180: relative_turn -= 360
        while relative_turn < -180: relative_turn += 360

        print(f"Navigating to ({tx}, {ty}): Turn {relative_turn:.1f}°, Move Forward {distance:.1f}")

        if relative_turn > 0:
            self.driver.turn_left(relative_turn)
        elif relative_turn < 0:
            self.driver.turn_right(abs(relative_turn))

        self.driver.forward(distance)

        self.pose.x = tx
        self.pose.y = ty
        self.pose.heading = target_angle

    def move_to_avoiding(self, tx: float, ty: float,
                         obstacles: List[Tuple[float, float]]):
        """Move to (tx,ty), inserting waypoints to steer around obstacles."""
        danger_sq = DANGER_RADIUS_CM ** 2
        clearance = DANGER_RADIUS_CM + 5.0

        sx, sy = self.pose.x, self.pose.y
        dx, dy = tx - sx, ty - sy
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.1:
            return

        ux, uy = dx / length, dy / length
        perp_x, perp_y = -uy, ux

        blocked = []
        for ox, oy in obstacles:
            if (ox - tx) ** 2 + (oy - ty) ** 2 < 1.0:
                continue
            if (ox - sx) ** 2 + (oy - sy) ** 2 < 1.0:
                continue
            if _point_seg_dist_sq(ox, oy, sx, sy, tx, ty) < danger_sq:
                t = (ox - sx) * ux + (oy - sy) * uy
                side = (ox - sx) * perp_x + (oy - sy) * perp_y
                blocked.append((t, ox, oy, side))

        if not blocked:
            self.move_to_goal(tx, ty)
            return

        # Detour to the side with fewer obstacles
        pos_count = sum(1 for _, _, _, s in blocked if s >= 0)
        detour_sign = -1.0 if pos_count >= len(blocked) - pos_count else 1.0

        waypoints = []
        for t, ox, oy, _side in blocked:
            wp_x = ox + detour_sign * perp_x * clearance
            wp_y = oy + detour_sign * perp_y * clearance
            waypoints.append((t, wp_x, wp_y))

        waypoints.sort()
        print(f"[nav] avoiding {len(blocked)} obstacle(s), "
              f"{len(waypoints)} waypoint(s)")

        for _, wx, wy in waypoints:
            self.move_to_goal(wx, wy)
        self.move_to_goal(tx, ty)

DANGER_RADIUS_CM = 18.0
OBSTRUCTION_PENALTY = 2.5


def _point_seg_dist_sq(px, py, ax, ay, bx, by) -> float:
    """Squared distance from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-9:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return (px - proj_x) ** 2 + (py - proj_y) ** 2


def calculate_best_path(start_pose: Pose, goals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Finds an efficient visitation order using Nearest Neighbor.
    Penalizes paths that pass too close to other unvisited resources.
    """
    path = []
    unvisited = list(goals)
    current_x, current_y = start_pose.x, start_pose.y
    danger_sq = DANGER_RADIUS_CM ** 2

    while unvisited:
        best_idx = -1
        min_cost = float('inf')

        for i, (gx, gy) in enumerate(unvisited):
            dist_sq = (gx - current_x)**2 + (gy - current_y)**2

            obstructions = 0
            for j, (ox, oy) in enumerate(unvisited):
                if j == i:
                    continue
                if _point_seg_dist_sq(ox, oy, current_x, current_y, gx, gy) < danger_sq:
                    obstructions += 1

            cost = dist_sq * (OBSTRUCTION_PENALTY ** obstructions)
            if cost < min_cost:
                min_cost = cost
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
