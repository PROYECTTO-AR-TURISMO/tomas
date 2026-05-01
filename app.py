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
        self.ar_renderer = ARRenderer(self.base_dir, self.map_system, self.ui_manager, self.animation_manager)

        # Variables de estado de la aplicación
        self.guia_activo = False
        self.paso = 1
        self.max_pasos = 6
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None}
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

    def cargar_activos_sitio(self, texto_qr):
        sitio_id = texto_qr.strip().lower()
        path_sitio = os.path.join(self.base_dir, 'assets', 'sitios', sitio_id)
        
        if not os.path.exists(path_sitio):
            print(f"  [ERROR] No existe la carpeta: {path_sitio}")
            return False
        
        self.sitio_actual_id = sitio_id
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None, 'textos': {}, 'vaca_gif': None, 'iguana_gif': None, 'suelo_textura': None, 'porton': None}
        archivos = os.listdir(path_sitio)
        
        for i in range(1, self.max_pasos + 1):
            # Buscar avatar con prioridad al atuendo actual
            path_avatar = os.path.join(path_sitio, f"avatar_{i}.gif")
            if self.shop_system.atuendo_actual != "original":
                path_custom = os.path.join(self.base_dir, 'assets', 'outfits', self.shop_system.atuendo_actual, f"avatar_{i}.gif")
                if os.path.exists(path_custom):
                    path_avatar = path_custom
            
            if os.path.exists(path_avatar):
                self.activos['avatars'][i] = GifHandler(path_avatar)

            for f in archivos:
                if f.lower() == f"burbuja_{i}.gif":
                    self.activos['burbujas'][i] = GifHandler(os.path.join(path_sitio, f))
        
        if 'historica.png' in [f.lower() for f in archivos]:
            self.activos['foto_h'] = cv2.imread(os.path.join(path_sitio, 'historica.png'), cv2.IMREAD_UNCHANGED)

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
                    self.activos['mapa_mask'] = (combined - combined.min()) / diff
                else:
                    self.activos['mapa_mask'] = combined
            else:
                self.activos['mapa_mask'] = None
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
            if self.trivia_system.trivia_fase == 1:
                print("  [GAME] Iniciando desafío del Paso 5 (Parte 1)...")
                self.audio_manager.tts.decir(mensaje_extra + "podrias recordarme en que año se tomó la foto para avanzar")
            else:
                print("  [GAME] Iniciando desafío del Paso 5 (Parte 2)...")
                self.audio_manager.tts.decir(mensaje_extra + "¿quien tomo la foto?")
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
        """Inicia el proceso de transición hacia un nuevo paso."""
        self.proximo_paso = nuevo_paso
        self.proximo_mensaje = mensaje_extra
        self.animation_manager.start_transition()

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

        # NUEVO: Lógica de scroll con la rueda del mouse para la tienda
        if event == cv2.EVENT_MOUSEWHEEL:
            if self.shop_system.tienda_abierta:
                # flags > 0 es scroll hacia arriba, flags < 0 hacia abajo
                delta = 45 if flags > 0 else -45
                self.animation_manager.shop_scroll_y += delta
                # Calcular el límite del scroll basado en el contenido
                content_h = 100 + len(self.shop_system.outfits_disponibles) * 110
                min_scroll = min(0, h_f - content_h - 50)
                self.animation_manager.shop_scroll_y = max(min_scroll, min(0, self.animation_manager.shop_scroll_y))
        
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
                    self.animation_manager.add_button_pulse(x, y)
                    self.animation_manager.start_cinematic(sitio['nombre'])
                    # Iniciar ambiente después de un breve delay cinematográfico
                    pygame.time.set_timer(pygame.USEREVENT + 1, 1500)
                    if self.cargar_activos_sitio(sitio['id']):
                        self.audio_manager.iniciar_ambiente(sitio['id'])
                        self.map_system.modo_seleccion = False
                        self.guia_activo = True
                        self._cambiar_paso(1)
                    return

        if event == cv2.EVENT_LBUTTONDOWN and self.guia_activo:
            # --- LÓGICA DE NAVEGACIÓN (PRIORIDAD MÁXIMA PARA EVITAR BLOQUEOS) ---
            if y > h_f * 0.75:
                # Botón Atrás
                if x < w_f * 0.18: 
                    if self.paso > 1:
                        if self.paso == 5 and self.trivia_system.trivia_fase == 2:
                            self.trivia_system.trivia_fase = 1
                            self._cambiar_paso(5)
                        else:
                            self._cambiar_paso(self.paso - 1)
                    return
                # Botón Siguiente (Derecha)
                elif x > w_f * 0.7 and self.paso != 5:
                    if self.paso == self.max_pasos:
                        self.guia_activo = False
                        self.map_system.modo_seleccion = True
                        self.map_system.anim_mapa_progreso = 0.0
                    else:
                        self._cambiar_paso(self.paso + 1)
                    return
                # Botón Saltar
                elif 0.18 * w_f <= x < 0.38 * w_f and self.paso != 5:
                    self._cambiar_paso(self.max_pasos)
                    return

            # --- DETECCIÓN DE CLIC EN EL AVATAR ---
            if self.last_avatar_bbox:
                ax, ay, aw, ah = self.last_avatar_bbox
                if ax < x < ax + aw and ay < y < ay + ah:
                    av_handler = self.activos['avatars'].get(self.paso)
                    if av_handler:
                        av_handler.current_frame = 0 # Reiniciar animación del GIF
                        av_handler.spawn_timer = 0   # Reiniciar caída
                        av_handler.dust_done = False # Resetear polvo
                    
                    # También reiniciamos la burbuja de texto si existe
                    bu_handler = self.activos['burbujas'].get(self.paso)
                    if bu_handler:
                        bu_handler.current_frame = 0
                        
                        self.reproducir_texto_paso() # Volver a reproducir el audio
                    return # Consumir el evento de clic para evitar que se procese como un clic de botón


            # Botón Tienda (Arriba a la derecha, ajustado para el nuevo tamaño)
            if self.ui_manager.is_hovering_shop_button(x, y, w_f, h_f):
                self.shop_system.tienda_abierta = not self.shop_system.tienda_abierta
                return

            if self.shop_system.tienda_abierta:
                # Lógica de clics dentro del menú de la tienda
                panel_w = 300
                x1 = w_f - panel_w

                # NUEVO: Cerrar si se presiona el botón X (coordenadas: w_f - 40, 40)
                if np.sqrt((x - (w_f - 40))**2 + (y - 40)**2) < 20:
                    self.shop_system.tienda_abierta = False
                    return

                # Cerrar la tienda si se hace clic fuera del panel (a la izquierda de x1)
                if x < x1:
                    self.shop_system.tienda_abierta = False
                    return

                for i, outfit in enumerate(self.shop_system.outfits_disponibles):
                    y_box = 100 + i * 110 + self.animation_manager.shop_scroll_y
                    if x1 + 20 < x < w_f - 20 and y_box < y < y_box + 90:
                        if outfit["id"] in self.shop_system.outfits_comprados:
                            # Seleccionar atuendo ya comprado
                            self.shop_system.atuendo_actual = outfit["id"]
                            if self.sitio_actual_id: self.cargar_activos_sitio(self.sitio_actual_id)
                        elif self.shop_system.monedas >= outfit["precio"]:
                            # Comprar nuevo atuendo
                            self.shop_system.monedas -= outfit["precio"]
                            self.shop_system.outfits_comprados.append(outfit["id"])
                            self.shop_system.atuendo_actual = outfit["id"]
                            if self.sitio_actual_id: self.cargar_activos_sitio(self.sitio_actual_id)
                        return
                return

            # --- Lógica de Juego (Paso 5) ---
            if self.paso == 5 and self.trivia_system.trivia_fase == 1:
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

            elif self.paso == 5 and self.trivia_system.trivia_fase == 2:
                # (Ajustado para el nuevo UI Manager)
                if self.ui_manager.bg_opciones_2 is not None:
                    target_h_bg = h_f * 0.70 # Mantiene el ancho
                    base_scale_bg = target_h_bg / self.bg_opciones_2.shape[0]
                    w_bg_px = self.bg_opciones_2.shape[1] * base_scale_bg
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

            # Actualizar estado de los gestores
            self.animation_manager.update(self.mouse_x, self.mouse_y, show_leaves=self.guia_activo)
            
            # NUEVO: Sincronización del cambio de paso con el punto máximo del fundido (clímax de la transición)
            if (self.animation_manager.transition_active and 
                self.animation_manager.transition_timer == self.animation_manager.transition_duration // 2):
                self._ejecutar_cambio_real()

            self.map_system.update_qr_detection(frame, self.guia_activo)

            # Renderizar el frame usando el ARRenderer
            frame, self.last_avatar_bbox = self.ar_renderer.render(
                frame,
                self.guia_activo,
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
                self.shop_system.outfits_comprados,
                self.shop_system.atuendo_actual,
                self.trivia_system.trivia_fase,
                self.trivia_system.trivia_opciones,
                self.trivia_system.trivia_opciones_fase2,
                self.trivia_system.trivia_errores,
                self.trivia_system.trivia_acierto
            )
            cv2.imshow("VISOR_TURISMO_AR", frame) # Mostrar el frame final
            self.animation_manager.anim_frame += 1 # Incremento global para todas las animaciones
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1: break
            

        self.ar_renderer.release_camera() # Liberar la cámara a través del ARRenderer
        cv2.destroyAllWindows()