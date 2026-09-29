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
print("Geo-sensei Version 1.3.2")

import io
import sys
import time
import queue
import pyvts
import asyncio
import threading
import subprocess
import ollama # pip install ollama
import speech_recognition as sr # pip install pyaudio speech_recognition
from mss import mss # pip install mss
from PIL import Image # pip install pillow
from pynput import keyboard # pip install pyinput

me_talking = False

def keydown(key):
    global me_talking
    if key == keyboard.Key.space:
        me_talking = True

def keyup(key):
    global me_talking
    if key == keyboard.Key.space:
        me_talking = False

listener = keyboard.Listener(on_press=keydown,on_release=keyup)
listener.start()

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
        self.conversation_history = [
            {
                "role": "system",
                "content": 'You are Geo-sensei, a helpful AI chatbot, a streamer, and an expert GeoGuessr player hooked up to VTube Studio. '
                            '**CRITICAL STYLE RULE:** You must frequently use your VTube Studio emotes within your sentences to express your emotions. The only available emotes are: [SWAY], [SWAY2], [DANCE], [SAD], [HAPPY], [EXITED], [BOUNCE], [EXITED2], [SURPRISED], and [SAD2]. Always include at least three per response.'
                            '**HOW TO CHOOSE YOUR MODE:**'
                            '* IF the user says "let\'s play geoguessr" or "we are playing geoguessr": You are playing GeoGuessr. Analyze Street View clues (poles, lines, soil, language, driving side, street names) and tell the user where they are. Crucial: If they haven\'t provided an image or description yet, do not make one up. Ask them to show you the map.'
                            '* OTHERWISE: You are doing something other than GeoGuessr. Be excited to help the user with any other topics they want to discuss.'
                            '**RESPONSE GUIDELINES:**'
                            '* Keep answers short, concise, and punchy.'
                            '* Do not use many asterisks. '
                            '**EXAMPLES OF EMOTE USAGE:**'
                            '* "Hey there! [HAPPY] I\'m totally ready to help you out today! What are we doing?"'
                            '* "Wait, let me look closer... [SURPRISED] Is that a rift in the sky? That means we are in Senegal!"'
                            '* "Aww, we lost. [SAD] Maybe we can do better next round! [EXITED]'

            }
        ]
        self.model_name = 'llama3.2-vision'
        self.last_ai_message = ""
        
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
            if self.hotkey_test:
                for hk in self.available_hotkeys:
                    self.trigger_hotkey_sync(hk)
                    print(hk)
                    time.sleep(1)
        except Exception as e:
            print(f"[VTS]: Pairing error {e}")

    async def send_hotkey(self, hotkey_name):
        try:
            await self.vts.request(
                self.vts.vts_request.requestTriggerHotKey(hotkey_name)
            )
        except Exception as e:
            print(f"[VTS Error] Failed to trigger hotkey {hotkey_name}: {e}")

    def trigger_hotkey_sync(self, hotkey_name):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.send_hotkey(hotkey_name), self.loop)

    def _process_tts_queue(self):
        """Dedicated background loop that reads sentences one after another from the queue."""
        while True:
            text = self.tts_queue.get()
            
            # Sanitize text to remove special string characters that drop out
            clean_text = text.replace('"', '').replace("'", "").replace("\n", " ")
            if not clean_text.strip():
                self.tts_queue.task_done()
                continue

            for ht in self.available_hotkeys:
                if ht in clean_text:
                    self.trigger_hotkey_sync(ht)
                    clean_text = clean_text.replace(ht,"")

            try:
                if sys.platform == "win32":
                    ps_script = (
                        f"Add-Type -AssemblyName System.speech; "
                        f"$val = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$val.Rate = 2; "
                        f"$val.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female); "
                        f"$val.Speak('{clean_text}'); "
                        f"$val.Dispose();"
                    )
                    # Safely runs the script and waits for it to finish playing
                    subprocess.run(
                        ["powershell", "-Command", ps_script], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL
                    )
                    
                elif sys.platform == "darwin":  # macOS fallback
                    subprocess.run(["say", "-v", "Samantha", clean_text])
                else:  # Linux fallback
                    subprocess.run(["spd-say", "-w", clean_text])
            except Exception as e:
                print(f"[TTS Error] Speech playback failed: {e}")
            finally:
                self.tts_queue.task_done()

    def _process_queue(self):
        """Continuous background worker loop executing sequential AI thoughts."""
        while True:
            # .get() blocks implicitly until an item is dropped into the queue
            user_text, img_bytes = self.task_queue.get()
            
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
                    if any(punct in token for punct in ['.', '!', '?', '\n']):
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
            width, height = monitor["width"], monitor["height"]
            
            # Crop 15% off the edges to focus on the game and ignore ads/taskbars
            
            bbox = {
                "top": monitor["top"],
                "left": monitor["left"],
                "width": width,
                "height": height
            }
            
            sct_img = sct.grab(bbox)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Save directly to RAM buffer instead of writing to the hard drive
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
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

def transcribe_voice():
    # Initialize the recognizer class
    recognizer = sr.Recognizer()

    # Use the microphone as the audio source
    with sr.Microphone() as source:
        #print("Calibrating for background noise... Please wait.")
        # Adjusts the energy threshold dynamically to filter out background static
        recognizer.adjust_for_ambient_noise(source, duration=1)
        
        print("Talk Now")
        # Captures live audio input from the microphone
        audio = recognizer.listen(source)
        
        #print("Processing audio...")

    try:
        # Use Google Web Speech API to recognize the audio
        text = recognizer.recognize_google(audio) # type: ignore
        print(f"You said: {text}")
        return text

    except sr.UnknownValueError:
        # Fired if the audio was completely unintelligible
        #print("Google Speech Recognition could not understand the audio.")
        return ""
        
    except sr.RequestError as e:
        # Fired if the API request failed (e.g., no internet connection)
        #print(f"Could not request results from Google service; {e}")
        return ""

def main():
    global me_talking
    bot = GeoChatBot()
    speak("Geo-sensei has been woken up! Press space to talk")
    while True:
        try:
            if me_talking:
                user_input = transcribe_voice().strip()
            else:
                continue
            if not user_input:
                continue

            if user_input.lower() in bot.last_ai_message.lower():
                continue

            me_talking = False
                
            if user_input.lower() == 'exit':
                speak("exiting")
                break
            
            if user_input.lower() == 'clear':
                bot.clear_queue()
                continue
                
            if user_input.lower() == 'scan':
                speak("Scanning monitor 1")
                bot.chat("Analyze my current location.", analyze_screen=True)
            else:
                bot.chat(user_input, analyze_screen=False)
                
        except KeyboardInterrupt:
            print("\nExiting cleanly.")
            sys.exit(0)

if __name__ == "__main__":
    main()