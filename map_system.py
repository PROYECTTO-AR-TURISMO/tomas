import cv2
import numpy as np
import os
import pytesseract
from utils import load_ui_asset, render_alfa, dibujar_sombra, dibujar_texto_utf8

class MapSystem:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        
        self.img_mapa_general = load_ui_asset('mapa_monteria.png', self.base_dir)
        # Asegurar canal alfa para que el mapa pueda ser transparente en los bordes
        if self.img_mapa_general is not None and self.img_mapa_general.shape[2] == 3:
            self.img_mapa_general = cv2.cvtColor(self.img_mapa_general, cv2.COLOR_BGR2BGRA)
            
        self.qr_detectado_persistente = False
        self.modo_seleccion = False  # Ahora comenzamos escaneando el QR para "desbloquear" el mapa
        self.anim_mapa_progreso = 0.0 # 0.0 a 1.0 (animación de apertura)
        self.mapa_matrix = None # Guardará la perspectiva actual para los clics
        self.map_zoom_factor = 1.0 # Factor de escala para vista fija
        self.target_zoom = 1.0
        self.qr_anchor_points = None 
        self.qr_last_seen_points = None # Para suavizado de movimiento
        self.detector = cv2.QRCodeDetector()
        
        self.sitios_turisticos = [ # Lista de sitios turísticos con sus propiedades
            {"id": "sitio1", "nombre": "Ronda del Sinú", "x_rel": 0.40, "y_rel": 0.25, "calibrated_manually": True, "unlock_condition": None}, # Siempre desbloqueado
            {"id": "sitio_2", "nombre": "Catedral", "x_rel": 0.55, "y_rel": 0.45, "unlock_condition": "s1_completado"}, # Desbloqueado al completar sitio 1
            {"id": "sitio_3", "nombre": "Planchones", "x_rel": 0.18, "y_rel": 0.20, "unlock_condition": "s2_completado"}, # Desbloqueado al completar sitio 2
        ]
        self.progreso = {} # Para almacenar el estado de completado de los sitios
        self.icon_anims = [0.0] * len(self.sitios_turisticos) # Control de fade-in para iconos
        
        self.img_pin = load_ui_asset('pin.png', self.base_dir)
        self.img_pin_parque = load_ui_asset('pin_parque.png', self.base_dir)
        self.img_pin_iglesia = load_ui_asset('pin_iglesia.png', self.base_dir)
        self.img_pin_barco = load_ui_asset('pin_barco.png', self.base_dir) # Nuevo icono solicitado
        self.img_lock = load_ui_asset('lock.png', self.base_dir) # Icono de candado para sitios bloqueados

        # Validación de activos para ayudarte a debuguear
        if self.img_pin_parque is None: print("  [AVISO] No se encontró 'pin_parque.png' en assets/ui/")
        if self.img_pin_iglesia is None: print("  [AVISO] No se encontró 'pin_iglesia.png' en assets/ui/")
        if self.img_mapa_general is None: print("  [AVISO] No se encontró 'mapa_monteria.png' en assets/ui/")

        # Intentar auto-localizar los nombres en el mapa usando OCR para posicionar los pines
        self._calibrar_pines_por_ocr()

    def _calibrar_pines_por_ocr(self):
        """Intenta localizar las coordenadas de los sitios buscando el texto en la imagen del mapa."""
        if self.img_mapa_general is None: return
        print("  [SISTEMA] Escaneando mapa para localizar nombres de sitios...")
        try:
            # Convertir a escala de grises para mejorar la precisión del OCR
            gray = cv2.cvtColor(self.img_mapa_general, cv2.COLOR_BGR2GRAY)
            # Tesseract busca el texto y devuelve las cajas delimitadoras
            dict_ocr = pytesseract.image_to_data(gray, lang='spa', output_type=pytesseract.Output.DICT)
            
            h_m, w_m = gray.shape[:2]
            
            for i in range(len(dict_ocr['text'])):
                palabra = dict_ocr['text'][i].lower().strip()
                if len(palabra) < 4: continue # Ignorar palabras muy cortas
                
                for sitio in self.sitios_turisticos:
                    # Saltar sitios que han sido calibrados manualmente
                    if sitio.get("calibrated_manually", False):
                        continue
                    if palabra in sitio['nombre'].lower():
                        # Calculamos el centro relativo basado en el hallazgo del OCR
                        sitio['x_rel'] = (dict_ocr['left'][i] + dict_ocr['width'][i] / 2) / w_m
                        sitio['y_rel'] = (dict_ocr['top'][i] + dict_ocr['height'][i] / 2) / h_m
                        print(f"  [MAPA] Detectado '{sitio['nombre']}' en mapa: x={sitio['x_rel']:.2f}, y={sitio['y_rel']:.2f}")
        except Exception as e:
            print(f"  [AVISO] No se pudo auto-calibrar el mapa por OCR: {e}")

    def update_progreso(self, progreso_dict):
        """Actualiza el diccionario de progreso de los sitios."""
        self.progreso = progreso_dict

    def update_qr_detection(self, frame, guia_activo):
        """Detecta QR y actualiza el estado del mapa de forma robusta."""
        data, points = "", None
        
        try:
            # Separamos detección de decodificación para validar los puntos
            # y evitar el crash interno de OpenCV cuando el área detectada es 0
            hay_qr, points_candidate = self.detector.detect(frame)
            
            if hay_qr and points_candidate is not None:
                # Solo procedemos si el área del contorno es válida (> 0) para evitar el crash
                if cv2.contourArea(points_candidate) > 0:
                    data, _ = self.detector.decode(frame, points_candidate)
                    points = points_candidate
        except cv2.error:
            # Silenciamos errores internos de la librería para mantener la estabilidad
            data, points = "", None

        if points is not None and len(points) > 0:
            self.qr_anchor_points = points[0]
            
            # SUAVIZADO DE ANCLAJE: Aplicamos LERP (Linear Interpolation)
            if self.qr_last_seen_points is None:
                self.qr_last_seen_points = points[0]
            else:
                alpha = 0.25 # Factor de suavizado (más bajo = más estable pero más lento)
                self.qr_last_seen_points = self.qr_last_seen_points * (1 - alpha) + points[0] * alpha

            self.qr_detectado_persistente = True
            # Si detectamos un nuevo QR y no hay nada activo, iniciamos animación
            if data and not guia_activo and not self.modo_seleccion:
                self.modo_seleccion = True
                self.anim_mapa_progreso = 0.0
                self.icon_anims = [0.0] * len(self.sitios_turisticos)
        elif not self.modo_seleccion: # Permitir que el mapa sea interactivo aunque se pierda el QR si ya se abrió
            self.qr_detectado_persistente = False

    def render_map_animation(self, frame, w_f, h_f, mouse_x, mouse_y, anim_frame, animation_manager, progreso):
        """Renderiza el mapa con comportamiento dual: AR con QR al inicio, 2D estable con zoom al completar."""
        ronda_completada = progreso.get('s1', False)
        s2_completado = progreso.get('s2', False)

        if self.modo_seleccion:
            # Control de animación de aparición
            if self.qr_detectado_persistente:
                self.anim_mapa_progreso = min(1.0, self.anim_mapa_progreso + 0.05)
            elif ronda_completada:
                self.anim_mapa_progreso = 1.0
            else:
                self.anim_mapa_progreso = max(0.0, self.anim_mapa_progreso - 0.1)

            if self.anim_mapa_progreso <= 0 or self.img_mapa_general is None:
                return frame

            h_m, w_m = self.img_mapa_general.shape[:2]

            if ronda_completada:
                # --- MODO 2D ESTABLE CON ZOOM (NUEVO) ---
                self.map_zoom_factor += (self.target_zoom - self.map_zoom_factor) * 0.15
                current_scale = self.map_zoom_factor * self.anim_mapa_progreso
                
                base_w_scale = (w_f * 0.85) / w_m
                base_h_scale = (h_f * 0.85) / h_m
                final_base_scale = min(base_w_scale, base_h_scale) * current_scale
                
                target_w, target_h = int(w_m * final_base_scale), int(h_m * final_base_scale)
                x_off, y_off = (w_f - target_w) // 2, (h_f - target_h) // 2

                map_render = cv2.resize(self.img_mapa_general, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                if self.anim_mapa_progreso < 1.0 and map_render.shape[2] == 4:
                    map_render[:, :, 3] = (map_render[:, :, 3] * self.anim_mapa_progreso).astype(np.uint8)
                
                frame = render_alfa(frame, map_render, x_off/w_f, y_off/h_f, 1.0)
                self.mapa_matrix = np.float32([[final_base_scale, 0, x_off], [0, final_base_scale, y_off], [0, 0, 1]])
            else:
                # --- MODO PERSPECTIVA QR (ORIGINAL) ---
                pts_base = self.qr_last_seen_points
                if pts_base is None: return frame
                
                e_prog = 1 - (1 - self.anim_mapa_progreso)**4 
                src_p = np.float32([[0, 0], [w_m, 0], [0, h_m], [w_m, h_m]])
                
                tl, tr, bl = pts_base[0], pts_base[1], pts_base[3]
                vx, vy = tr - tl, bl - tl
                cx, cy = np.mean(pts_base[:, 0]), np.mean(pts_base[:, 1])
                esc_actual = 5.0 * e_prog
                
                dst_p = np.float32([
                    [cx + (-0.5 * esc_actual) * vx[0] + (-0.5 * esc_actual) * vy[0], cy + (-0.5 * esc_actual) * vx[1] + (-0.5 * esc_actual) * vy[1]],
                    [cx + (0.5 * esc_actual) * vx[0] + (-0.5 * esc_actual) * vy[0], cy + (0.5 * esc_actual) * vx[1] + (-0.5 * esc_actual) * vy[1]],
                    [cx + (-0.5 * esc_actual) * vx[0] + (0.5 * esc_actual) * vy[0], cy + (-0.5 * esc_actual) * vx[1] + (0.5 * esc_actual) * vy[1]],
                    [cx + (0.5 * esc_actual) * vx[0] + (0.5 * esc_actual) * vy[0], cy + (0.5 * esc_actual) * vx[1] + (0.5 * esc_actual) * vy[1]]
                ])
                
                self.mapa_matrix = cv2.getPerspectiveTransform(src_p, dst_p)
                mapa_warp = cv2.warpPerspective(self.img_mapa_general, self.mapa_matrix, (w_f, h_f), borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
                
                if e_prog < 1.0: mapa_warp[:, :, 3] = (mapa_warp[:, :, 3] * e_prog).astype(np.uint8)
                
                # Sombra y ruido (Estética de papel)
                shadow_pts = dst_p + np.array([[10, 20]] * 4, dtype=np.float32)
                dibujar_sombra(frame, np.mean(shadow_pts[:,0]), np.mean(shadow_pts[:,1]), int(w_f*0.2), int(h_f*0.05))
                frame = render_alfa(frame, mapa_warp, 0, 0, 1.0)
                current_scale = 1.0

            # --- PINES Y LÍNEAS ---
            if self.anim_mapa_progreso > 0.6 and self.mapa_matrix is not None and self.progreso:
                # Almacenar puntos de los sitios para dibujar líneas
                sitio_coords = {}
                for sitio in self.sitios_turisticos:
                    pt_src = np.array([[[sitio['x_rel'] * w_m, sitio['y_rel'] * h_m]]], dtype=np.float32)
                    pt_dst = cv2.perspectiveTransform(pt_src, self.mapa_matrix)[0][0]
                    sitio_coords[sitio['id']] = pt_dst

                # Dibujar líneas entre sitios (Gris bloqueado, Verde desbloqueado)
                if 'sitio1' in sitio_coords and 'sitio_2' in sitio_coords:
                    color_s1_s2 = (0, 255, 0) if self.progreso.get('s1_completado', False) else (150, 150, 150)
                    cv2.line(frame, tuple(sitio_coords['sitio1'].astype(int)), tuple(sitio_coords['sitio_2'].astype(int)), color_s1_s2, 2, cv2.LINE_AA)
                
                if 'sitio_2' in sitio_coords and 'sitio_3' in sitio_coords:
                    color_s2_s3 = (0, 255, 0) if self.progreso.get('s2_completado', False) else (150, 150, 150)
                    cv2.line(frame, tuple(sitio_coords['sitio_2'].astype(int)), tuple(sitio_coords['sitio_3'].astype(int)), color_s2_s3, 2, cv2.LINE_AA)

                for i, sitio in enumerate(self.sitios_turisticos):
                    # Lógica de bloqueo progresivo
                    esta_bloqueado = False
                    if sitio['unlock_condition'] is not None:
                        if not self.progreso.get(sitio['unlock_condition'], False):
                            esta_bloqueado = True
                    
                    # El sitio 1 siempre está desbloqueado
                    if sitio['id'] == 'sitio1':
                        esta_bloqueado = False

                    if self.anim_mapa_progreso > (0.6 + i * 0.05):
                        self.icon_anims[i] = min(1.0, self.icon_anims[i] + 0.1)

                    alpha_icon = self.icon_anims[i] * (0.4 if esta_bloqueado else 1.0)
                    if alpha_icon <= 0: continue

                    pt_src = np.array([[[sitio['x_rel'] * w_m, sitio['y_rel'] * h_m]]], dtype=np.float32)
                    pt_dst = cv2.perspectiveTransform(pt_src, self.mapa_matrix)
                    px, py = pt_dst[0][0]

                    float_y = np.sin(anim_frame * 0.12 + i) * 8
                    py_f = py + float_y - (20 * (1.0 - alpha_icon))

                    dist = np.sqrt((mouse_x - px)**2 + (mouse_y - py_f)**2)
                    esc_pin = (0.15 if dist < 40 else 0.10) * current_scale
                    
                    if sitio['id'] == 'sitio1': img_a_usar = self.img_pin_parque
                    elif sitio['id'] == 'sitio_2': img_a_usar = self.img_pin_iglesia
                    else: img_a_usar = self.img_pin_barco

                    if esta_bloqueado and img_a_usar is not None:
                        # Convertir el icono a escala de grises para mostrarlo "sin color"
                        b, g, r, a = cv2.split(img_a_usar)
                        gray = cv2.cvtColor(cv2.merge([b, g, r]), cv2.COLOR_BGR2GRAY)
                        img_a_usar = cv2.merge([gray, gray, gray, a])

                    dibujar_sombra(frame, px, py, int(25 * esc_pin * 10), int(8 * esc_pin * 10))
                    frame = render_alfa(frame, img_a_usar, (px/w_f) - (0.2*esc_pin), (py_f/h_f) - (0.5*esc_pin), esc_pin)
                    
                    # Dibujar candado si está bloqueado
                    if esta_bloqueado and self.img_lock is not None:
                        esc_lock = esc_pin * 0.4
                        frame = render_alfa(frame, self.img_lock, (px/w_f), (py_f/h_f) - (0.45*esc_pin), esc_lock)
                    
                    txt = "[BLOQUEADO]" if esta_bloqueado else sitio['nombre']
                    frame = dibujar_texto_utf8(frame, txt, (int(px - 50 * current_scale), int(py_f + 15 * current_scale)), int(14 * current_scale), (255,255,255))

        return frame