import os
from pathlib import Path

import requests

VOICE_URL = "http://localhost:5010"
VOICE_URL = VOICE_URL.rstrip('/')


def transcribe_audio(audio: str):
    try:
        text = requests.post(url='{}/{}'.format(VOICE_URL, 'stt'), json={'audio': audio})
        text = text.json().get('text')
        print(f"Transcribed text: {text}")
    except requests.exceptions.RequestException:
        text = ''
    return text


def synthesize_text(text: str):
    try:
        audio = requests.post(url='{}/{}'.format(VOICE_URL, 'tts'), json={'text': text})
        audio = audio.json().get('audio')
    except requests.exceptions.RequestException as e:
        print(f"Error in synthesizing audio: {e}")
        audio = None
    return audio