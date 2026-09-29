# V1.1

import queue
import threading
import numpy
import sounddevice
import pyttsx3
import websockets
import asyncio
import threading
import json
import time
from faster_whisper import WhisperModel

doing_be_saying = False

class captions:
    def __init__(self):
        self.connected_clients = set()
        self.busy = False
        # WHISPER CONFIG
        self.SR_MODEL = "tiny.en"
        self.SR_SAMP_RATE = 16000
        self.SR_CHANNELS = 1
        self.SR_SEND_2_BOT = 0.5
        self.sr_queue = queue.Queue()
        self.mic_incoming = queue.Queue()
        self.say_queue = queue.Queue()
        self.init_sr()

        self.ws_loop = None
        self.connected_clients = set()
        self.ws_thread = threading.Thread(target=self._start_ws_server, daemon=True)
        self.ws_thread.start()
    
    def init_sr(self):
        threading.Thread(target=self.sr_worker,daemon=True).start()
        threading.Thread(target=self.mic_listener,daemon=True).start()

    def sr_worker(self):
        model = WhisperModel(self.SR_MODEL, device="cpu", compute_type="int8")
        while True:
            #epic loop dun dun duuuuuuuuuuuunnnnnnnnnnnn
            try:
                audio_data = self.sr_queue.get(timeout=1)
                segments, _ = model.transcribe(audio_data, beam_size=5)
                full_text = "".join([segment.text for segment in segments]).strip()
                if full_text:
                    self.say_queue.put(full_text)
            except Exception:
                pass
    
    def do_mic_stuff(self, indata, frames, info_time, status):
        self.mic_incoming.put(indata.copy())

    def mic_listener(self): # the only one who listens to yapping miceal
        a_buff = []
        s_start_time = None
        is_recording = False
        stream = sounddevice.InputStream(samplerate=self.SR_SAMP_RATE, channels=self.SR_CHANNELS, callback=self.do_mic_stuff)
        with stream:
            calibration_start = time.time()
            calibration_rms_values = []

            while time.time() - calibration_start < 2:
                try:
                    chunk = self.mic_incoming.get(timeout=0.1)
                    rms = numpy.sqrt(numpy.mean(chunk**2))
                    calibration_rms_values.append(rms)
                except queue.Empty:
                    continue

            if calibration_rms_values:
                avg_noise_floor = numpy.mean(calibration_rms_values)
                SILENCE_THRESHOLD = max(avg_noise_floor + 0.005, 0.01) 
            else:
                SILENCE_THRESHOLD = 0.01 # Fallback if queue failed

            print(f"Room noise = {SILENCE_THRESHOLD}")
            while True:
                try: # if he fails we dont care
                    chunk = self.mic_incoming.get(timeout = 0.1)
                    if self.busy:
                        a_buff.clear()
                        is_recording = False
                        s_start_time = None
                        continue

                    a_buff.append(chunk)
                    rms = numpy.sqrt(numpy.mean(chunk**2))

                    if rms > SILENCE_THRESHOLD:
                        s_start_time = None # hasn't changed yet...
                        is_recording = True
                    else:
                        if is_recording and s_start_time is None:
                            s_start_time = time.time()
                    
                    if is_recording and s_start_time:
                        if time.time() - s_start_time >= self.SR_SEND_2_BOT:
                            full_audio = numpy.concatenate(a_buff, axis=0).flatten()
                            self.sr_queue.put(full_audio)
                            a_buff.clear()
                            is_recording = False
                            s_start_time = None

                
                except Exception:
                    pass

    async def _async_send_to_all(self, client_set, payload):
        if client_set:
            # return_exceptions=True prevents one disconnected client from breaking others
            await asyncio.gather(
                *[client.send(payload) for client in client_set], 
                return_exceptions=True
            )

    def _start_ws_server(self):
        async def handler(websocket):
            self.connected_clients.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                self.connected_clients.remove(websocket)

        async def main():
            self.ws_loop = asyncio.get_running_loop() 
            async with websockets.serve(handler, "localhost", 8766):
                await asyncio.Future() # run forever

        asyncio.run(main())

    def broadcast_caption(self, text):
        if not self.connected_clients or not self.ws_loop:
            return
        payload = json.dumps({"text": text})
        # Safely hand the async job off to the server's loop
        asyncio.run_coroutine_threadsafe(
            self._async_send_to_all(self.connected_clients, payload), 
            self.ws_loop
        )

caption = captions()

while True:
    try:
        text = caption.say_queue.get(timeout=0.1)
        if text:
            print(f"You said: {text}")
            caption.broadcast_caption(text)

            if doing_be_saying:
                caption.busy = True
                engine = pyttsx3.init()
                voices = engine.getProperty("voices")
                engine.setProperty("rate", 260)
                engine.setProperty("voice", voices[1].id)
                engine.say(text)
                engine.runAndWait()
                del engine
                caption.busy = False
        else:
            pass
    except Exception as e:
        #print(f"Error: {e}")
        #caption.broadcast_caption("")
        pass
    finally:
        #print("next:")
        pass
