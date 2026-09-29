import io
import json
import time
import wave
import queue
import pyvts
import numpy
import pyttsx3
import pyaudio
import asyncio
import pythoncom
import threading
import websockets
import sounddevice
from mss import mss
from PIL import Image
from faster_whisper import WhisperModel

class GeoClient:
    def __init__(self):
        # --- IMPORTANT ---#
        self.available_hotkeys = [
            "[SWAY]",
            "[SWAY2]",
            "[DANCE]",
            "[SAD]",
            "[HAPPY]",
            "[EXCITED]",
            "[BOUNCE]",
            "[EXCITED2]",
            "[SURPRISED]",
            "[SAD2]",
        ]

        self.canbored = False

        self.needs_screen = False
        
        # Initialize the queue and start the background worker thread
        self.task_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

        self.tts_queue = queue.Queue()
        self.tts_thread = threading.Thread(target=self._process_tts_queue, daemon=True)
        self.tts_thread.start()

        self.plugin_info = {
            "plugin_name": "Geo-sensei",
            "developer": "Ryan Jacob (ToadTheGreatest)",
            "authentication_token_path": "./vts_token.json"  # Saves token here
        }
        self.vts_loop = asyncio.new_event_loop()
        self.vts_thread = threading.Thread(target=self._run_vts_loop, daemon=True)
        self.vts_thread.start()
        self.hotkey_test = False

        self.bot_busy = False

        self.audio = pyaudio.PyAudio()

        self.connected_clients = set()
        self.i_connected_clients = set()
        self.i_thread = threading.Thread(target=self._start_indicator_server, daemon=True)
        self.i_thread.start()
        self.ws_thread = threading.Thread(target=self._start_ws_server, daemon=True)
        self.ws_thread.start()
        self.ws_loop = None
        self.i_loop = None

        self.vts_connected = False

        # WHISPER CONFIG
        self.SR_MODEL = "tiny.en"
        self.SR_SAMP_RATE = 16000
        self.SR_CHANNELS = 1
        self.SR_SEND_2_BOT = 2.5
        self.sr_queue = queue.Queue()
        self.mic_incoming = queue.Queue() # INCOMING !!!!!!!!!!!! AAAAAAAAAAAAAAAAAAAAAAA NOOOOOOOOOOOOOO YAYFDG:JFLKGJ:DLKFJ
        self.say_queue = queue.Queue()
        self.init_sr()

        self.thinking = False

    
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
                    print(f"putting {full_text}")
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

            while time.time() - calibration_start < 0.5:
                try:
                    # Grab mic chunks as fast as they arrive during calibration
                    chunk = self.mic_incoming.get(timeout=0.1)
                    rms = numpy.sqrt(numpy.mean(chunk**2))
                    calibration_rms_values.append(rms)
                except queue.Empty:
                    continue

            # Calculate average noise floor and add a safety buffer (e.g., multiplier or static addition)
            if calibration_rms_values:
                avg_noise_floor = numpy.mean(calibration_rms_values)
                # We multiply by 1.5 or add a small padding so normal background ripples don't trigger speech
                SILENCE_THRESHOLD = max(avg_noise_floor + 0.005, 0.01) 
            else:
                SILENCE_THRESHOLD = 0.01 # Fallback if queue failed

            print(f"Room noise = {SILENCE_THRESHOLD}")
            while True:
                try: # if he fails we dont care
                    chunk = self.mic_incoming.get(timeout = 0.5)
                    if self.bot_busy or not self.tts_queue.empty():
                        a_buff.clear()
                        is_recording = False
                        s_start_time = None
                        continue
                    
                    elif self.thinking:
                        a_buff.clear()
                        is_recording = False
                        s_start_time = None
                        continue

                    a_buff.append(chunk)
                    rms = numpy.sqrt(numpy.mean(chunk**2))

                    if rms > SILENCE_THRESHOLD:
                        if not self.thinking:
                            self.broadcast_state("green")
                        s_start_time = None # hasn't changed yet...
                        is_recording = True
                    else:
                        if not self.thinking:
                            self.broadcast_state("blue")
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
            async with websockets.serve(handler, "localhost", 8765):
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
    
    def _start_indicator_server(self):
        async def handler(websocket):
            self.i_connected_clients.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                self.i_connected_clients.remove(websocket)

        async def main():
            self.i_loop = asyncio.get_running_loop() 
            async with websockets.serve(handler, "localhost", 8767):
                await asyncio.Future() # run forever

        asyncio.run(main())

    def broadcast_state(self, text):
        if not self.i_connected_clients or not self.i_loop:
            return
        payload = json.dumps({"text": text})
        # Safely hand the async job off to the indicator's loop
        asyncio.run_coroutine_threadsafe(
            self._async_send_to_all(self.i_connected_clients, payload), 
            self.i_loop
        )

    def _run_vts_loop(self):
        asyncio.set_event_loop(self.vts_loop)
        self.vts_loop.run_until_complete(self.connect_vts())
        self.vts_loop.run_forever()

    async def connect_vts(self):
        print("connecting to vts...")
        self.vts = pyvts.vts(plugin_info=self.plugin_info)
        try:
            await self.vts.connect()
            await self.vts.request_authenticate_token()
            await self.vts.request_authenticate()
            self.loop = asyncio.get_running_loop()
            print("Connected!")
            self.vts_connected = True
            if self.hotkey_test:
                for hk in self.available_hotkeys:
                    self.trigger_hotkey_sync(hk)
                    print(hk)
                    time.sleep(1)
        except Exception as e:
            print(f"[VTS Error]: Pairing error {e}")

    async def send_hotkey(self, hotkey_name):
        try:
            await self.vts.request(
                self.vts.vts_request.requestTriggerHotKey(hotkey_name)
            )
        except Exception as e:
            pass
            #print(f"[VTS Error] Failed to trigger hotkey {hotkey_name}: {e}")

    def trigger_hotkey_sync(self, hotkey_name):
        if self.vts_connected:
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(self.send_hotkey(hotkey_name), self.loop)

    def _process_tts_queue(self):
        pythoncom.CoInitialize()
        engine = pyttsx3.init()
        engine.setProperty('rate', 220)
        try:
            voices = engine.getProperty('voices')
            for voice in voices: # type: ignore
                if "female" in voice.name.lower() or "zira" in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
        except Exception:
            pass
        
        while True:
            text = self.tts_queue.get()
            self.bot_busy = True
            self.broadcast_state("yellow")
            
            # Sanitize text to remove special string characters that drop out
            clean_text = text.replace("\n", " ").replace("[LOOK]","")
            if not clean_text.strip():
                self.tts_queue.task_done()
                self.bot_busy = False
                continue

            # Process Hotkeys
            for ht in self.available_hotkeys:
                if ht in clean_text:
                    self.trigger_hotkey_sync(ht)
                    clean_text = clean_text.replace(ht, "")
            
            # Process Sound Effects
            for sfx in self.sound_files:
                if sfx in clean_text:
                    try:
                        sfx_file = wave.open(self.sound_files[sfx], "rb")
                        stream = self.audio.open(
                            format=self.audio.get_format_from_width(sfx_file.getsampwidth()),
                            channels=sfx_file.getnchannels(),
                            rate=sfx_file.getframerate(),
                            output=True
                        )
                        chunk_size = 1024
                        data = sfx_file.readframes(chunk_size)
            
                        while len(data) > 0:
                            stream.write(data)
                            data = sfx_file.readframes(chunk_size)
                            
                        stream.stop_stream()
                        stream.close()
                        sfx_file.close()
                    except Exception as e:
                        print(f"[SFX Error] Failed to play sound {sfx}: {e}")
                    
                    clean_text = clean_text.replace(sfx, "")

            # Process Voice Output & Live Captions
            if clean_text.strip():
                try:

                    # Speak out loud and block this thread until finished
                    engine.say(clean_text.replace('"', ''))
                    engine.runAndWait()
                    
                except Exception as e:
                    print(f"[TTS Error] Speech/Caption playback failed: {e}")
            self.bot_busy = False
            self.tts_queue.task_done()

    def _process_queue(self):
        while True:
            # .get() blocks implicitly until an item is dropped into the queue
            user_text, img_bytes = self.task_queue.get()
            
            try:
                pass #send shit
            except Exception as e:
                print(f"[Error] AI communication failed: {e}")
                self.thinking = False
            finally:
                self.task_queue.task_done()

    def clear_queue(self):
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
                self.tts_queue.task_done()
            except queue.Empty:
                break

    def capture_game_area(self):
        print("\n[System] Capturing screen...")
        with mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # 1. Downscale the image to a reasonable size for AI vision (e.g., max 1024px)
            img.thumbnail((1024, 1024))
            
            img_byte_arr = io.BytesIO()
            # 2. Save as JPEG with 75% quality instead of heavy PNG
            img.save(img_byte_arr, format='JPEG', quality=75)
            return img_byte_arr.getvalue()

    def chat(self, user_text, analyze_screen=False):
        img_bytes = None
        
        if analyze_screen:
            try:
                img_bytes = self.capture_game_area()
                user_text += " (Screen captured. Please analyze this GeoGuessr location.)"
            except Exception as e:
                print(f"[Error] Failed to capture screen: {e}")

        # Drop the text and image bytes directly into the queue and exit the function instantly
        self.task_queue.put((user_text, img_bytes))
