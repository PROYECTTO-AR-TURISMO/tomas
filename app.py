import cv2
import numpy as np
import random
import os
import time
import pytesseract
import pygame

# Importar los nuevos módulos
from utils import GifHandler, render_alfa, dibujar_texto_utf8, load_ui_asset
from audio_manager import AudioManager
from animation_manager import AnimationManager
from map_system import MapSystem
from trivia_system import TriviaSystem
from shop_system import ShopSystem
from ui_manager import UIManager
from ar_renderer import ARRenderer
from puzzle_system import PuzzleSystem
from planchon_system import PlanchonSystem

# Configuraciones de OCR para Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ['TESSDATA_PREFIX'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tessdata')

# --- CLASE PRINCIPAL DEL VISOR AR ---
class App: # Renombrado de VisorTurismoAR a App
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"\n[SISTEMA] Ruta base: {self.base_dir}")
        
        # Inicializar gestores
        self.audio_manager = AudioManager(self.base_dir)
        self.animation_manager = AnimationManager(self.base_dir)
        self.map_system = MapSystem(self.base_dir)
        self.trivia_system = TriviaSystem()
        self.shop_system = ShopSystem(self.base_dir)
        self.ui_manager = UIManager(self.base_dir)
        self.puzzle_system = PuzzleSystem()
        self.planchon_system = PlanchonSystem(self.base_dir)
        self.ar_renderer = ARRenderer(self.base_dir, self.map_system, self.ui_manager, self.animation_manager)

        # Variables de estado de la aplicación
        self.estado = "bienvenida" # bienvenida, escaneo, mapa, guia
        self.guia_activo = False   # Mantenemos por compatibilidad con renderer
        self.ayuda_activa = False
        self.paso = 1
        self.max_pasos = 6
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None}
        self.s1_completado = False # Ronda del Sinú
        self.s2_completado = False # Catedral
        self.s3_completado = False # Planchones
        self.animales_stampida = [] # Lista para manejar la estampida del paso 2
        
        # Inicializar variables de mouse
        self.mouse_x, self.mouse_y = 0, 0
        self.last_avatar_bbox = None # Almacena (x, y, w, h) del último avatar renderizado para detección de clic

        # Variables para la transición diferida
        self.proximo_paso = None
        self.proximo_mensaje = ""
        self.sitio_actual_id = "" # Para recargar activos al cambiar de outfit
        self.running = True
        # Inicializar la música de fondo
        self.audio_manager.iniciar_musica_fondo()
        self.map_system.update_progreso({'s1': self.s1_completado, 's2': self.s2_completado, 's3': self.s3_completado, 's1_completado': self.s1_completado, 's2_completado': self.s2_completado})

    def abrir_mapa(self, forzar_abierto=False):
        """Centraliza la apertura del mapa y la instrucción por voz."""
        self.guia_activo = False
        self.estado = "mapa"
        self.map_system.modo_seleccion = True
        self.map_system.update_progreso({'s1': self.s1_completado, 's2': self.s2_completado, 's3': self.s3_completado, 's1_completado': self.s1_completado, 's2_completado': self.s2_completado})
        if forzar_abierto:
            self.map_system.anim_mapa_progreso = 1.0
        txt = "¿cual es el siguiente sitio?" if self.s1_completado else "selecciona el primer sitio turistico para desbloquear los otros"
        self.audio_manager.tts.decir(txt)

    def is_step_finished(self):
        """Comprueba si el audio del paso, la burbuja y el avatar han terminado."""
        # Verificar audio (Canal 1 es el TTS)
        if pygame.mixer.get_init() and pygame.mixer.Channel(1).get_busy():
            return False
        # Verificar burbuja
        bu = self.activos.get('burbujas', {}).get(self.paso)
        if bu and bu.frames:
            if bu.current_frame < len(bu.frames) - 1:
                return False
        # Verificar avatar
        av = self.activos.get('avatars', {}).get(self.paso)
        if av and av.frames:
            if av.current_frame < len(av.frames) - 1:
                return False
        return True

    def saltar_informacion(self):
        """Finaliza inmediatamente la reproducción de audio y animaciones del paso actual."""
        # 1. Detener audio del Canal 1 (TTS)
        if pygame.mixer.get_init():
            pygame.mixer.Channel(1).stop()
        print(f"[DEBUG] Saltar Información: Deteniendo audio y forzando fin de GIFs para paso {self.paso}")
        
        # 2. Forzar el último frame en el avatar y la burbuja para que is_step_finished() sea True
        av = self.activos.get('avatars', {}).get(self.paso)
        if av and av.frames:
            av.current_frame = len(av.frames) - 1
            
        bu = self.activos.get('burbujas', {}).get(self.paso)
        if bu and bu.frames:
            bu.current_frame = len(bu.frames) - 1
        
        # Después de esto, is_step_finished() debería retornar True en el siguiente ciclo de renderizado.

    def cargar_activos_sitio(self, texto_qr):
        sitio_id = texto_qr.strip().lower()
        path_sitio = os.path.join(self.base_dir, 'assets', 'sitios', sitio_id)
        
        if not os.path.exists(path_sitio):
            print(f"  [ERROR] No existe la carpeta: {path_sitio}")
            return False
        
        self.sitio_actual_id = sitio_id
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None, 'textos': {}, 'vaca_gif': None, 'iguana_gif': None, 'suelo_textura': None, 'porton': None, 'avatar_trivia': None}
        archivos = os.listdir(path_sitio)
        
        # Ajustar cantidad de pasos y mapeo de archivos según el sitio
        if sitio_id == 'sitio_2':
            self.max_pasos = 5 # Ahora son 5 pasos (Intro, Estampida, Mapa, Puzzle, Felicitaciones)
        elif sitio_id == 'sitio_3':
            self.max_pasos = 5 # Intro (8), Historia 1 (9), Historia 2 (9.2), Planchón, Felicitaciones (10)
            self.planchon_system.reset()
        else:
            self.max_pasos = 6

        # Limpiar puzzle previo
        self.puzzle_system.activo = False
        self.puzzle_system.piezas = []

        for i in range(1, self.max_pasos + 1):
            # Lógica de asignación de nombres de archivo según el sitio
            es_ultimo_paso = (i == self.max_pasos)
            
            if sitio_id == 'sitio_3':
                if i == 1: nombre_av, nombre_bu = "avatar_8.gif", "burbuja_8.gif"
                elif i == 2: nombre_av, nombre_bu = "avatar_9.gif", "burbuja_9.gif"
                elif i == 3: nombre_av, nombre_bu = "avatar_9.gif", "burbuja_9.2.gif"
                elif i == 4: nombre_av, nombre_bu = "", "" # Sin avatar durante el juego
                elif es_ultimo_paso: nombre_av, nombre_bu = "avatar_10.gif", "burbuja_10.gif"
                else: nombre_av, nombre_bu = "", ""
            else:
                # Para sitio_2, el paso 1 usa el archivo 5 y el paso 2 el 6
                file_num = i + 4 if sitio_id == 'sitio_2' else i
                
                # Identificar nombres de archivos (Especial para felicitaciones al final de cada sitio)
                nombre_av = "avatar_felicitaciones.gif" if es_ultimo_paso else f"avatar_{file_num}.gif"
                nombre_bu = "burbuja_felicitaciones.gif" if es_ultimo_paso else f"burbuja_{file_num}.gif"

            if not nombre_av: continue

            # Buscar avatar de forma insensible a mayúsculas y permitiendo nombres alternativos
            nombre_av_real = next((f for f in archivos if f.lower() == nombre_av.lower() or (es_ultimo_paso and f.lower() == "avatar_felicitaciones.gif")), None)
            if not nombre_av_real: continue

            path_avatar = os.path.join(path_sitio, nombre_av_real)
            if os.path.exists(path_avatar):
                handler = GifHandler(path_avatar)
                if handler.frames: # Solo añadir si se cargaron frames correctamente
                    if sitio_id == 'sitio_2' and i == 2:
                        handler.paused = True
                    self.activos['avatars'][i] = handler
                else:
                    print(f"  [WARNING] GifHandler no pudo cargar frames para el avatar: {path_avatar}")

            # Búsqueda flexible de la burbuja
            nombre_bu_real = next((f for f in archivos if f.lower() == nombre_bu.lower() or (es_ultimo_paso and f.lower() == "burbuja_felicitaciones.gif")), nombre_bu)
            for f in archivos:
                if f.lower() == nombre_bu_real.lower():
                    burbuja_handler = GifHandler(os.path.join(path_sitio, f))
                    if burbuja_handler.frames: # Solo añadir si se cargaron frames correctamente
                        self.activos['burbujas'][i] = burbuja_handler
                    else:
                        print(f"  [WARNING] GifHandler no pudo cargar frames para la burbuja: {os.path.join(path_sitio, f)}")
        
        # Búsqueda flexible de la foto histórica (soporta .png, .jpg, .jpeg y mayúsculas)
        foto_h_file = next((f for f in archivos if f.lower().startswith('historica.')), None)
        if foto_h_file:
            path_h = os.path.join(path_sitio, foto_h_file)
            self.activos['foto_h'] = cv2.imread(path_h, cv2.IMREAD_UNCHANGED)
            
            # Si es el sitio 2, preparamos el puzzle para el paso final
            if sitio_id == 'sitio_2' and self.activos['foto_h'] is not None:
                self.puzzle_system.inicializar_puzzle(self.activos['foto_h'])

        # Cargar avatar especial de duda (para la trivia en paso 5)
        self.activos['avatar_trivia'] = load_ui_asset('duda.png', self.base_dir, sitio_id)

        # Cargar GIFs de animales para la estampida (Paso 2)
        vaca_path = load_ui_asset('vaca.gif', self.base_dir, sitio_id)
        if vaca_path: self.activos['vaca_gif'] = GifHandler(vaca_path)
        
        iguana_path = load_ui_asset('iguana.gif', self.base_dir, sitio_id)
        if iguana_path: self.activos['iguana_gif'] = GifHandler(iguana_path)

        # Cargar suelo específico si existe (suelo.png)
        if 'suelo.png' in [f.lower() for f in archivos]:
            img_s = cv2.imread(os.path.join(path_sitio, 'suelo.png'), cv2.IMREAD_UNCHANGED)
            if img_s is not None:
                if len(img_s.shape) == 3: img_s = cv2.cvtColor(img_s, cv2.COLOR_BGR2BGRA)
                self.activos['suelo_textura'] = img_s

        # Cargar y pre-procesar el portón para el paso 2
        if 'porton.png' in [f.lower() for f in archivos]:
            img_p = cv2.imread(os.path.join(path_sitio, 'porton.png'), cv2.IMREAD_UNCHANGED)
            if img_p is not None:
                if len(img_p.shape) == 3: img_p = cv2.cvtColor(img_p, cv2.COLOR_BGR2BGRA)

                
                # Aplicar inclinación de perspectiva para dar profundidad
                h_p, w_p = img_p.shape[:2]
                pts1 = np.float32([[0,0], [w_p,0], [0,h_p], [w_p,h_p]])
                # Inclinamos el lado derecho para que parezca una puerta en ángulo
                pts2 = np.float32([[w_p*0.1, h_p*0.1], [w_p*0.9, 0], [w_p*0.1, h_p*0.9], [w_p*0.9, h_p]])
                matrix_p = cv2.getPerspectiveTransform(pts1, pts2)
                self.activos['porton'] = cv2.warpPerspective(img_p, matrix_p, (w_p, h_p), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))

        self.activos['mapa_img'] = None
        self.activos['pop_up_img'] = None
        self.activos['mapa_mask'] = None # Resetear máscara al cargar nuevo sitio
        
        mapa_file = next((f for f in archivos if f.lower().startswith('mapa.') and f.lower().endswith(('.png', '.jpg', '.jpeg'))), None)
        pop_up_file = next((f for f in archivos if f.lower().startswith('pop_up.') and f.lower().endswith(('.png', '.jpg', '.jpeg'))), None)

        if mapa_file:
            img = cv2.imread(os.path.join(path_sitio, mapa_file), cv2.IMREAD_UNCHANGED)
            if img is not None and len(img.shape) == 3 and img.shape[2] == 3: img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            self.activos['mapa_img'] = img
        elif sitio_id in ['sitio_2', 'sitio_3']:
            # Si no hay mapa específico, usamos el mapa general para la animación 3D
            self.activos['mapa_img'] = self.map_system.img_mapa_general

        # Generar máscara compleja de materialización (H, V, Diag, Ruido) si hay un mapa cargado (específico o general)
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
                self.activos['mapa_mask'] = (combined - combined.min()) / diff
            else:
                self.activos['mapa_mask'] = combined
        else:
            self.activos['mapa_mask'] = None

        # Búsqueda de pop-up: Soporta 'pop_up' estándar o 'planchonantes' para el sitio 3
        pop_up_file = next((f for f in archivos if (f.lower().startswith('pop_up.') or f.lower().startswith('planchonantes.') or f.lower().startswith('planchon.')) 
                           and f.lower().endswith(('.png', '.jpg', '.jpeg'))), None)
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
        if self.paso == 5 and self.sitio_actual_id == 'sitio1':
            if self.trivia_system.trivia_fase == 1:
                print("  [GAME] Iniciando desafío del Paso 5 (Parte 1)...")
                self.audio_manager.tts.decir(mensaje_extra + "podrias recordarme en que año se tomó la foto para avanzar")
            else:
                print("  [GAME] Iniciando desafío del Paso 5 (Parte 2)...")
                self.audio_manager.tts.decir(mensaje_extra + "¿quien tomo la foto?")
            return
        # Si es el paso del rompecabezas del Sitio 2
        if self.sitio_actual_id == 'sitio_2' and self.paso == 4:
            self.audio_manager.tts.decir(mensaje_extra + "ayudame a armar la catedral")
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
        self.audio_manager.tts.decir(mensaje_extra + texto)

    def _cambiar_paso(self, nuevo_paso, mensaje_extra=""):
        """Aplica el cambio de paso de forma inmediata."""
        self.proximo_paso = nuevo_paso
        self.proximo_mensaje = mensaje_extra
        self._ejecutar_cambio_real()

    def _ejecutar_cambio_real(self):
        """Aplica el cambio de estado cuando la pantalla está totalmente oscurecida."""
        if self.proximo_paso is None: return
        
        self.paso = self.proximo_paso
        self.animation_manager.anim_frame = 0
        self.trivia_system.trivia_errores = [] # Limpiar errores al cambiar de fase o paso
        self.trivia_system.trivia_acierto = None
        self.animation_manager.hover_trivia_anims = [0.0, 0.0, 0.0, 0.0]
        self.animation_manager.hover_trivia_anims_2 = [0.0, 0.0, 0.0, 0.0]
        self.animation_manager.hover_mapa_anim = 0.0
        self.animales_stampida = []
        self.planchon_system.activo = (self.sitio_actual_id == 'sitio_3' and self.paso == 4)
        
        for handler in list(self.activos['avatars'].values()) + list(self.activos['burbujas'].values()):
            handler.current_frame = 0
            handler.spawn_timer = 0  # Reiniciar tiempo de caída
            handler.dust_done = False # Permitir que salga polvo de nuevo
            
        self.reproducir_texto_paso(self.proximo_mensaje)
        self.proximo_paso = None

    def mouse_callback(self, event, x, y, flags, param):
        h_f, w_f = param
        # Actualizar posición del mouse siempre
        self.mouse_x, self.mouse_y = x, y

        # --- 1. GESTIÓN DE LA TIENDA (BLOQUEO DE CAPAS) ---
        if self.shop_system.tienda_abierta:
            if event == cv2.EVENT_LBUTTONDOWN:
                panel_w = 300
                offset_x = 0 # Asumimos panel abierto
                x1 = w_f - panel_w
                # Botón Cerrar (X)
                if np.sqrt((x - (w_f - 40))**2 + (y - 40)**2) < 20:
                    self.shop_system.tienda_abierta = False
                    return
                # Clic fuera del panel
                if x < x1:
                    self.shop_system.tienda_abierta = False
                    return
                # Clic en items
                for i, outfit in enumerate(self.shop_system.outfits_disponibles):
                    y_box = 100 + i * 110 + self.animation_manager.shop_scroll_y
                    if x1 + 20 < x < w_f - 20 and y_box < y < y_box + 90:
                        if outfit["id"] in self.shop_system.marcos_comprados:
                            self.shop_system.marco_actual = outfit["id"]
                            self.animation_manager.frame_transition_alpha = 0.0
                        elif self.shop_system.monedas >= outfit["precio"]:
                            self.shop_system.monedas -= outfit["precio"]
                            self.shop_system.marcos_comprados.append(outfit["id"])
                            self.shop_system.marco_actual = outfit["id"]
                            self.animation_manager.frame_transition_alpha = 0.0
                        return
            # Bloquear cualquier otro evento si la tienda está abierta
            if event == cv2.EVENT_MOUSEWHEEL:
                delta = 45 if flags > 0 else -45
                self.animation_manager.shop_scroll_y = min(0, self.animation_manager.shop_scroll_y + delta)
            return

        if self.estado == "bienvenida":
            if event == cv2.EVENT_LBUTTONDOWN:
                # Botón "Comenzar" abajo a la derecha
                if (w_f*0.7 < x < w_f*0.98) and (h_f*0.8 < y < h_f*0.95):
                    self.animation_manager.start_transition()
                    self.estado = "escaneo"
            return

        # Botones HUD Globales
        if event == cv2.EVENT_LBUTTONDOWN and self.ui_manager.is_hovering_shop_button(x, y, w_f, h_f):
            self.shop_system.tienda_abierta = True
            return

        # Botón de Ayuda (HUD)
        if event == cv2.EVENT_LBUTTONDOWN and self.ui_manager.is_hovering_help_button(x, y, w_f, h_f):
            self.ayuda_activa = not self.ayuda_activa
            return
            
        if self.ayuda_activa and event == cv2.EVENT_LBUTTONDOWN:
            self.ayuda_activa = False # Cerrar ayuda con cualquier clic
            return

        if event in [cv2.EVENT_LBUTTONDOWN, cv2.EVENT_MOUSEMOVE, cv2.EVENT_LBUTTONUP] and self.guia_activo:
            # Interacción exclusiva para el paso del rompecabezas (Sitio 2, Paso 4)
            if self.sitio_actual_id == 'sitio_2' and self.paso == 4 and self.puzzle_system.activo:
                # Detectar si ya hay una pieza en movimiento antes de procesar
                was_dragging = self.puzzle_system.selected_piece is not None
                fue_completado = self.puzzle_system.completado
                self.puzzle_system.manejar_mouse(event, x, y)

                # Recompensa por completar el rompecabezas de la Catedral
                if not fue_completado and self.puzzle_system.completado:
                    self.shop_system.add_coins(300) # Recompensa por el puzzle
                    self.animation_manager.add_coin_particles(x, y, 30)

                # Si se está arrastrando o se acaba de seleccionar, bloqueamos otros clics
                if was_dragging or self.puzzle_system.selected_piece is not None:
                    return

        # Interacción para el minijuego de planchones (Sitio 3, Paso 4)
        if event in [cv2.EVENT_LBUTTONDOWN, cv2.EVENT_MOUSEMOVE, cv2.EVENT_LBUTTONUP] and self.guia_activo:
            if self.sitio_actual_id == 'sitio_3' and self.paso == 4:
                self.planchon_system.manejar_mouse(event, x / w_f, y / h_f)

        if event == cv2.EVENT_MOUSEWHEEL:
            if self.map_system.modo_seleccion and self.s1_completado:
                # Permitir zoom en el mapa si la ronda 1 terminó
                delta = 0.1 if flags > 0 else -0.1
                self.map_system.target_zoom = max(0.5, min(2.5, self.map_system.target_zoom + delta))
        
        if event == cv2.EVENT_LBUTTONDOWN:
            # Botón Salir App (Esquina superior derecha del HUD)
            if np.sqrt((x - int(w_f * 0.98))**2 + (y - int(h_f * 0.04))**2) < 15:
                self.running = False
                return

        if event == cv2.EVENT_LBUTTONDOWN and self.map_system.modo_seleccion and self.map_system.anim_mapa_progreso >= 0.3 and self.map_system.mapa_matrix is not None:
            # Lógica para elegir sitio en el mapa con perspectiva
            h_m, w_m = self.map_system.img_mapa_general.shape[:2]
            for sitio in self.map_system.sitios_turisticos:
                # Transformar coordenadas relativas del sitio a pantalla usando la matriz actual
                pt_src = np.array([[[sitio['x_rel'] * w_m, sitio['y_rel'] * h_m]]], dtype=np.float32)
                pt_dst = cv2.perspectiveTransform(pt_src, self.map_system.mapa_matrix)
                px, py = pt_dst[0][0]

                # Área de detección aumentada para que responda al primer intento
                if np.sqrt((x - px)**2 + (y - py)**2) < 70 and not self.animation_manager.cinematic_active:
                    esta_bloqueado = False
                    if sitio['unlock_condition'] is not None:
                        if not self.map_system.progreso.get(sitio['unlock_condition'], False):
                            esta_bloqueado = True
                    if esta_bloqueado: return

                    self.animation_manager.add_button_pulse(x, y)
                    self.animation_manager.start_cinematic(sitio['nombre'])
                    # Iniciar ambiente después de un breve delay cinematográfico
                    pygame.time.set_timer(pygame.USEREVENT + 1, 1500)
                    if self.cargar_activos_sitio(sitio['id']):
                        self.audio_manager.iniciar_ambiente(sitio['id'])
                        self.map_system.modo_seleccion = False
                        self.estado = "guia"
                        self.guia_activo = True
                        self._cambiar_paso(1)
            return

        # --- DETECCIÓN DE CLIC EN EL AVATAR (FUERA DEL MODO SELECCIÓN) ---
        if event == cv2.EVENT_LBUTTONDOWN and self.last_avatar_bbox:
            ax, ay, aw, ah = self.last_avatar_bbox
            # Evitamos que el clic en el avatar interfiera con la zona de navegación inferior (y > 70%)
            if ax < x < ax + aw and ay < y < ay + ah and y < h_f * 0.70:
                av_handler = self.activos['avatars'].get(self.paso)
                if av_handler:
                    av_handler.current_frame = 0 # Reiniciar animación del GIF
                    av_handler.spawn_timer = 0   # Reiniciar caída
                    av_handler.dust_done = False
                bu_handler = self.activos['burbujas'].get(self.paso)
                if bu_handler:
                    bu_handler.current_frame = 0
                    self.reproducir_texto_paso() # Volver a reproducir el audio
                return

        # --- INTERACCIONES DE GUÍA (FUERA DEL MODO SELECCIÓN) ---
        if event == cv2.EVENT_LBUTTONDOWN and self.guia_activo:
            # 1. Botón de Finalización de Sitio
            if self.ui_manager.is_hovering_finish_button(x, y, w_f, h_f) and self.is_step_finished():
                if self.paso == self.max_pasos:
                    if self.sitio_actual_id == 'sitio1': self.s1_completado = True
                    elif self.sitio_actual_id == 'sitio_2': self.s2_completado = True
                    elif self.sitio_actual_id == 'sitio_3': self.s3_completado = True
                    self.abrir_mapa(forzar_abierto=True)
                    return

            # 2. Botones de Navegación (Siguiente / Atrás / Saltar)
            if y > h_f * 0.70: # Margen más amplio para detección
                if x < w_f * 0.18: # Botón Atrás
                    if self.paso > 1:
                        if self.paso == 5 and self.trivia_system.trivia_fase == 2:
                            self.trivia_system.trivia_fase = 1
                            self._cambiar_paso(5)
                        else:
                            self._cambiar_paso(self.paso - 1)
                    return
                elif x > w_f * 0.7: # Botón Siguiente
                    print("[DEBUG] Clic en botón Siguiente")
                    if self.is_step_finished():
                        # Validar que no estemos en un minijuego incompleto
                        if (self.sitio_actual_id == 'sitio1' and self.paso == 5) or \
                           (self.sitio_actual_id == 'sitio_2' and self.paso == 4 and not self.puzzle_system.completado) or \
                           (self.sitio_actual_id == 'sitio_3' and self.paso == 4 and not self.planchon_system.completado):
                            return
                        if self.paso < self.max_pasos:
                            self._cambiar_paso(self.paso + 1)
                    return
                elif 0.18 * w_f <= x < 0.38 * w_f: # Botón Saltar Información
                    print("[DEBUG] Clic en botón Saltar Información")
                    self.saltar_informacion()
                    return

            # --- Lógica de Juego (Paso 5) ---
            if self.sitio_actual_id == 'sitio1' and self.paso == 5 and self.trivia_system.trivia_fase == 1:
                # Calcular dinámicamente las dimensiones de la imagen de fondo para alinear los clics
                if self.ui_manager.bg_opciones_1 is not None:
                    target_h_bg = h_f * 0.65 # Más pequeño para que la cámara sea el fondo real
                    base_scale_bg = target_h_bg / self.ui_manager.bg_opciones_1.shape[0]
                    w_bg_px = self.ui_manager.bg_opciones_1.shape[1] * base_scale_bg
                    # Alinear a la derecha con 2% de margen (ajustado para el nuevo UI Manager)
                    x_porc_bg = (w_f - w_bg_px - (w_f * 0.02)) / w_f
                    x_img, y_img = w_f * x_porc_bg, h_f * 0.15 # Un poco más centrado verticalmente
                    w_img, h_img = w_bg_px, target_h_bg
                else:
                    x_img, y_img, w_img, h_img = w_f * 0.35, h_f * 0.10, w_f * 0.60, h_f * 0.80

                for i, anio in enumerate(self.trivia_system.trivia_opciones):
                    # Coordenadas ajustadas para representar el ancho visual real de la caja (ajustado para el nuevo UI Manager)
                    x1 = int(x_img + w_img * 0.69)
                    x2 = int(x_img + w_img * 0.92)
                    y1 = int(y_img + h_img * (0.31 + i * 0.15))
                    y2 = int(y1 + h_img * 0.09)
                    
                    if x1 < x < x2 and y1 < y < y2:
                        if self.trivia_system.check_answer_phase1(anio):
                            self.trivia_system.trivia_acierto = anio
                            self.trivia_system.trivia_fase = 2 # Pasar a la siguiente pregunta del autor
                            self._cambiar_paso(self.paso, "¡Correcto! ")
                            self.shop_system.add_coins(50)
                        else:
                            self.trivia_system.record_error(anio)
                            self.audio_manager.tts.decir("Ese no es el año correcto. ¡Sigue intentando!")
                        return

            elif self.sitio_actual_id == 'sitio1' and self.paso == 5 and self.trivia_system.trivia_fase == 2:
                # (Ajustado para el nuevo UI Manager)
                if self.ui_manager.bg_opciones_2 is not None:
                    target_h_bg = h_f * 0.70 # Mantiene el ancho
                    base_scale_bg = target_h_bg / self.ui_manager.bg_opciones_2.shape[0]
                    w_bg_px = self.ui_manager.bg_opciones_2.shape[1] * base_scale_bg
                    # Centrado horizontalmente
                    x_porc_bg = (w_f - w_bg_px) / 2 / w_f
                    x_img, y_img = w_f * x_porc_bg, h_f * 0.35 # Empujado hacia abajo para dar espacio a la pregunta
                    w_img, h_img = w_bg_px, target_h_bg
                else:
                    x_img, y_img, w_img, h_img = w_f * 0.20, h_f * 0.35, w_f * 0.60, h_f * 0.70

                for i, nombre in enumerate(self.trivia_system.trivia_opciones_fase2):
                    # Reducimos el ancho para no tapar las flores
                    x1 = int(x_img + w_img * 0.15)
                    x2 = int(x_img + w_img * 0.85)
                    # Bajamos la caja matemática para que coincida con la madera interior
                    y1 = int(y_img + h_img * (0.19 + i * 0.185))
                    y2 = int(y1 + h_img * 0.10) # Altura reducida para no salirse de la caja

                    if x1 < x < x2 and y1 < y < y2:
                        if self.trivia_system.check_answer_phase2(nombre):
                            self.trivia_system.trivia_acierto = nombre
                            self.shop_system.add_coins(100)
                            self._cambiar_paso(self.paso + 1, "excelente ya podemos avanzar por la historia de monteria. ")
                        else:
                            self.trivia_system.record_error(nombre)
                            self.audio_manager.tts.decir("Ese no es el nombre correcto. Intenta de nuevo.")
                        return

    def update_logic(self, mouse_y_rel):
        """Actualiza lógica de minijuegos."""
        if self.sitio_actual_id == 'sitio_3' and self.paso == 4:
            # Actualizar física del planchón
            fue_completado = self.planchon_system.completado
            self.planchon_system.actualizar(self.animation_manager)

            if not fue_completado and self.planchon_system.completado:
                self.shop_system.add_coins(self.planchon_system.obtener_recompensa())
                self.animation_manager.add_coin_particles(self.mouse_x, self.mouse_y, 20)

    def run(self):
        window_name = "VISOR_TURISMO_AR"
        cv2.namedWindow(window_name, cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        
        # Bandera para configurar el callback del mouse solo una vez
        callback_seteado = False
        
        while self.running:
            ret, frame = self.ar_renderer.cap.read() # Acceso correcto a la cámara
            if not ret: break
            frame = cv2.flip(frame, 1)
            h_f, w_f, _ = frame.shape # Obtener dimensiones del frame

            # Configuramos el callback una sola vez tras obtener el primer frame
            if not callback_seteado:
                # Mostramos un frame inicial para asegurar que la ventana se instancie físicamente
                cv2.imshow(window_name, frame)
                cv2.setMouseCallback(window_name, self.mouse_callback, param=(h_f, w_f))
                callback_seteado = True

            # LÓGICA DE ACTUALIZACIÓN DE ESTAMPIDA (PASO 2)
            if self.paso == 2 and self.guia_activo:
                av_h = self.activos['avatars'].get(2)
                # Disparar si el avatar desapareció y no hay animales aún
                if av_h and av_h.current_frame >= len(av_h.frames) - 1 and not self.animales_stampida:
                    for _ in range(3):
                        self.animales_stampida.append({'t': 'vaca', 'x': 0.12, 'y': 0.55 + random.uniform(0, 0.1), 's': random.uniform(0.02, 0.04), 'esc': 0.3})
                    for _ in range(5):
                        self.animales_stampida.append({'t': 'iguana', 'x': 0.12, 'y': 0.70 + random.uniform(0, 0.05), 's': random.uniform(0.03, 0.06), 'esc': 0.15})
                
                # Mover animales existentes
                for animal in self.animales_stampida:
                    animal['x'] += animal['s']

            # Lógica del planchón
            self.update_logic(self.mouse_y / h_f)

            # Actualizar estado de los gestores
            self.animation_manager.update(self.mouse_x, self.mouse_y, show_leaves=self.guia_activo)

            # Actualizar detección si estamos buscando el QR o si el mapa está abierto para que se mueva con el código
            if self.estado in ["escaneo", "mapa"]:
                self.map_system.update_qr_detection(frame, self.guia_activo)
                if self.map_system.modo_seleccion and self.estado == "escaneo":
                    self.abrir_mapa(forzar_abierto=False)
                
                # Si el mapa se cerró por perder el QR, volvemos al estado de escaneo
                if self.estado == "mapa" and self.map_system.anim_mapa_progreso <= 0 and not self.map_system.qr_detectado_persistente:
                    self.estado = "escaneo"

            # Renderizar el frame usando el ARRenderer
            frame, self.last_avatar_bbox = self.ar_renderer.render(
                frame,
                self.estado,
                self.paso,
                self.max_pasos,
                self.activos,
                self.animales_stampida,
                self.mouse_x,
                self.mouse_y,
                self.last_avatar_bbox,
                self.shop_system.monedas,
                self.shop_system.tienda_abierta,
                self.shop_system.outfits_disponibles,
                self.shop_system.marcos_comprados, # Se cambió de 'outfits_comprados'
                self.shop_system.marco_actual,     # Se cambió de 'atuendo_actual'
                self.trivia_system.trivia_fase,
                self.trivia_system.trivia_opciones,
                self.trivia_system.trivia_opciones_fase2,
                self.trivia_system.trivia_errores,
                self.trivia_system.trivia_acierto,
                self.puzzle_system,
                self.planchon_system,
                self.ayuda_activa,
                {'s1': self.s1_completado, 's2': self.s2_completado, 's3': self.s3_completado},
                self.sitio_actual_id # Pasar sitio_actual_id al renderizador
            )
            cv2.imshow("VISOR_TURISMO_AR", frame) # Mostrar el frame final
            self.animation_manager.anim_frame += 1 # Incremento global para todas las animaciones
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1: break
            

        self.ar_renderer.release_camera() # Liberar la cámara a través del ARRenderer
        cv2.destroyAllWindows()