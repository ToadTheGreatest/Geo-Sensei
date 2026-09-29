# V1.0

import speech_recognition as sr
import pyttsx3
import websockets
import asyncio
import threading
import json

recognizer = sr.Recognizer()
recognizer.non_speaking_duration = 0.4
recognizer.pause_threshold = 0.5

doing_be_saying = False

class captions:
    def __init__(self):
        self.connected_clients = set()
        self.ws_thread = threading.Thread(target=self._start_ws_server, daemon=True)
        self.ws_thread.start()

    def _start_ws_server(self):
        async def handler(websocket):
            self.connected_clients.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                self.connected_clients.remove(websocket)

        async def main():
            async with websockets.serve(handler, "localhost", 8766):
                await asyncio.Future() # run forever

        asyncio.run(main())

    def broadcast_caption(self, text):
        if not self.connected_clients:
            return
        payload = json.dumps({"text": text})
        # Run async broadcast from synchronous thread safely
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(*[client.send(payload) for client in self.connected_clients]))
        loop.close()

caption = captions()

with sr.Microphone() as mic:
    recognizer.adjust_for_ambient_noise(mic, duration=2)
    while True:
        try:
            audio = recognizer.listen(mic, timeout=None, phrase_time_limit=15)
            text = recognizer.recognize_google(audio).strip()

            print(f"You said: {text}")
            caption.broadcast_caption(text)

            if doing_be_saying:
                engine = pyttsx3.init()
                voices = engine.getProperty("voices")
                engine.setProperty("rate", 260)
                engine.setProperty("voice", voices[1])
                engine.say(text)
                engine.runAndWait()
        except Exception as e:
            print(f"Error: {e}")
            caption.broadcast_caption("")
        finally:
            print("next:")
