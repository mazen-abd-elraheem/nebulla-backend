"""
Test script to send a message to the running Nebula server,
print the LLM text response, and save the cloned voice audio as a WAV file.
"""

import requests
import base64
from pathlib import Path

SERVER_URL = "http://127.0.0.1:8000/api/v1/conversations/chat"
OUTPUT_WAV = Path("output_chat_voice.wav")

def test_chat():
    payload = {
        "message": "صباح الخير يا نيبولا، عرفني بنفسك باختصار وبلهجة ودودة",
        "personality_id": 1,
        "return_audio": True
    }
    
    print(f"📡 Sending request to: {SERVER_URL} ...")
    try:
        response = requests.post(SERVER_URL, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        print("\n✅ Server Response Received successfully!")
        print("-" * 50)
        print(f"💬 LLM Text Response:\n{data.get('text')}\n")
        print(f"🎭 Voice Sample Used: {data.get('has_voice_sample')}")
        print(f"🔗 Audio URL: {data.get('audio_url')}")
        
        audio_b64 = data.get("audio_base64")
        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
            OUTPUT_WAV.write_bytes(audio_bytes)
            print(f"🔊 Audio saved successfully to: {OUTPUT_WAV.resolve()} ({len(audio_bytes)} bytes)")
            print("▶️ You can play the WAV file now to hear the cloned voice!")
        else:
            print("⚠️ No audio returned. Notice:", data.get("voice_notice"))
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the server. Make sure Uvicorn is running:")
        print("   uvicorn app.main:app --host 127.0.0.1 --port 8000")
    except Exception as e:
        print(f"❌ Error during test: {e}")

if __name__ == "__main__":
    test_chat()

