"""
Speech package for G1 Robot Controller.
Provides text-to-speech functionality.
"""

from .speaker import Speaker, get_speaker, speak

__all__ = ["Speaker", "get_speaker", "speak"]
