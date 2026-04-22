from numpy.fft import fftfreq
import cv2
import numpy as np
import random
import os
from PIL import Image, ImageSequence, ImageDraw, ImageFont
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
        # Si la imagen no tiene canal alfa (3 canales), le agregamos uno opaco para evitar errores
        if len(img.shape) == 3 and img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            
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

def dibujar_texto_utf8(frame, texto, posicion, tamano, color_bgr):
    """Dibuja texto con soporte para caracteres especiales (ñ, tildes) usando PIL."""
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    
    # Intentar cargar Arial (estándar en Windows) o una por defecto
    try:
        font = ImageFont.truetype("arial.ttf", tamano)
    except:
        font = ImageFont.load_default()
        
    # Color PIL usa RGB
    color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
    draw.text(posicion, texto, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

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
        self.mapa_noise_mask = None # Inicialización de seguridad para evitar cierres
        self.trivia_errores = [] # Para rastrear clics incorrectos en la trivia
        self.trivia_acierto = None # Para marcar la respuesta correcta elegida
        self.hover_trivia_anims = [0.0, 0.0, 0.0, 0.0] # Animación para cada opción de la trivia
        self.hover_popup_anim = 0.0 # Animación para el efecto de onda del pop-up
        self.hover_trivia_anims_2 = [0.0, 0.0, 0.0, 0.0] # Animación para la segunda trivia
        self.hover_mapa_anim = 0.0 # Efecto de fluido/hundimiento para el mapa
        
        # Cargar botones de interfaz
        self.btn_sig = self._buscar_archivo_ui('next.png')
        self.btn_salt = self._buscar_archivo_ui('skip.png')
        self.btn_back = self._buscar_archivo_ui('back.png')
        self.btn_input = self._buscar_archivo_ui('input_box.png')
        self.img_pregunta = self._buscar_archivo_ui('pregunta.png')
        self.avatar_5 = self._buscar_archivo_ui('avatar_5.png')
        self.img_escaner = self._buscar_archivo_ui('fondo_escaner.png')
        
        # Igualar el tamaño del botón 'saltar' y 'atrás' al botón 'siguiente' para mantener consistencia
        if self.btn_sig is not None:
            h, w = self.btn_sig.shape[:2]
            if self.btn_salt is not None:
                self.btn_salt = cv2.resize(self.btn_salt, (w, h), interpolation=cv2.INTER_AREA)
            if self.btn_back is not None:
                self.btn_back = cv2.resize(self.btn_back, (w, h), interpolation=cv2.INTER_AREA)

        # Iniciamos el motor de síntesis de voz en segundo plano
        self.tts = TTSManager()
        
        # Iniciamos la ambientación musical
        self.iniciar_musica_fondo()
        
        self.anim_frame = 0 # Contador para controlar tiempos de animaciones
        
        # Variables para interactividad de botones
        self.mouse_x, self.mouse_y = 0, 0
        self.hover_sig_anim = 0.0  # 0.0 a 1.0 para suavizar la animación
        self.hover_back_anim = 0.0
        self.hover_salt_anim = 0.0
        self.hover_tienda_anim = 0.0

        # Sistema de Recompensas y Tienda
        self.monedas = 0
        self.tienda_abierta = False
        self.atuendo_actual = "original"
        self.outfits_comprados = ["original"]
        self.outfits_disponibles = [
            {"id": "original", "nombre": "Original", "precio": 0},
            {"id": "elegante", "nombre": "Traje Elegante", "precio": 100},
            {"id": "explorador", "nombre": "Monteriano", "precio": 150}
        ]
        self.sitio_actual_id = "" # Para recargar activos al cambiar de outfit

        # Cargar icono de tienda
        self.btn_tienda = self._buscar_archivo_ui('shop.png')
        self.btn_moneda = self._buscar_archivo_ui('coin.png')

        # Configuración de Trivia para el Paso 5
        self.trivia_opciones = [1938]
        while len(self.trivia_opciones) < 4:
            anio = random.randint(1900, 1999)
            if anio not in self.trivia_opciones:
                self.trivia_opciones.append(anio)
        random.shuffle(self.trivia_opciones)

        self.trivia_opciones_fase2 = ["Francisco de Miranda", "Gabriel García Márquez", "Policarpa Salavarrieta", "Justo Manuel Triviña"]

        self.trivia_fase = 1 # 1: Año, 2: Autor
        self.input_texto = "" # Para almacenar lo que el usuario escribe

    def dibujar_sombra(self, frame, cx, cy, rx, ry):
        """Dibuja una elipse semitransparente como sombra bajo los personajes."""
        if rx <= 0 or ry <= 0: return
        overlay = frame.copy()
        # Color oscuro para la sombra (gris muy oscuro/negro)
        cv2.ellipse(overlay, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, (20, 20, 20), -1)
        # Aplicamos transparencia (0.35 de opacidad para la sombra)
        cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)

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
                    pygame.mixer.music.set_volume(0.4) # Volumen un poco más alto
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
        
        self.sitio_actual_id = sitio_id
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None, 'textos': {}}
        archivos = os.listdir(path_sitio)
        
        for i in range(1, self.max_pasos + 1):
            # Buscar avatar con prioridad al atuendo actual
            path_avatar = os.path.join(path_sitio, f"avatar_{i}.gif")
            if self.atuendo_actual != "original":
                path_custom = os.path.join(self.base_dir, 'assets', 'outfits', self.atuendo_actual, f"avatar_{i}.gif")
                if os.path.exists(path_custom):
                    path_avatar = path_custom
            
            if os.path.exists(path_avatar):
                self.activos['avatars'][i] = GifHandler(path_avatar)

            for f in archivos:
                if f.lower() == f"burbuja_{i}.gif":
                    self.activos['burbujas'][i] = GifHandler(os.path.join(path_sitio, f))
        
        if 'historica.png' in [f.lower() for f in archivos]:
            self.activos['foto_h'] = cv2.imread(os.path.join(path_sitio, 'historica.png'), cv2.IMREAD_UNCHANGED)

        self.activos['mapa_img'] = None
        self.activos['pop_up_img'] = None
        self.mapa_noise_mask = None # Resetear máscara al cargar nuevo sitio
        
        mapa_file = next((f for f in archivos if f.lower().startswith('mapa.') and f.lower().endswith(('.png', '.jpg', '.jpeg'))), None)
        pop_up_file = next((f for f in archivos if f.lower().startswith('pop_up.') and f.lower().endswith(('.png', '.jpg', '.jpeg'))), None)

        if mapa_file:
            img = cv2.imread(os.path.join(path_sitio, mapa_file), cv2.IMREAD_UNCHANGED)
            if img is not None and len(img.shape) == 3 and img.shape[2] == 3: img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            self.activos['mapa_img'] = img
            
            # Generar máscara compleja de materialización (H, V, Diag, Ruido) aquí, si el mapa se cargó
            if self.activos['mapa_img'] is not None:
                h, w = self.activos['mapa_img'].shape[:2]
                noise = np.random.rand(h, w).astype(np.float32)
                h_mask = np.repeat(np.random.rand(h // 6 + 1), 6)[:h, np.newaxis]
                v_mask = np.repeat(np.random.rand(w // 6 + 1), 6)[np.newaxis, :w]
                yy, xx = np.indices((h, w))
                diag = (xx + yy) / (w + h)
                combined = (noise * 0.4 + h_mask * 0.2 + v_mask * 0.2 + diag * 0.2)
                
                diff = combined.max() - combined.min()
                if diff > 0:
                    self.mapa_noise_mask = (combined - combined.min()) / diff
                else:
                    self.mapa_noise_mask = combined
            else:
                self.mapa_noise_mask = None # Asegurarse de que sea None si el mapa no se cargó
        if pop_up_file:
            img = cv2.imread(os.path.join(path_sitio, pop_up_file), cv2.IMREAD_UNCHANGED)
            if img is not None and len(img.shape) == 3 and img.shape[2] == 3: img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            self.activos['pop_up_img'] = img
            
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

    def reproducir_texto_paso(self, mensaje_extra=""):
        if self.paso == 5:
            if self.trivia_fase == 1:
                print("  [GAME] Iniciando desafío del Paso 5 (Parte 1)...")
                self.tts.decir(mensaje_extra + "podrias recordarme en que año se tomó la foto para avanzar")
            else:
                print("  [GAME] Iniciando desafío del Paso 5 (Parte 2)...")
                self.tts.decir(mensaje_extra + "¿quien tomo la foto?")
            return

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
        self.tts.decir(mensaje_extra + texto)

    def _cambiar_paso(self, nuevo_paso, mensaje_extra=""):
        """Cambia el paso y reinicia animaciones y voz."""
        self.paso = nuevo_paso
        self.anim_frame = 0
        self.trivia_errores = [] # Limpiar errores al cambiar de fase o paso
        self.trivia_acierto = None
        self.hover_trivia_anims = [0.0, 0.0, 0.0, 0.0]
        self.hover_trivia_anims_2 = [0.0, 0.0, 0.0, 0.0]
        self.hover_mapa_anim = 0.0
        # Reiniciar frames de los GIFs activos para que empiecen de cero
        for handler in list(self.activos['avatars'].values()) + list(self.activos['burbujas'].values()):
            handler.current_frame = 0
        self.reproducir_texto_paso(mensaje_extra)

    def mouse_callback(self, event, x, y, flags, param):
        h_f, w_f = param
        # Actualizar posición del mouse siempre
        self.mouse_x, self.mouse_y = x, y
        
        if event == cv2.EVENT_LBUTTONDOWN and self.guia_activo:
            # Botón Tienda (Arriba a la derecha)
            if w_f * 0.86 < x < w_f * 0.94 and h_f * 0.01 < y < h_f * 0.08:
                self.tienda_abierta = not self.tienda_abierta
                return

            if self.tienda_abierta:
                # Lógica de clics dentro del menú de la tienda
                for i, outfit in enumerate(self.outfits_disponibles):
                    y_box = 80 + i * 60
                    if w_f - 250 < x < w_f - 50 and y_box < y < y_box + 50:
                        if outfit["id"] in self.outfits_comprados:
                            # Seleccionar atuendo ya comprado
                            self.atuendo_actual = outfit["id"]
                            if self.sitio_actual_id: self.cargar_activos_sitio(self.sitio_actual_id)
                        elif self.monedas >= outfit["precio"]:
                            # Comprar nuevo atuendo
                            self.monedas -= outfit["precio"]
                            self.outfits_comprados.append(outfit["id"])
                            self.atuendo_actual = outfit["id"]
                            if self.sitio_actual_id: self.cargar_activos_sitio(self.sitio_actual_id)
                        return
                return

            # --- Lógica de Juego (Paso 5) ---
            if self.paso == 5 and self.trivia_fase == 1:
                for i, anio in enumerate(self.trivia_opciones):
                    x1, y1 = int(w_f * 0.72), int(h_f * (0.35 + i * 0.12))
                    x2, y2 = x1 + 140, y1 + 50
                    if x1 < x < x2 and y1 < y < y2:
                        if anio == 1938:
                            self.trivia_acierto = anio
                            self.trivia_fase = 2 # Pasar a la siguiente pregunta del autor
                            self._cambiar_paso(self.paso, "¡Correcto! ")
                            self.monedas += 50
                        else:
                            if anio not in self.trivia_errores:
                                self.trivia_errores.append(anio)
                            self.tts.decir("Ese no es el año correcto. ¡Sigue intentando!")
                        return

            elif self.paso == 5 and self.trivia_fase == 2:
                for i, nombre in enumerate(self.trivia_opciones_fase2):
                    x1, y1_base = int(w_f * 0.25), int(h_f * (0.55 + i * 0.08))
                    x2, y2_base = x1 + 320, y1_base + 40
                    if x1 < x < x2 and y1_base < y < y2_base:
                        if nombre == "Justo Manuel Triviña":
                            self.trivia_acierto = nombre
                            self.monedas += 100
                            self._cambiar_paso(self.paso + 1, "excelente ya podemos avanzar por la historia de monteria. ")
                        else:
                            if nombre not in self.trivia_errores:
                                self.trivia_errores.append(nombre)
                            self.tts.decir("Ese no es el nombre correcto. Intenta de nuevo.")
                        return

            # Lógica de botones de navegación inferior
            if y > h_f * 0.75:
                # Botón Atrás (Izquierda) - Ahora disponible durante las trivias
                if x < w_f * 0.18:
                    if self.paso > 1:
                        # Si estamos en la fase 2 de la trivia, regresar a la fase 1
                        if self.paso == 5 and self.trivia_fase == 2:
                            self.trivia_fase = 1
                            self.input_texto = ""
                            self._cambiar_paso(5)
                        else:
                            self._cambiar_paso(self.paso - 1)
                
                # Los botones Siguiente y Saltar siguen bloqueados hasta completar la trivia
                elif self.paso != 5:
                    # Botón Siguiente (Derecha)
                    if x > w_f * 0.7:
                        if self.paso < self.max_pasos:
                            self._cambiar_paso(self.paso + 1)
                        else:
                            self.guia_activo = False # Salir si se presiona siguiente en el último paso
                    # Botón Saltar (Al lado de Atrás)
                    elif 0.18 * w_f <= x < 0.38 * w_f:
                        self._cambiar_paso(self.max_pasos)

    def run(self):
        cv2.namedWindow("VISOR_TURISMO_AR")
        while True:
            ret, frame = self.cap.read()
            if not ret: break
            frame = cv2.flip(frame, 1)
            h_f, w_f, _ = frame.shape
            cv2.setMouseCallback("VISOR_TURISMO_AR", self.mouse_callback, param=(h_f, w_f))

            if not self.guia_activo:
                # Renderizar la imagen decorativa detrás del visor del escáner
                if self.img_escaner is not None:
                    # Forzamos que la imagen ocupe exactamente el tamaño de la pantalla
                    img_full = cv2.resize(self.img_escaner, (w_f, h_f), interpolation=cv2.INTER_AREA)
                    frame = render_alfa(frame, img_full, 0.0, -0.05, 1.0)
                
                cv2.putText(frame, "ESCANEE QR", (int(w_f * 0.38), int(h_f * 0.98)), 0, 0.7, (0, 255, 0), 2)
                # Resetear trivia y tienda al volver a escanear
                self.trivia_fase = 1
                self.input_texto = ""
                self.trivia_errores = []
                self.trivia_acierto = None
                self.hover_trivia_anims = [0.0, 0.0, 0.0, 0.0]
                self.tienda_abierta = False
                data, _, _ = self.detector.detectAndDecode(frame)
                if data:
                    if self.cargar_activos_sitio(data):
                        self.guia_activo = True
                        self._cambiar_paso(1)
            else:
                # ------ INICIO LÓGICA PASO 4 (MAPA 3D) ------
                if self.paso == 4 and self.activos.get('mapa_img') is not None:
                    # Configuración de tiempos
                    duracion_caida = 40
                    duracion_materializacion = 30 # Materialización más rápida
                    
                    # Progresos de animación (0.0 a 1.0)
                    fall_prog = min(self.anim_frame / duracion_caida, 1.0)
                    mat_prog = min(self.anim_frame / duracion_materializacion, 1.0)
                    
                    mapa_original = self.activos['mapa_img']
                    h_m, w_m = mapa_original.shape[:2]
                    
                    # 1. Aplicar máscara de materialización (Líneas y ruido aleatorio)
                    mapa_animado = mapa_original.copy()
                    if self.mapa_noise_mask is not None and mapa_animado.shape[2] == 4:
                        mask = (self.mapa_noise_mask < mat_prog).astype(np.uint8) * 255
                        mapa_animado[:, :, 3] = cv2.bitwise_and(mapa_animado[:, :, 3], mask)
                    
                    # 2. Lógica de caída con Perspectiva
                    escala_base = 0.8
                    w_target = w_f * escala_base
                    h_target = h_m * (w_target / w_m)
                    
                    center_x = w_f / 2
                    bottom_y = h_f * 0.9 # El mapa pivota sobre la base del suelo
                    
                    # Coordenadas Destino: De Vertical (Inicio) a Suelo (Fin)
                    pts_inicio = np.float32([ # El mapa empieza vertical
                        [center_x - w_target/2, bottom_y - h_target], [center_x + w_target/2, bottom_y - h_target],
                        [center_x - w_target/2, bottom_y], [center_x + w_target/2, bottom_y]
                    ])
                    
                    persp_suelo = 0.85 # Efecto de profundidad (más acostado)
                    pts_fin = np.float32([
                        [center_x - (w_target/2) * persp_suelo, bottom_y - (h_target * 0.3)],
                        [center_x + (w_target/2) * persp_suelo, bottom_y - (h_target * 0.3)],
                        [center_x - w_target/2, bottom_y], [center_x + w_target/2, bottom_y]
                    ])
                    
                    # Interpolación de los puntos de destino y transformación
                    pts_dst = pts_inicio + (pts_fin - pts_inicio) * fall_prog
                    
                    # --- EFECTO DE FLUIDO / HUNDIMIENTO CUANDO FLOTA ---
                    if fall_prog >= 1.0:
                        # Detectar si el mouse está sobre el área del mapa (perspectiva)
                        cnt_mapa = pts_dst.reshape((-1, 1, 2)).astype(np.int32)
                        is_over_map = cv2.pointPolygonTest(cnt_mapa, (self.mouse_x, self.mouse_y), False) >= 0
                        
                        # Suavizado de la animación de interacción
                        self.hover_mapa_anim = min(1.0, self.hover_mapa_anim + 0.1) if is_over_map else max(0.0, self.hover_mapa_anim - 0.1)
                        
                        if self.hover_mapa_anim > 0:
                            for i in range(4):
                                px, py = pts_dst[i]
                                dist = np.sqrt((px - self.mouse_x)**2 + (py - self.mouse_y)**2)
                                # Influencia: 1.0 en el cursor, 0.0 a 350px de distancia
                                influencia = max(0, 1.0 - dist / 350.0)
                                # Hundimiento con un pequeño rebote (seno) para simular fluido
                                hundimiento = (influencia * 35 + np.sin(self.anim_frame * 0.2) * 4 * influencia) * self.hover_mapa_anim
                                pts_dst[i][1] += hundimiento # Aumentar Y es "hundir"

                    pts_src = np.float32([[0, 0], [w_m, 0], [0, h_m], [w_m, h_m]])
                    
                    try:
                        matrix = cv2.getPerspectiveTransform(pts_src, pts_dst)
                        mapa_warped = cv2.warpPerspective(mapa_animado, matrix, (w_f, h_f), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
                        frame = render_alfa(frame, mapa_warped, 0, 0, 1.0)
                    except:
                        # Fallback de seguridad si la matriz es inválida
                        frame = render_alfa(frame, mapa_animado, 0.1, 0.6, 0.8)

                    # 3. Aparición del Pop-up (sale del mapa después de que este caiga)
                    if fall_prog >= 1.0 and self.activos.get('pop_up_img') is not None:
                        pop_prog = min((self.anim_frame - duracion_caida) / 30.0, 1.0)
                        flotacion = np.sin(self.anim_frame * 0.1) * 0.02
                        # Emerge escalando y subiendo desde el centro del mapa con diagonal hacia la izquierda
                        esc_pop = 0.4 * pop_prog
                        # El pop-up también se hunde un poco si el mapa lo hace
                        y_pop = 0.6 - (0.3 * pop_prog) + flotacion + (0.05 * self.hover_mapa_anim)
                        x_pop = 0.45 - (0.35 * pop_prog) # Empieza cerca del centro y se desplaza a la izquierda
                        frame = render_alfa(frame, self.activos['pop_up_img'], x_pop, y_pop, esc_pop)
                    
                    self.anim_frame += 1
                # ------ FIN LÓGICA PASO 4 ------

                # ------ RENDERIZADO DE AVATAR CON SOMBRA ------
                av_handler = self.activos['avatars'].get(self.paso)
                if av_handler:
                    img_av = av_handler.get_frame()
                    if img_av is not None:
                        # Calculamos dimensiones del avatar escalado para la sombra
                        h_orig, w_orig = img_av.shape[:2]
                        esc = 0.7
                        w_esc, h_esc = int(w_orig * esc), int(h_orig * esc)
                        
                        # Si es el paso 1, centrar horizontalmente. Si no, usar posición lateral (0.40)
                        x_porc = (w_f - w_esc) / (2.0 * w_f) if self.paso == 1 else 0.40
                        y_porc = 0.35
                        x_px, y_px = int(w_f * x_porc), int(h_f * y_porc)
                        
                        # Dibujar la sombra proyectada hacia atrás (como si el sol estuviera delante)
                        # El radio vertical define cuánto se extiende hacia atrás
                        ry_sombra = h_esc // 15
                        self.dibujar_sombra(frame, x_px + w_esc // 2, y_px + h_esc - ry_sombra, w_esc // 2.5, ry_sombra)
                        
                        # Renderizar el avatar encima
                        frame = render_alfa(frame, img_av, x_porc, y_porc, esc)
                        
                        # Renderizar burbuja de texto encima del avatar
                        bu = self.activos['burbujas'].get(self.paso)
                        if bu and self.paso != 5:
                            # Centramos la burbuja sobre el avatar y la subimos para que flote sobre él
                            frame = render_alfa(frame, bu.get_frame(), x_porc - 0.0, y_porc - 0.40, 0.9)

                # --- RENDERIZADO DE INTERFAZ DE TRIVIA (PASO 5) ---
                if self.paso == 5:
                    if self.trivia_fase == 1:
                        # Imagen para la primera trivia (Fase 1: Años)
                        if self.avatar_5 is not None:
                            frame = render_alfa(frame, self.avatar_5, 0.02, 0.20, 0.6)

                        # Pregunta animada letra por letra saliendo de la zona de la cabeza
                        t1 = "PODRIAS RECORDARME EN QUE AÑO"
                        t2 = "SE TOMO LA FOTO PARA AVANZAR?"
                        progreso = int(self.anim_frame * 0.7)
                        
                        if progreso < len(t1):
                            frame = dibujar_texto_utf8(frame, t1[:progreso], (int(w_f*0.20), int(h_f*0.12)), 20, (0, 0, 0))
                        else:
                            frame = dibujar_texto_utf8(frame, t1, (int(w_f*0.20), int(h_f*0.12)), 20, (0, 0, 0))
                            frame = dibujar_texto_utf8(frame, t2[:max(0, progreso - len(t1))], (int(w_f*0.20), int(h_f*0.17)), 20, (0, 0, 0))
                        
                        self.anim_frame += 1 # Incrementar para manejar la animación del texto
                        
                        for i, anio in enumerate(self.trivia_opciones):
                            x1, y1_base = int(w_f * 0.72), int(h_f * (0.35 + i * 0.12))
                            x2, y2_base = x1 + 140, y1_base + 50
                            
                            hover_op = x1 < self.mouse_x < x2 and y1_base < self.mouse_y < y2_base
                            # Suavizado de la animación de levante (subida)
                            self.hover_trivia_anims[i] = min(1.0, self.hover_trivia_anims[i] + 0.3) if hover_op else max(0.0, self.hover_trivia_anims[i] - 0.3)
                            
                            # Aplicar efecto de levante a las coordenadas de dibujo
                            y_offset = int(h_f * 0.02 * self.hover_trivia_anims[i])
                            y1, y2 = y1_base - y_offset, y2_base - y_offset
                            
                            # Lógica de colores: Rojo si falló, Verde si acertó, Gris si hover
                            if anio in self.trivia_errores:
                                color_op = (0, 0, 255) # Rojo
                            elif anio == self.trivia_acierto:
                                color_op = (0, 255, 0) # Verde (solo el correcto)
                            elif hover_op:
                                color_op = (180, 180, 180) # Hover neutro para los demás
                            else:
                                color_op = (220, 220, 220) # Gris normal
                                
                            cv2.rectangle(frame, (x1, y1), (x2, y2), color_op, -1)
                            cv2.putText(frame, str(anio), (x1+35, y1+35), 0, 0.7, (0, 0, 0), 2)
                    else:
                        # Pregunta 2: El autor (Imagen de fondo + Texto encima)
                        if self.img_pregunta is not None:
                            frame = render_alfa(frame, self.img_pregunta, 0.20, 0.10, 0.6)
                        
                        frame = dibujar_texto_utf8(frame, "¿Quien tomó esta foto?", (int(w_f*0.28), int(h_f*0.38)), 26, (0, 0, 0))
                        
                        # Renderizado de opciones múltiples para la Fase 2
                        for i, nombre in enumerate(self.trivia_opciones_fase2):
                            x1, y1_base = int(w_f * 0.25), int(h_f * (0.55 + i * 0.08))
                            x2, y2_base = x1 + 320, y1_base + 40
                            
                            hover_op = x1 < self.mouse_x < x2 and y1_base < self.mouse_y < y2_base
                            # Suavizado de la animación
                            self.hover_trivia_anims_2[i] = min(1.0, self.hover_trivia_anims_2[i] + 0.3) if hover_op else max(0.0, self.hover_trivia_anims_2[i] - 0.3)
                            
                            y_offset = int(h_f * 0.01 * self.hover_trivia_anims_2[i])
                            y1, y2 = y1_base - y_offset, y2_base - y_offset
                            
                            # Lógica de colores
                            if nombre in self.trivia_errores:
                                color_op = (0, 0, 255) # Rojo
                            elif nombre == self.trivia_acierto:
                                color_op = (0, 255, 0) # Verde
                            elif hover_op:
                                color_op = (180, 180, 180) # Hover
                            else:
                                color_op = (220, 220, 220) # Gris
                                
                            cv2.rectangle(frame, (x1, y1), (x2, y2), color_op, -1)
                            # Usamos dibujar_texto_utf8 para los nombres por caracteres especiales
                            frame = dibujar_texto_utf8(frame, nombre, (x1 + 10, y1 + 5), 18, (0, 0, 0))

                if self.paso == self.max_pasos and self.activos['foto_h'] is not None:
                    # Mover la foto histórica para no tapar el avatar
                    frame = render_alfa(frame, self.activos['foto_h'], 0.10, 0.10, 0.3)

                # --- LÓGICA DE INTERACTIVIDAD DE BOTONES ---
                # Detectar hover basado en las mismas regiones del mouse_callback
                hover_sig = self.mouse_x > w_f * 0.7 and self.mouse_y > h_f * 0.75
                hover_back = self.mouse_x < w_f * 0.18 and self.mouse_y > h_f * 0.75
                hover_salt = 0.18 * w_f <= self.mouse_x < 0.38 * w_f and self.mouse_y > h_f * 0.75

                # Suavizado de la animación (incremento/decremento gradual)
                self.hover_sig_anim = min(1.0, self.hover_sig_anim + 0.3) if hover_sig else max(0.0, self.hover_sig_anim - 0.3)
                self.hover_back_anim = min(1.0, self.hover_back_anim + 0.3) if hover_back else max(0.0, self.hover_back_anim - 0.3)
                self.hover_salt_anim = min(1.0, self.hover_salt_anim + 0.3) if hover_salt else max(0.0, self.hover_salt_anim - 0.3)

                # Aplicar efecto de "levante" (sube un poco y crece ligeramente)
                if self.btn_sig is not None and self.paso != 5:
                    y_btn = 0.8 - (0.03 * self.hover_sig_anim) # Sube hasta un 3% de la pantalla
                    esc_btn = 0.18 + (0.02 * self.hover_sig_anim) # Crece un poco
                    frame = render_alfa(frame, self.btn_sig, 0.75, y_btn, esc_btn)

                if self.btn_back is not None:
                    y_btn = 0.8 - (0.03 * self.hover_back_anim)
                    esc_btn = 0.18 + (0.02 * self.hover_back_anim)
                    frame = render_alfa(frame, self.btn_back, 0.05, y_btn, esc_btn)

                if self.btn_salt is not None and self.paso != 5:
                    y_btn = 0.8 - (0.03 * self.hover_salt_anim)
                    esc_btn = 0.18 + (0.02 * self.hover_salt_anim)
                    frame = render_alfa(frame, self.btn_salt, 0.20, y_btn, esc_btn)

                cv2.putText(frame, f"PASO {self.paso} / {self.max_pasos}", (10, 30), 0, 0.6, (255, 255, 255), 2)

                # --- INTERFAZ GLOBAL (MONEDAS Y TIENDA) ---
                # Dibujar contador de monedas
                if self.btn_moneda is not None:
                    frame = render_alfa(frame, self.btn_moneda, 0.21, 0.02, 0.03)
                    frame = dibujar_texto_utf8(frame, str(self.monedas), (int(w_f * 0.26), 10), 20, (0, 255, 255))
                else:
                    frame = dibujar_texto_utf8(frame, f"MONEDAS: {self.monedas}", (int(w_f * 0.22), 10), 20, (0, 255, 255))
                
                # Lógica de interactividad para el botón de tienda
                hover_tienda = w_f * 0.86 < self.mouse_x < w_f * 0.94 and h_f * 0.01 < self.mouse_y < h_f * 0.08
                self.hover_tienda_anim = min(1.0, self.hover_tienda_anim + 0.3) if hover_tienda else max(0.0, self.hover_tienda_anim - 0.3)

                if self.btn_tienda is not None:
                    # Efecto de levante y escala para el icono de tienda
                    y_tienda = 0.02 - (0.01 * self.hover_tienda_anim)
                    esc_tienda = 0.03 + (0.01 * self.hover_tienda_anim)
                    frame = render_alfa(frame, self.btn_tienda, 0.88, y_tienda, esc_tienda)
                else:
                    # Fallback visual si no se encuentra 'shop.png' (Mantiene la funcionalidad)
                    color_tienda = (0, 140, 255) if not self.tienda_abierta else (0, 0, 255)
                    cv2.rectangle(frame, (int(w_f*0.88), int(h_f*0.02)), (int(w_f*0.93), int(h_f*0.08)), color_tienda, -1)
                    cv2.putText(frame, "T", (int(w_f*0.89), int(h_f*0.06)), 0, 0.4, (255, 255, 255), 1)

                if self.tienda_abierta:
                    # Fondo semitransparente para el menú
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (w_f - 260, 60), (w_f - 10, 350), (40, 40, 40), -1)
                    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
                    
                    for i, outfit in enumerate(self.outfits_disponibles):
                        y_box = 80 + i * 60
                        comprado = outfit["id"] in self.outfits_comprados
                        color_item = (0, 255, 0) if comprado else (200, 200, 200)
                        if outfit["id"] == self.atuendo_actual: color_item = (255, 255, 0)
                        
                        cv2.rectangle(frame, (w_f - 250, y_box), (w_f - 50, y_box + 50), color_item, 2)
                        txt = outfit["nombre"]
                        if not comprado: txt += f" (${outfit['precio']})"
                        elif outfit["id"] == self.atuendo_actual: txt += " [PUESTO]"
                        
                        frame = dibujar_texto_utf8(frame, txt, (w_f - 240, y_box + 15), 16, (255, 255, 255))

            cv2.imshow("VISOR_TURISMO_AR", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            

        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = VisorTurismoAR()
    app.run()