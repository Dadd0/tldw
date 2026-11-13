import os
import base64
import json
import requests
from dotenv import load_dotenv

def main():
    load_dotenv()

    with open("audios/audio.mp3", "rb") as f:
        audio = base64.b64encode(f.read()).decode("utf-8")
        response = requests.post(
          url="https://openrouter.ai/api/v1/audio/transcriptions",
          headers={
            "Authorization": f"Bearer {os.environ.get("OPENROUTER_API_KEY")}",
            "Content-Type": "application/json",
          },
          data=json.dumps({
            "model": f"{os.environ.get("TRANSCRIPTION_MODEL_ID")}",
            "input_audio": {
              "data": audio,
              "format": "mp3"
            }
          })
    )
    result = response.json()
    print(result["text"])

if __name__ == "__main__":
    main()

