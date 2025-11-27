"""
G1 Robot Controller
A comprehensive control system for the Unitree G1 robot.

Components:
- ASR Listener: Speech recognition
- TTS Speaker: Text-to-speech synthesis
- Camera Reader: Image capture from robot camera
- Thor Communication: Send/receive from Jetson Thor VLM
- Action Dispatcher: Route commands to appropriate handlers
- Action Executor: Execute gestures, movements, and system commands

Usage:
    python -m g1_robot_controller eth0
"""

from .main import G1RobotController

__all__ = ["G1RobotController"]
