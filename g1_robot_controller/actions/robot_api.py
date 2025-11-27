"""
robot_api.py

High-level robot API wrapper used by action handlers.

- Provides simple high level methods like move_forward, turn, stop, execute_gesture.
- These methods are currently stubs that log the requested actions and can be
  replaced with real SDK calls (or be forwarded to a lower-level motor API)

Design:
  - Use this module as the single place to switch between a high-level API and
    a low-level motor API later (e.g., unitree_sdk2py motion APIs).

"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RobotAPI:
    """High-level robot API interface."""

    def move_forward(self, distance: float = 0.5, speed: float = 0.2, cancel_event=None) -> bool:
        """Move forward specified distance (meters)."""
        logger.info(f"[robot_api] move_forward: distance={distance}m, speed={speed}m/s")
        # Simulate movement with cancel support
        if cancel_event is not None:
            elapsed = 0.0
            step = 0.1
            total_time = distance / speed if speed > 0 else 0
            while elapsed < total_time:
                if cancel_event.is_set():
                    logger.info("[robot_api] move_forward cancelled")
                    return False
                time.sleep(step)
                elapsed += step
            return True
        else:
            # No cancel support, block until simulated movement completes
            time.sleep(distance / speed if speed > 0 else 0)
            return True

    def turn(self, angle_deg: float = 90.0, speed: float = 30.0, cancel_event=None) -> bool:
        """Turn in degrees (positive = clockwise)."""
        logger.info(f"[robot_api] turn: angle={angle_deg}deg, speed={speed}deg/s")
        if cancel_event is not None:
            elapsed = 0.0
            step = 0.1
            total_time = abs(angle_deg) / speed if speed > 0 else 0
            while elapsed < total_time:
                if cancel_event.is_set():
                    logger.info("[robot_api] turn cancelled")
                    return False
                time.sleep(step)
                elapsed += step
            return True
        else:
            time.sleep(abs(angle_deg) / speed if speed > 0 else 0)
            return True

    def stop(self) -> bool:
        logger.info("[robot_api] stop command")
        return True

    def execute_gesture(self, gesture_name: str, cancel_event=None) -> bool:
        logger.info(f"[robot_api] execute_gesture: {gesture_name}")
        # Gesture usually quick; still support cancel_event
        if cancel_event is not None:
            if cancel_event.is_set():
                logger.info("[robot_api] gesture cancelled")
                return False
        time.sleep(0.5)
        return True


# Global API instance
_api = RobotAPI()


def get_robot_api() -> RobotAPI:
    return _api

