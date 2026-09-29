import json
import queue
import ollama
import asyncio
import threading
import websockets
from pathlib import Path

class GeoServer:
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
        
        self.memory_path = "./memory/geo-sensei-memories.json" # Path to memory file
        self.use_memory = True # CONTROLS IF GEO-SENSEI IS ABLE TO RECOLLECT PAST EXPIRIENCES AND SAVE MEMORIES

        # Keep a history of the conversation for chatbot capabilities
        self.set_ai_memory()
        self.model_name = 'qwen3-vl:2b'
        
        # Initialize the queue and start the background worker thread
        self.task_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        self.bot_busy = False

        self.connected_clients = set()

        self.thinking = False

    def set_ai_memory(self):
        self.sound_effects = ""
        self.sound_effect_path = Path("./sound-effects")
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
                            '**LIVE FEED ACCESS:** You have access to the user\'s live screen. If the user asks where they are, or if you want to look at the game at ANY time to make a guess, output the exact tag [LOOK] and you will get an image in the next prompt. '
                            '**LONG TERM MEMORY** You possess a permanent memory of all past streams and interactions. The messages below your system instructions are real historical conversations from your previous sessions with the user. If the user asks you about something from a "past session," "last time," or "earlier," look down at your conversation history to find the answers! Acknowledge your memory happily and use it to call back to old jokes or facts. '
                            '**HOW TO CHOOSE YOUR MODE:** '
                            '* IF the user says "let\'s play geoguessr" or "we are playing geoguessr": You are playing GeoGuessr. Analyze Street View clues (poles, lines, soil, language, driving side, street names) and tell the user where they are. Crucial: If they haven\'t provided an image or description yet, do not make one up. Ask them to show you the map. '
                            '* OTHERWISE: You are doing something other than GeoGuessr. Be excited to help the user with any other topics they want to discuss or try. '
                            '**RESPONSE GUIDELINES:** '
                            '* Keep answers short, concise, punchy, sassy, and silly. '
                            '* Do not use asterisks. '
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
        pass # send caption to connected client to send to html

    def broadcast_state(self, text):
        pass # send state to connected client to send to html

    def send_hotkey(self, hotkey_name):
        pass # Send hotkey trigger to connected client

    def _process_tts_queue(self):
        pass # client side

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
                "images": images_to_send if images_to_send else None
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
                    if 'message' in chunk and 'content' in chunk['message']:
                        token = chunk['message']['content']
                    else:
                        continue
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
                    self.needs_screen = True

            except Exception as e:
                print(f"[Error] AI communication failed: {e}")
                self.thinking = False
            finally:
                self.task_queue.task_done()


    def capture_game_area(self):
        pass # get game area from connected client

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
            file = open("./memory/geo-sensei-memories.json", "r")
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
