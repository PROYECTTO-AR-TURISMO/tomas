import cv2
import numpy as np
import os
from PIL import Image, ImageSequence
import pyttsx3
import threading
import queue
import pytesseract
import pygame

# Configuraciones de OCR para Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ['TESSDATA_PREFIX'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tessdata')

# --- CLASE PARA MANEJAR TEXT-TO-SPEECH EN SEGUNDO PLANO ---
class TTSManager:
    def __init__(self):
        self.tts_queue = queue.Queue()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while True:
            text = self.tts_queue.get()
            if text is None:
                break
            try:
                # Inicializar el motor por cada frase ayuda a evitar congelamientos en Windows
                engine = pyttsx3.init()
                
                # Ajustar a voz masculina y velocidad más amigable para un recorrido
                try:
                    engine.setProperty('rate', 160)
                    voz_masculina = r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\MSTTS_V110_esES_PabloM'
                    engine.setProperty('voice', voz_masculina)
                except:
                    pass
                
                engine.say(text)
                engine.runAndWait()
                del engine
            except Exception as e:
                print(f"  [ERROR TTS] {e}")

    def decir(self, text):
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
            except queue.Empty:
                break
        self.tts_queue.put(text)


# --- CLASE PARA MANEJAR ANIMACIONES GIF ---
class GifHandler:
    """Extrae y gestiona los frames de archivos GIF para OpenCV."""
    def __init__(self, filepath):
        self.frames = []
        self.current_frame = 0
        self.load_gif(filepath)

    def load_gif(self, filepath):
        if not os.path.exists(filepath):
            return
        try:
            pil_img = Image.open(filepath)
            for frame in ImageSequence.Iterator(pil_img):
                # Convertimos a RGBA (Red, Green, Blue, Alpha)
                frame_rgba = frame.convert('RGBA')
                opencv_frame = cv2.cvtColor(np.array(frame_rgba), cv2.COLOR_RGBA2BGRA)
                
                # --- MEJORA: TRATAMIENTO DE FONDO NEGRO SI NO HAY ALFA ---
                # Si el GIF no tiene canal alfa real, convertimos el negro puro en transparente
                if not self.tiene_transparencia_real(opencv_frame):
                    # Crear una máscara donde el negro (0,0,0) sea transparente
                    gray = cv2.cvtColor(opencv_frame, cv2.COLOR_BGRA2GRAY)
                    _, alpha_mask = cv2.threshold(gray, 5, 255, cv2.THRESH_BINARY)
                    opencv_frame[:, :, 3] = alpha_mask
                
                self.frames.append(opencv_frame)
            if len(self.frames) > 0:
                print(f"  [OK] GIF cargado: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"  [ERROR] Al cargar GIF {filepath}: {e}")

    def tiene_transparencia_real(self, frame):
        # Verifica si el canal alfa tiene variaciones (si todo es 255, no hay transparencia)
        return not np.all(frame[:, :, 3] == 255)

    def get_frame(self):
        if not self.frames: return None
        frame = self.frames[self.current_frame]
        
        # En lugar de repetirse en bucle, se queda quieto en el último fotograma
        if self.current_frame < len(self.frames) - 1:
            self.current_frame += 1
            
        return frame

# --- FUNCIÓN DE RENDERIZADO CON CANAL ALFA ---
def render_alfa(fondo, img, x_porcentaje, y_porcentaje, escala):
    if img is None: return fondo
    try:
        h_f, w_f = fondo.shape[:2]
        img_res = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
        h, w, c = img_res.shape
        
        x = int(w_f * x_porcentaje)
        y = int(h_f * y_porcentaje)
        
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_f, x + w), min(h_f, y + h)
        
        if x1 >= x2 or y1 >= y2: return fondo
        
        img_rec = img_res[y1-y:y2-y, x1-x:x2-x]
        region_fondo = fondo[y1:y2, x1:x2]
        
        # Mezcla basada en el canal Alfa
        alpha = img_rec[:, :, 3] / 255.0
        for canal in range(3):
            region_fondo[:, :, canal] = (alpha * img_rec[:, :, canal] + 
                                        (1.0 - alpha) * region_fondo[:, :, canal])
            
        return fondo
    except:
        return fondo

