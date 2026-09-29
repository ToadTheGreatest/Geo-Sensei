print("""
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
""")
import io
import sys
import queue
import threading
import subprocess
import ollama # pip install ollama
from mss import mss # pip install mss
from PIL import Image # pip install pillow

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
                "content": "You are a helpful AI chatbot and a streamer and an expert GeoGuessr player. Your name is Geo-sensei. You are hooked up to a program that allows you to play GeoGuessr."
                           "**HOW TO CHOOSE YOUR MODE:**"
                           "* **IF the user says 'let's play geoguessr', or 'we are playing geoguessr'** You are playing GeoGuessr. Analyze the Street View clues (poles, lines, soil, language, driving side, street names) and tell the user where they are. Crucial: If they say they are playing but haven't provided an image or description yet, do not make one up. Ask them to show you the map."
                           "* **OTHERWISE:** You are doing something other than GeoGuessr. You are excited to take on things and help the user with any other topics they want to discuss."
                           "Keep your answers short and concise. Do not use many asterisks."

            }
        ]
        self.model_name = 'llama3.2-vision'
        self.last_ai_message = ""

        self.tts_queue = queue.Queue()
        self.tts_thread = threading.Thread(target=self._process_tts_queue, daemon=True)
        self.tts_thread.start()

    def _process_tts_queue(self):
        """Dedicated background loop that reads sentences one after another from the queue."""
        while True:
            text = self.tts_queue.get()
            
            # Sanitize text to remove special string characters that drop out
            clean_text = text.replace('"', '').replace("'", "").replace("\n", " ")
            if not clean_text.strip():
                self.tts_queue.task_done()
                continue

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
                if any(punct in token for punct in ['.', '!', '?', '\n', ","]):
                    dispatch_text = sentence_buffer.strip()
                    if dispatch_text:
                        self.tts_queue.put(dispatch_text) # Safe handoff to the voice thread
                    sentence_buffer = "" # Reset buffer for the next sentence
            
            print()
            self.last_ai_message = full_response
            self.conversation_history.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            print(f"[Error] AI communication failed: {e}")

def main():
    bot = GeoChatBot()
    speak("Geo-sensei has been woken up!")
    while True:
        try:
            user_input = str(input("What do you want to say to Geo-Sensei\n>>>"))
            if not user_input:
                continue
                
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