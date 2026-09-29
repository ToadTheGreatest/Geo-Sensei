####################################
# By: Ryan Jacob (ToadTheGreatest)
# Started 5/29/2026
####################################

# The code starts here:
print("Starting...")
print("Geo-sensei Version 1.13.2") # Using Qwen3 vision # Has indicator light (lamp) # Integration with the custom-made Geo-Sensei HTML External Chatting System (MORE WEBSOCKET STUFF AAAA)

import io
import sys
import json
import time
import wave
import queue
import pyvts
import numpy
import ollama
import pyttsx3
import pyaudio
import asyncio
import pythoncom
import threading
import websockets
import sounddevice
from mss import mss
from PIL import Image
from pathlib import Path
from faster_whisper import WhisperModel

class GeoChatBot:
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

        self.memory_path = "C:/Users/Taild/OneDrive/Documents/coding stuffs/geo-sensei/memory/geo-sensei-memories.json" # Path to memory file
        self.use_memory = True # CONTROLS IF GEO-SENSEI IS ABLE TO RECOLLECT PAST EXPIRIENCES AND SAVE MEMORIES

        # Keep a history of the conversation for chatbot capabilities
        self.set_ai_memory()
        self.model_name = 'qwen3-vl:2b'
        
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
            "authentication_token_path": "C:/Users/Taild/OneDrive/Documents/coding stuffs/geo-sensei/vts_token.json"  # Saves token here
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

        self.extc_thread = threading.Thread(target=self.run_extc_server, daemon=True)
        self.extc_thread.start()

        
    
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

    def set_ai_memory(self):
        self.sound_effects = ""
        self.sound_effect_path = Path("C:/Users/Taild/OneDrive/Documents/coding stuffs/geo-sensei/sound-effects")
        self.sound_files = {}
        for file in self.sound_effect_path.glob("*.wav"):
            if file.is_file():
                self.sound_files[f"<{file.stem}>"] = str(file.resolve())
                self.sound_effects += f"<{file.stem}> "
        print(f"sound effects found: {self.sound_effects}")
        self.available_hotkeys_text = ""
        for htk in self.available_hotkeys:
            self.available_hotkeys_text += f"{htk} "
        print(f"available hotkeys: {self.available_hotkeys_text}")
        self.conversation_history = self.readMemory()
        self.conversation_history.insert(0, 
            {
                "role": "system",
                "content": 'You are Geo-sensei, a helpful female AI VTuber chatbot, and an expert GeoGuessr player hooked up to VTube Studio. ' # ADD a streamer when streaming
                            f'**CRITICAL STYLE RULE:** You must frequently use your VTube Studio emotes within your sentences to express your emotions. The only available emotes are: {self.available_hotkeys_text}. Always include at least three per response. **DO NOT PUT MULTIPLE IN A ROW** '
                            f'You must add sound effects to your prompts. The only available sound effects are {self.sound_effects}. The sound effects are wrapped in <> '
                            'If the user takes too long to reply, you will receive a system message telling you how many seconds have passed. React to this by getting impatient, teasing them, or complaining, and ALWAYS use your emotes! '
                            '**KEEP INTERNAL REASONING TO A MINIMUM** '
                            '**LIVE FEED ACCESS:** You have access to the user\'s live screen. If the user asks where they are, or if you want to look at the game at ANY time to make a guess, output the exact tag [LOOK] . '
                            '**LONG TERM MEMORY** You possess a permanent memory of all past streams and interactions. The messages below your system instructions are real historical conversations from your previous sessions with the user. If the user asks you about something from a "past session," "last time," or "earlier," look down at your conversation history to find the answers! Acknowledge your memory happily and use it to call back to old jokes or facts. '
                            '**HOW TO CHOOSE YOUR MODE:** '
                            '* IF the user says "let\'s play geoguessr" or "we are playing geoguessr": You are playing GeoGuessr. Analyze Street View clues (poles, lines, soil, language, driving side, street names) and tell the user where they are. Crucial: If they haven\'t provided an image or description yet, do not make one up. Ask them to show you the map. '
                            '* OTHERWISE: You are doing something other than GeoGuessr. Be excited to help the user with any other topics they want to discuss or try. '
                            '**RESPONSE GUIDELINES:** '
                            '* Keep answers short, concise, punchy, sassy, and silly. '
                            '* Do not use asterisks. '
                            '* INSTEAD OF EMOJIS (example: 😊 or 👍), use text based emoticons (example: ^u^ or :D). '
                            '**EXAMPLES OF EMOTE USAGE:** '
                            '* "Hey there! [HAPPY] I\'m totally ready to help you out today! What are we doing?" '
                            '* "Wait, let me look closer... [SURPRISED] Is that a rift in the sky? That means we are in Senegal!" '
                            '* "Aww, we lost. [SAD] Maybe we can do better next round! [EXCITED] '
                            '**EXAMPLES OF SOUND EFFECT USAGE** '
                            '* "We won! <anime-wow> That was unexpected." '
                            '* "Bruh. <vine-boom> What was that?!?" '

            }
        )
        self.conversation_history.append({
            "role": "system",
            "content": "**THIS IS THE START OF THE LATEST APP SESSION!**"
        })
        self.last_ai_message = ""

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
            
            images_to_send = []
            if img_bytes:
                images_to_send.append(img_bytes)

            self.conversation_history.append({
                "role": "user", 
                "content": user_text, 
                # "images": images_to_send if images_to_send else None
            })
            self.writeMemory({
                "role": "user", 
                "content": user_text, 
            })

            print("\n[Geo-sensei] Thinking...")
            try:
                self.broadcast_state("yellow")
                self.thinking = True
                response = ollama.chat(model=self.model_name, messages=self.conversation_history, stream=True)
    
                full_response = ""
                sentence_buffer = ""
                
                for chunk in response:
                    token = chunk['message']['content']
                    print(token, end="", flush=True)  # Print word-by-word instantly to terminal
                    
                    full_response += token
                    sentence_buffer += token
                    self.broadcast_caption(full_response)
                    
                    # Whenever a sentence ends, throw just that sentence into the voice queue
                    if any(punct in token for punct in [',', ';', ':', '.', '!', '?', '\n']):
                        dispatch_text = sentence_buffer.strip()
                        if dispatch_text:
                            self.tts_queue.put(dispatch_text) # Safe handoff to the voice thread
                        sentence_buffer = "" # Reset buffer for the next sentence
                self.thinking = False
                dispatch_text = sentence_buffer.strip()
                if dispatch_text:
                    self.tts_queue.put(dispatch_text) # Safe handoff to the voice thread
                sentence_buffer = "" # Reset buffer for the next sentence
                print()
                self.last_ai_message = full_response
                self.conversation_history.append({"role": "assistant", "content": full_response})
                self.writeMemory({"role": "assistant", "content": full_response})
                
                if "[LOOK]" in full_response:
                    print("Geo-sensei want a peek at your screen!")
                    self.chat("(System Note: Here is the live screen feed you requested.)", analyze_screen=True)

            except Exception as e:
                print(f"[Error] AI communication failed: {e}")
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

    def readMemory(self):
        if self.use_memory:
            file = open("C:/Users/Taild/OneDrive/Documents/coding stuffs/geo-sensei/memory/geo-sensei-memories.json", "r")
            mem = json.load(file)
            file.close()
        else:
            mem = []
        return mem
    
    def writeMemory(self, data):
        if self.use_memory:
            with open(self.memory_path, "r") as file:
                mem = json.load(file)
            
            mem.append(data)

            with open(self.memory_path, "w") as file:
                json.dump(mem, file, indent=2)
    
    async def handle_extc_client(self, websocket):
        print("External Chatting System has connected!")
        try:
            async for message in websocket:
                print(f"[WEBSOCKETS] Received: {message}")
                self.say_queue.put(message)
        except websockets.exceptions.ConnectionClosed:
            print("External Chatting System has Disconnected!")
        except Exception as e:
            print(f"Error: {e}")

    async def start_external_chat_server(self):
        # This hosts the server on port 8768
        async with websockets.serve(self.handle_extc_client, "localhost", 8768):
            print("External Chatting System server running on ws://localhost:8768")
            await asyncio.Future()  # Keeps the server running forever
    
    def run_extc_server(self):
        asyncio.run(self.start_external_chat_server())