# --- CLASE PRINCIPAL DEL VISOR AR ---
class VisorTurismoAR:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"\n[SISTEMA] Ruta base: {self.base_dir}")
        
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.detector = cv2.QRCodeDetector()
        
        self.guia_activo = False
        self.paso = 1
        self.max_pasos = 6
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None}
        
        # Cargar botones de interfaz
        self.btn_sig = self._buscar_archivo_ui('next.png')
        self.btn_salt = self._buscar_archivo_ui('skip.png')
        # Igualar el tamaño del botón 'saltar' al botón 'siguiente' para que se vean del mismo tamaño
        if self.btn_sig is not None and self.btn_salt is not None:
            self.btn_salt = cv2.resize(self.btn_salt, (self.btn_sig.shape[1], self.btn_sig.shape[0]), interpolation=cv2.INTER_AREA)

        # Iniciamos el motor de síntesis de voz en segundo plano
        self.tts = TTSManager()
        
        # Iniciamos la ambientación musical
        self.iniciar_musica_fondo()

    def iniciar_musica_fondo(self):
        try:
            pygame.mixer.init()
            ruta_audio = os.path.join(self.base_dir, 'assets', 'audio')
            if os.path.exists(ruta_audio):
                # Busca cualquier formato compatible
                archivos = [f for f in os.listdir(ruta_audio) if f.lower().endswith(('.mp3', '.wav', '.ogg'))]
                if archivos:
                    # Toma el primer archivo que encuentre
                    audio_path = os.path.join(ruta_audio, archivos[0])
                    pygame.mixer.music.load(audio_path)
                    pygame.mixer.music.set_volume(0.2) # Volumen bajito para que no tape la voz principal
                    pygame.mixer.music.play(-1) # -1 significa reproducir en bucle (loop)
                    print(f"  [AUDIO] Música de fondo iniciada: {archivos[0]}")
                else:
                    print(f"  [AUDIO] La carpeta {ruta_audio} está vacía. Coloca tu archivo de música aquí.")
        except Exception as e:
            print(f"  [ERROR AUDIO] Al iniciar música de fondo: {e}")

    def _buscar_archivo_ui(self, nombre):
        rutas = [os.path.join(self.base_dir, 'assets', 'ui', nombre),
                 os.path.join(self.base_dir, 'ui', nombre),
                 os.path.join(self.base_dir, nombre)]
        for r in rutas:
            if os.path.exists(r):
                return cv2.imread(r, cv2.IMREAD_UNCHANGED)
        return None

    def cargar_activos_sitio(self, texto_qr):
        sitio_id = texto_qr.strip().lower()
        path_sitio = os.path.join(self.base_dir, 'assets', 'sitios', sitio_id)
        
        if not os.path.exists(path_sitio):
            print(f"  [ERROR] No existe la carpeta: {path_sitio}")
            return False
        
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None, 'textos': {}}
        archivos = os.listdir(path_sitio)
        
        for i in range(1, self.max_pasos + 1):
            for f in archivos:
                f_low = f.lower()
                if f_low == f"avatar_{i}.gif":
                    self.activos['avatars'][i] = GifHandler(os.path.join(path_sitio, f))
                if f_low == f"burbuja_{i}.gif":
                    self.activos['burbujas'][i] = GifHandler(os.path.join(path_sitio, f))
        
        if 'historica.png' in [f.lower() for f in archivos]:
            self.activos['foto_h'] = cv2.imread(os.path.join(path_sitio, 'historica.png'), cv2.IMREAD_UNCHANGED)
            
        # Cargar textos desde textos.txt (cada linea corresponde a un paso)
        path_textos = os.path.join(path_sitio, 'textos.txt')
        if os.path.exists(path_textos):
            try:
                with open(path_textos, 'r', encoding='utf-8') as f:
                    lineas = [l.strip() for l in f.readlines() if l.strip()]
                    for i, linea in enumerate(lineas):
                        self.activos['textos'][i+1] = linea
            except Exception as e:
                print(f"  [ERROR] Al cargar textos.txt: {e}")
                
        return True

    def reproducir_texto_paso(self):
        # Intentamos obtener el texto para el paso actual
        texto = self.activos['textos'].get(self.paso, "")
        
        # Si no se encontró en textos.txt, hacemos OCR sobre el último frame del GIF de la burbuja
        if not texto and self.paso in self.activos.get('burbujas', {}):
            print(f"  [OCR] Leyendo burbuja {self.paso}...")
            try:
                burbuja = self.activos['burbujas'][self.paso]
                if burbuja and burbuja.frames:
                    # El último frame suele ser el que tiene todo el texto completo
                    frame = burbuja.frames[-1]
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
                    # Ampliamos la imagen para mejorar la precisión del lector
                    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                    texto_ocr = pytesseract.image_to_string(gray, lang='spa').strip()
                    texto = " ".join(texto_ocr.split())
                    self.activos['textos'][self.paso] = texto # Guardar en caché
            except Exception as e:
                print(f"  [ERROR OCR] {e}")

        if not texto:
            texto = f"Paso {self.paso}"
            
        print(f"  [TTS] Reproduciendo paso {self.paso}: {texto[:30]}...")
        self.tts.decir(texto)

    def mouse_callback(self, event, x, y, flags, param):
        h_f, w_f = param
        if event == cv2.EVENT_LBUTTONDOWN and self.guia_activo:
            if x > w_f * 0.7 and y > h_f * 0.75:
                if self.paso < self.max_pasos:
                    self.paso += 1
                    self.reproducir_texto_paso()
                else:
                    self.guia_activo = False # Salir si se presiona siguiente en el último paso
            elif x < w_f * 0.3 and y > h_f * 0.75:
                self.paso = self.max_pasos # Llevar directamente al último paso
                self.reproducir_texto_paso()

    def run(self):
        cv2.namedWindow("VISOR_TURISMO_AR")
        while True:
            ret, frame = self.cap.read()
            if not ret: break
            frame = cv2.flip(frame, 1)
            h_f, w_f, _ = frame.shape
            cv2.setMouseCallback("VISOR_TURISMO_AR", self.mouse_callback, param=(h_f, w_f))

            if not self.guia_activo:
                cv2.rectangle(frame, (int(w_f*0.25), int(h_f*0.25)), (int(w_f*0.75), int(h_f*0.75)), (0, 255, 0), 2)
                cv2.putText(frame, "ESCANEE QR", (int(w_f*0.4), int(h_f*0.2)), 0, 0.7, (0, 255, 0), 2)
                data, _, _ = self.detector.detectAndDecode(frame)
                if data:
                    if self.cargar_activos_sitio(data):
                        self.guia_activo, self.paso = True, 1
                        self.reproducir_texto_paso()
            else:
                av = self.activos['avatars'].get(self.paso)
                # Avatar a la izquierda (x_porcentaje = 0.40), proporcional (escala = 0.7)
                if av: frame = render_alfa(frame, av.get_frame(), 0.40, 0.35, 0.7)
                bu = self.activos['burbujas'].get(self.paso)
                # Burbuja a la derecha del avatar (x_porcentaje = 0.60), proporcional (escala = 0.7)
                if bu: frame = render_alfa(frame, bu.get_frame(), 0.60, 0.15, 0.7)
                if self.paso == self.max_pasos and self.activos['foto_h'] is not None:
                    # Mover la foto histórica para no tapar el avatar
                    frame = render_alfa(frame, self.activos['foto_h'], 0.10, 0.10, 0.3)

                if self.btn_sig is not None: frame = render_alfa(frame, self.btn_sig, 0.75, 0.8, 0.18)
                if self.btn_salt is not None: frame = render_alfa(frame, self.btn_salt, 0.05, 0.8, 0.18)

                cv2.putText(frame, f"PASO {self.paso} / {self.max_pasos}", (10, 30), 0, 0.6, (255, 255, 255), 2)

            cv2.imshow("VISOR_TURISMO_AR", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = VisorTurismoAR()
    app.run()