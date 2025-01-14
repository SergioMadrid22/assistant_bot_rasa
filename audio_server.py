import os
import base64
import tempfile
from flask import Flask, request, jsonify
import whisper
from flask_cors import CORS
#from melo.api import TTS
from gtts import gTTS


# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Allow CORS for testing and cross-origin requests

# Load Whisper model
WHISPER_MODEL = "small"  # Choose 'tiny', 'base', 'small', 'medium', or 'large'
whisper_model = whisper.load_model(WHISPER_MODEL, 'cuda')

# Load MeloTTS model
#tts_model = TTS(language="ES", device="cuda")
#speaker_ids = tts_model.hps.data.spk2id


@app.route('/stt', methods=['POST'])
def stt():
    """
    Speech-to-Text endpoint using Whisper.
    Accepts a base64-encoded audio file and returns the transcribed text.
    """
    try:
        # Get the JSON payload
        data = request.json
        if not data or 'audio' not in data:
            return jsonify({"error": "Missing 'audio' field in the request"}), 400

        # Decode base64-encoded audio
        audio_base64 = data['audio']
        audio_bytes = base64.b64decode(audio_base64)

        # Save audio to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio_file:
            temp_audio_file.write(audio_bytes)
            temp_audio_path = temp_audio_file.name

        # Transcribe audio using Whisper
        result = whisper_model.transcribe(temp_audio_path, language="es", verbose=True)
        transcription = result.get("text", "").strip()
        print(f"Transcription: {transcription}")
        # Clean up the temporary file
        os.remove(temp_audio_path)

        # Return the transcription
        return jsonify({"text": transcription})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

'''
@app.route('/tts', methods=['POST'])
def tts():
    """
    Text-to-Speech endpoint using MeloTTS.
    Accepts text and returns a base64-encoded audio file.
    """
    try:
        # Get the JSON payload
        data = request.json
        if not data or 'text' not in data:
            return jsonify({"error": "Missing 'text' field in the request"}), 400

        # Get the text to synthesize
        text = data['text']
        print(f"Text to synthesize: {text}")
        if not text.strip():
            return jsonify({"error": "Empty text provided"}), 400

        # Synthesize audio using MeloTTS
'''     


@app.route('/tts', methods=['POST'])
def tts():
    """
    Text-to-Speech endpoint using Whisper.
    Accepts text and returns a base64-encoded audio file.
    """
    try:
        # Get the JSON payload
        data = request.json
        if not data or 'text' not in data:
            return jsonify({"error": "Missing 'text' field in the request"}), 400

        # Get the text to synthesize
        text = data['text']
        print(f"Text to synthesize: {text}")
        if not text.strip():
            return jsonify({"error": "Empty text provided"}), 400
        # Generate audio using gTTS
        tts = gTTS(text=text, lang='es')
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio_file:
            tts.save(temp_audio_file.name)
            temp_audio_path = temp_audio_file.name
        
        tts.save("/home/sergio/Desktop/audio.mp3")
        
        # Encode the audio file as base64
        with open(temp_audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Clean up the temporary file
        os.remove(temp_audio_path)

        # Return the base64-encoded audio
        return jsonify({"audio": audio_base64})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint.
    """
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    # Get port and host from environment variables (useful for deployment)
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5010))

    # Run the Flask app
    app.run(host=host, port=port, debug=True)
