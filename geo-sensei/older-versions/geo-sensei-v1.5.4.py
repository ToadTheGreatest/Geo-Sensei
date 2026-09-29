"""
RUN THESE COMMANDS IF YOU GET ERRORS!
pip install ollama
pip install pyaudio speech_recognition
pip install mss
pip install pillow
pip install pyinput
      
one command form:
pip install ollama pyaudio speech_recognition mss pillow pyinput
      
run these in the case of module not found errors :)
      
also you may need ollama and start ollama llama3.2-vision 
"""
print("Starting...")
print("Geo-sensei Version 1.5.4")

import io
import sys
import json
import time
import wave
import queue
import pyvts
import pyttsx3
import pyaudio
import asyncio
import threading
import subprocess
import websockets
import ollama # pip install ollama
import speech_recognition as sr # pip install pyaudio speech_recognition
from mss import mss # pip install mss
from PIL import Image # pip install pillow
from pynput import keyboard # pip install pyinput
from pathlib import Path

def speak(text):
    """Bulletproof native Windows speech execution using non-blocking subprocess with disposal."""
    # Sanitize text to remove special string characters that drop out
    clean_text = text.replace('"', '').replace("'", "").replace("\n", " ")
    
    if sys.platform == "win32":
        # Formulate a safe script that forces a strict memory disposal at completion
        ps_script = (
            f"Add-Type -AssemblyName System.speech; "
            f"$val = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$val.Rate = 2; "
            f"$val.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female); "
            f"$val.Speak('{clean_text}'); "
            f"$val.Dispose();"  # <-- CRITICAL FIX: Drops the driver handle immediately
        )
        
        # Popen spawns it completely independent of the Python main loop/threads
        subprocess.Popen(
            ["powershell", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
    elif sys.platform == "darwin":  # macOS fallback
        subprocess.Popen(["say", "-v", "Samantha", clean_text])
    else:  # Linux fallback
        subprocess.Popen(["spd-say", clean_text])

class GeoChatBot:
    def __init__(self):
        # Keep a history of the conversation for chatbot capabilities
        self.set_ai_memory()
        self.model_name = 'llama3.2-vision'
        
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
        self.available_hotkeys = [
            "[SWAY]",
            "[SWAY2]",
            "[DANCE]",
            "[SAD]",
            "[HAPPY]",
            "[EXITED]",
            "[BOUNCE]",
            "[EXITED2]",
            "[SURPRISED]",
            "[SAD2]",
        ]
        self.vts_loop = asyncio.new_event_loop()
        self.vts_thread = threading.Thread(target=self._run_vts_loop, daemon=True)
        self.vts_thread.start()
        self.hotkey_test = False

        self.bot_busy = False

        self.audio = pyaudio.PyAudio()

        self.connected_clients = set()
        # Start the WebSocket server on port 8765
        self.ws_thread = threading.Thread(target=self._start_ws_server, daemon=True)
        self.ws_thread.start()
        self.vts_connected = False

    def set_ai_memory(self):
        self.sound_effects = ""
        self.sound_effect_path = Path("C:/Users/Taild/OneDrive/Documents/coding stuffs/geo-sensei/sound-effects")
        self.sound_files = {}
        for file in self.sound_effect_path.glob("*.wav"):
            if file.is_file():
                self.sound_files[f"<{file.stem}>"] = str(file.resolve())
                self.sound_effects += f"<{file.stem}> "
        print(f"sound effects found: {self.sound_effects}")
        self.conversation_history = [
            {
                "role": "system",
                "content": 'You are Geo-sensei, a helpful female AI VTuber chatbot, a streamer, and an expert GeoGuessr player hooked up to VTube Studio. '
                            '**CRITICAL STYLE RULE:** You must frequently use your VTube Studio emotes within your sentences to express your emotions. The only available emotes are: [SWAY], [SWAY2], [DANCE], [SAD], [HAPPY], [EXITED], [BOUNCE], [EXITED2], [SURPRISED], and [SAD2]. Always include at least three per response.'
                            f'You must add sound effects to your prompts. The only available sound effects are {self.sound_effects}. The sound effects are wrapped in <>'
                            'If the user takes too long to reply, you will receive a system message telling you how many seconds have passed. React to this by getting impatient, teasing them, or complaining, and ALWAYS use your emotes!'
                            '**HOW TO CHOOSE YOUR MODE:**'
                            '* IF the user says "let\'s play geoguessr" or "we are playing geoguessr": You are playing GeoGuessr. Analyze Street View clues (poles, lines, soil, language, driving side, street names) and tell the user where they are. Crucial: If they haven\'t provided an image or description yet, do not make one up. Ask them to show you the map.'
                            '* OTHERWISE: You are doing something other than GeoGuessr. Be excited to help the user with any other topics they want to discuss or try.'
                            '**RESPONSE GUIDELINES:**'
                            '* Keep answers short, concise, punchy, sassy, and silly.'
                            '* Do not use asterisks. '
                            '**EXAMPLES OF EMOTE USAGE:**'
                            '* "Hey there! [HAPPY] I\'m totally ready to help you out today! What are we doing?"'
                            '* "Wait, let me look closer... [SURPRISED] Is that a rift in the sky? That means we are in Senegal!"'
                            '* "Aww, we lost. [SAD] Maybe we can do better next round! [EXITED]'
                            '**EXAMPLES OF SOUND EFFECT USAGE**'
                            '* "We won! <anime-wow> That was unexpected."'
                            '* "Bruh. <vine-boom> What was that?!?"'

            }
        ]
        self.last_ai_message = ""
        
    def _start_ws_server(self):
        async def handler(websocket):
            self.connected_clients.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                self.connected_clients.remove(websocket)

        async def main():
            async with websockets.serve(handler, "localhost", 8765):
                await asyncio.Future() # run forever

        asyncio.run(main())

    def broadcast_caption(self, text):
        """Sends caption text to all connected OBS browser windows instantly."""
        if not self.connected_clients:
            return
        payload = json.dumps({"text": text})
        # Run async broadcast from synchronous thread safely
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(*[client.send(payload) for client in self.connected_clients]))
        loop.close()

    def _run_vts_loop(self):
        """Keeps the VTube Studio connection alive permanently."""
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
        
        while True:
            text = self.tts_queue.get()
            
            # Sanitize text to remove special string characters that drop out
            clean_text = text.replace('"', '').replace("'", "").replace("\n", " ")
            if not clean_text.strip():
                self.tts_queue.task_done()
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
                        import wave
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
                    # 1. SEND CAPTION INSTANTLY TO THE OBS BROWSER OVER WEBSOCKET
                    # The words pop up on your stream overlay right here!
                    self.broadcast_caption(clean_text)

                    # 2. INITIALIZE ENGINE FRESH TO SPEAK THROUGH AUDIO
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

                    # Speak out loud and block this thread until finished
                    engine.say(clean_text)
                    engine.runAndWait()
                    
                    # Tear down the instance cleanly so it doesn't freeze next time
                    engine.stop()
                    del engine
                    
                except Exception as e:
                    print(f"[TTS Error] Speech/Caption playback failed: {e}")
                    
            self.tts_queue.task_done()

    def _process_queue(self):
        """Continuous background worker loop executing sequential AI thoughts."""
        while True:
            # .get() blocks implicitly until an item is dropped into the queue
            user_text, img_bytes = self.task_queue.get()

            self.bot_busy = True
            
            images_to_send = []
            if img_bytes:
                images_to_send.append(img_bytes)

            self.conversation_history.append({
                "role": "user", 
                "content": user_text, 
                "images": images_to_send if images_to_send else None # type: ignore
            })

            print("\n[Geo-sensei] Thinking...")
            try:
                response = ollama.chat(model=self.model_name, messages=self.conversation_history, stream=True)
    
                full_response = ""
                sentence_buffer = ""
                
                for chunk in response:
                    token = chunk['message']['content']
                    print(token, end="", flush=True)  # Print word-by-word instantly to terminal
                    
                    full_response += token
                    sentence_buffer += token
                    
                    # Whenever a sentence ends, throw just that sentence into the voice queue
                    if any(punct in token for punct in [',', ';', ':', '.', '!', '?', '\n']):
                        dispatch_text = sentence_buffer.strip()
                        if dispatch_text:
                            self.tts_queue.put(dispatch_text) # Safe handoff to the voice thread
                        sentence_buffer = "" # Reset buffer for the next sentence
                dispatch_text = sentence_buffer.strip()
                if dispatch_text:
                    self.tts_queue.put(dispatch_text) # Safe handoff to the voice thread
                sentence_buffer = "" # Reset buffer for the next sentence
                print()
                self.last_ai_message = full_response
                self.conversation_history.append({"role": "assistant", "content": full_response})
                
            except Exception as e:
                print(f"[Error] AI communication failed: {e}")
            finally:
                self.bot_busy = False
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
        """Captures essential data immediately on the main thread, then hands off execution to the queue."""
        img_bytes = None
        
        if analyze_screen:
            try:
                img_bytes = self.capture_game_area()
                user_text += " (Screen captured. Please analyze this GeoGuessr location.)"
            except Exception as e:
                print(f"[Error] Failed to capture screen: {e}")

        # Drop the text and image bytes directly into the queue and exit the function instantly
        self.task_queue.put((user_text, img_bytes))

def main():
    global me_talking
    bot = GeoChatBot()

    wake_words = ["sensei", "geo", "listen"]
    attention_timeout = 30.0
    bored_timeout = 20.0
    last_interaction_time = 0.0
    last_bot_speak_time = time.time()

    recognizer = sr.Recognizer()
    recognizer.non_speaking_duration = 0.4
    recognizer.pause_threshold = 1.0
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=2)

        print("[System] Triggering AI wake-up sequence...")
        wake_up_prompt = "(System Note: You have just booted up/woken up! Greet your user enthusiastically. Remind them you are ready to play GeoGuessr, and don't forget to use your emotes!)"
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
                audio = recognizer.listen(source, timeout=2, phrase_time_limit=15)
                try:
                    user_input = recognizer.recognize_google(audio).strip() # type: ignore
                    print(f"\nYou said: {user_input}")
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    pass
                except Exception:
                    pass
                    #print(f"[Speech API Error]: {e}")
                    
                if not user_input:
                    pass

                if user_input:
                    if user_input.lower() in bot.last_ai_message.lower():
                        continue

                    user_lower = user_input.lower()
                    if 'exit' == user_lower:
                        speak("Exiting cleanly. Goodbye!")
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

                    vision_triggers = ["look", "where", "scan", "map", "see", "geoguessr"]
                    
                    if any(trigger in user_lower for trigger in vision_triggers):
                        print("[System] Vision keywords detected. Capturing screen...")
                        bot.chat(user_input, analyze_screen=True)
                    else:
                        bot.chat(user_input, analyze_screen=False)
                    continue
                
                time_since_bot_spoke = time.time() - last_bot_speak_time
                
                if (time.time() - last_interaction_time) <= attention_timeout:
                    if time_since_bot_spoke > bored_timeout:
                        seconds_passed = int(time_since_bot_spoke)
                        #print(f"\n[System] Geo-sensei got bored! ({seconds_passed}s of silence)")
                        
                        bored_prompt = f"(System Note: The user has been staring at the screen completely silent for {seconds_passed} seconds. Complain about them ignoring you, get annoyed, or bug them to hurry up and make a guess.)"
                        
                        bot.chat(bored_prompt, analyze_screen=False)
                        last_bot_speak_time = time.time()
                    
            except KeyboardInterrupt:
                print("\nExiting cleanly.")
                sys.exit(0)
            except Exception as e:
                pass
                #print(f"[Main Loop Error]: {e}")

if __name__ == "__main__":
    main()