def main():
    global me_talking
    bot = GeoChatBot()

    wake_words = ["sensei", "geo", "listen"]
    attention_timeout = 30.0
    bored_timeout = 60.0
    last_interaction_time = 0.0
    last_bot_speak_time = time.time()

    time.sleep(5) # wait for processes
    print("done waiting for proceses like internet connectivity and vts")

    bot.tts_queue.put("Geo-sensei is ready to roll!")
    wake_up_prompt = "(System Note: You have just booted up/woken up! Greet your user enthusiastically. Remind them you are ready for anything, and don't forget to use your emotes!)"
    bot.chat(wake_up_prompt, analyze_screen=False)    

    # Initialize the timers immediately so she doesn't instantly get bored
    last_bot_speak_time = time.time()
    while True:
        try:
            user_input = ""
            if bot.bot_busy:
                last_interaction_time = time.time()
                last_bot_speak_time = time.time()
                time.sleep(0.5)
                continue
            
            try:
                user_input = bot.say_queue.get(timeout=0.5)
            except Exception:
                pass
                
            if not user_input:
                pass

            if user_input:
                print(f"[YOU]: {user_input}")
                if user_input.lower() in bot.last_ai_message.lower():
                    continue

                user_lower = user_input.lower()
                if 'exit' == user_lower:
                    break
                if 'clear' == user_lower:
                    bot.set_ai_memory()
                    continue

                is_mentioned = any(word in user_lower for word in wake_words)
                
                if is_mentioned:
                    last_interaction_time = time.time()
                    #print(f"\n[Woke Up!] You said: {user_input}")
                elif (time.time() - last_interaction_time) > attention_timeout:
                    #print(f"\n[Ignored Chatter]: {user_input}")
                    continue
                else:
                    last_interaction_time = time.time()
                    #print(f"\n[Active Conversation] You said: {user_input}")

                bot.chat(user_input, analyze_screen=False)
            
            time_since_bot_spoke = time.time() - last_bot_speak_time
            
            if (time.time() - last_interaction_time) <= attention_timeout:
                if time_since_bot_spoke > bored_timeout:
                    seconds_passed = int(time_since_bot_spoke)
                    #print(f"\n[System] Geo-sensei got bored! ({seconds_passed}s of silence)")
                    
                    bored_prompt = f"(System Note: The user has been completely silent for {seconds_passed} seconds. Complain about them ignoring you, get annoyed, or bug them.)"
                    
                    bot.chat(bored_prompt, analyze_screen=False)
                    last_bot_speak_time = time.time()
                
        except KeyboardInterrupt:
            print("\nExiting cleanly.")
            sys.exit(0)
        except Exception as e:
            #pass
            print(f"[Main Loop Error]: {e}")

if __name__ == "__main__":
    main()
