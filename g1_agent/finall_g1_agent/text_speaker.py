from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient


class TextSpeaker:
    def __init__(self):
        self.audio = AudioClient()
        self.audio.SetVolume(85)

    def speak(self, text):
        if text.strip():
            self.audio.PlayText(text)