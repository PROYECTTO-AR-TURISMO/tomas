import pyttsx3, threading, queue, time
import asyncio
import edge_tts
import pygame
import os

# --- CLASE PARA MANEJAR TEXT-TO-SPEECH EN SEGUNDO PLANO ---
class TTSManager:
    def __init__(self):
        self.tts_queue = queue.Queue()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        # Creamos un loop de eventos de asyncio para manejar la biblioteca edge-tts
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def procesar_audio(text):
            try:
                # Usamos la voz 'Gonzalo' con la velocidad normal (rate="+0%")
                voice = "es-CO-GonzaloNeural"
                communicate = edge_tts.Communicate(text, voice, rate="+0%")
                temp_file = "speech_temp.mp3"
                await communicate.save(temp_file)
                
                # Usamos Sound y el Canal 1 para no interrumpir la música de fondo
                if not pygame.mixer.get_init(): pygame.mixer.init()
                voz_audio = pygame.mixer.Sound(temp_file)
                canal = pygame.mixer.Channel(1) 
                canal.play(voz_audio)
                
                while canal.get_busy():
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"  [SISTEMA] Motor Neural no disponible (sin internet?). Activando voz de respaldo local... {e}")
                try:
                    # Fallback a pyttsx3 (SAPI5 en Windows) que es 100% offline
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 155) # Velocidad un poco más natural
                    engine.say(text)
                    engine.runAndWait()
                    # Es vital liberar el motor para evitar que el driver de audio se bloquee al reiniciar
                    del engine
                except Exception as e_off:
                    print(f"  [ERROR CRÍTICO] Fallaron ambos motores de voz: {e_off}")

        while True:
            text = self.tts_queue.get()
            if text is None:
                break
            loop.run_until_complete(procesar_audio(text))

    def decir(self, text):
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
            except queue.Empty:
                break
        # Detenemos la reproducción actual en el Canal 1 (TTS) para evitar solapamiento
        if pygame.mixer.get_init():
            pygame.mixer.Channel(1).stop()
        self.tts_queue.put(text)

class AudioManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.tts = TTSManager()
        pygame.init() # Inicializa todos los módulos de pygame, incluyendo el temporizador (timer)
        self.canal_ambiente = pygame.mixer.Channel(2)

    def iniciar_musica_fondo(self):
        try:
            ruta_audio = os.path.join(self.base_dir, 'assets', 'audio')
            if os.path.exists(ruta_audio):
                archivos = [f for f in os.listdir(ruta_audio) if f.lower().endswith(('.mp3', '.wav', '.ogg'))]
                if archivos:
                    audio_path = os.path.join(ruta_audio, archivos[0])
                    pygame.mixer.music.load(audio_path)
                    pygame.mixer.music.set_volume(0.4)
                    pygame.mixer.music.play(-1)
                    print(f"  [AUDIO] Música de fondo iniciada: {archivos[0]}")
                else:
                    print(f"  [AUDIO] La carpeta {ruta_audio} está vacía. Coloca tu archivo de música aquí.")
        except Exception as e:
            print(f"  [ERROR AUDIO] Al iniciar música de fondo: {e}")

    def iniciar_ambiente(self, sitio_id):
        """Carga y reproduce sonido ambiental específico del sitio."""
        try:
            # Mapeo de sonidos según el sitio
            sonidos = {
                "sitio1": "ronda_ambiente.mp3", # río, aves
                "sitio_2": "catedral_ambiente.mp3" # campanas, eco
            }
            archivo = sonidos.get(sitio_id)
            if not archivo: return

            ruta = os.path.join(self.base_dir, 'assets', 'audio', 'ambience', archivo)
            if os.path.exists(ruta):
                sonido = pygame.mixer.Sound(ruta)
                self.canal_ambiente.play(sonido, loops=-1, fade_ms=2000)
                self.canal_ambiente.set_volume(0.3) # Volumen ambiente suave
                print(f"  [AUDIO] Ambiente iniciado: {archivo}")
        except Exception as e:
            print(f"  [ERROR AUDIO] Ambiente: {e}")

    def detener_ambiente(self):
        self.canal_ambiente.fadeout(1000)