import cv2
import numpy as np
import os
import pytesseract
from utils import load_ui_asset, render_alfa, dibujar_sombra

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
        self.qr_anchor_points = None 
        self.qr_last_seen_points = None # Para suavizado de movimiento
        
        self.sitios_turisticos = [ # Lista de sitios turísticos con sus propiedades
            {"id": "sitio1", "nombre": "Ronda del Sinú", "x_rel": 0.40, "y_rel": 0.25, "calibrated_manually": True}, # Posición ajustada y sin texto específico
            {"id": "sitio2", "nombre": "Catedral", "x_rel": 0.55, "y_rel": 0.45}, # Catedral mantiene su posición
        ]
        self.icon_anims = [0.0] * len(self.sitios_turisticos) # Control de fade-in para iconos
        
        self.img_pin = load_ui_asset('pin.png', self.base_dir)
        self.img_pin_parque = load_ui_asset('pin_parque.png', self.base_dir)
        self.img_pin_iglesia = load_ui_asset('pin_iglesia.png', self.base_dir)

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

    def update_qr_detection(self, frame, guia_activo):
        """Detecta QR y actualiza el estado del mapa."""
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(frame)
        
        if points is not None and len(points) > 0:
            self.qr_anchor_points = points[0]
            self.qr_last_seen_points = points[0]
            self.qr_detectado_persistente = True
            # Si detectamos un nuevo QR y no hay nada activo, iniciamos animación
            if data and not guia_activo and not self.modo_seleccion:
                self.modo_seleccion = True
                self.anim_mapa_progreso = 0.0
                self.icon_anims = [0.0] * len(self.sitios_turisticos)
        else:
            self.qr_detectado_persistente = False

    def render_map_animation(self, frame, w_f, h_f, mouse_x, mouse_y, anim_frame, animation_manager):
        """Renderiza el mapa con la animación de apertura y los pines."""
        if self.modo_seleccion:
            # LÓGICA DE PERSISTENCIA: El mapa se abre de forma fluida hasta el final y persiste.
            self.anim_mapa_progreso = min(1.0, self.anim_mapa_progreso + 0.01) # Apertura fluida

            # RENDERIZADO DEL MAPA CON APERTURA DE PAPEL
            if self.img_mapa_general is not None and self.qr_last_seen_points is not None:
                h_m, w_m = self.img_mapa_general.shape[:2]
                
                # Easing Out Quartic para una transición muy fluida
                t = self.anim_mapa_progreso
                e_prog = 1 - (1 - t)**4 

                pts = self.qr_last_seen_points # TL, TR, BR, BL
                tl, tr, bl = pts[0], pts[1], pts[3]
                
                # Vectores de dirección basados en el QR
                vx = tr - tl
                vy = bl - tl
                cx, cy = np.mean(pts[:, 0]), np.mean(pts[:, 1])
                
                escala_mapa = 5.0
                
                # El papel se expande desde el centro de forma suave
                src_p = np.float32([[0, 0], [w_m, 0], [0, h_m], [w_m, h_m]])
                
                # Factor de expansión (tamaño actual determinado por e_prog)
                esc_actual = escala_mapa * e_prog
                
                dst_p = np.float32([
                    [cx + (-0.5 * esc_actual) * vx[0] + (-0.5 * esc_actual) * vy[0],
                     cy + (-0.5 * esc_actual) * vx[1] + (-0.5 * esc_actual) * vy[1]],
                    [cx + (0.5 * esc_actual) * vx[0] + (-0.5 * esc_actual) * vy[0],
                     cy + (0.5 * esc_actual) * vx[1] + (-0.5 * esc_actual) * vy[1]],
                    [cx + (-0.5 * esc_actual) * vx[0] + (0.5 * esc_actual) * vy[0],
                     cy + (-0.5 * esc_actual) * vx[1] + (0.5 * esc_actual) * vy[1]],
                    [cx + (0.5 * esc_actual) * vx[0] + (0.5 * esc_actual) * vy[0],
                     cy + (0.5 * esc_actual) * vx[1] + (0.5 * esc_actual) * vy[1]]
                ])

                self.mapa_matrix = cv2.getPerspectiveTransform(src_p, dst_p)
                mapa_warp = cv2.warpPerspective(self.img_mapa_general, self.mapa_matrix, (w_f, h_f), borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
                
                # Añadimos un desvanecimiento suave durante el crecimiento para mayor fluidez
                if e_prog < 1.0:
                    mapa_warp[:, :, 3] = (mapa_warp[:, :, 3] * e_prog).astype(np.uint8)
                
                # Simular textura de papel y sombra
                if e_prog > 0.1:
                    # Sombra proyectada debajo del mapa
                    shadow_offset_x = int(10 * e_prog)
                    shadow_offset_y = int(20 * e_prog)
                    shadow_pts = dst_p + np.array([[shadow_offset_x, shadow_offset_y]] * 4, dtype=np.float32)
                    cv2.fillConvexPoly(frame, shadow_pts.astype(int), (0, 0, 0), lineType=cv2.LINE_AA)
                    frame = cv2.GaussianBlur(frame, (5, 5), 0) # Suavizar la sombra

                    # Efecto de textura de papel (ruido sutil)
                    noise = np.random.randint(0, 20, mapa_warp[:, :, :3].shape, dtype=np.uint8)
                    mapa_warp[:,:,:3] = cv2.add(mapa_warp[:,:,:3], noise, dtype=cv2.CV_8U)

                frame = render_alfa(frame, mapa_warp, 0, 0, 1.0)

            # FASE: APARICIÓN SECUENCIAL DE ICONOS
            if self.anim_mapa_progreso >= 0.6 and self.mapa_matrix is not None:
                for i, sitio in enumerate(self.sitios_turisticos):
                    # Delay secuencial para cada icono
                    delay = i * 0.05
                    if self.anim_mapa_progreso > (0.6 + delay):
                        self.icon_anims[i] = min(1.0, self.icon_anims[i] + 0.1)
                    
                    alpha_icon = self.icon_anims[i]
                    if alpha_icon <= 0: continue

                    pt_src = np.array([[[sitio['x_rel'] * w_m, sitio['y_rel'] * h_m]]], dtype=np.float32)
                    pt_dst = cv2.perspectiveTransform(pt_src, self.mapa_matrix)
                    px, py = pt_dst[0][0]

                    float_y = np.sin(anim_frame * 0.12 + i) * 8
                    py_f = py + float_y - (20 * (1.0 - alpha_icon))

                    dist = np.sqrt((mouse_x - px)**2 + (mouse_y - py_f)**2)
                    esc_pin = 0.15 if dist < 40 else 0.10
                    
                    img_a_usar = self.img_pin
                    if sitio['id'] == 'sitio1' and self.img_pin_parque is not None:
                        img_a_usar = self.img_pin_parque
                    elif sitio['id'] == 'sitio2' and self.img_pin_iglesia is not None:
                        img_a_usar = self.img_pin_iglesia

                    if img_a_usar is not None:
                        # DIBUJAR SOMBRA EN EL MAPA
                        s_ratio = max(0.2, 1.0 - (abs(float_y) / 250))
                        dibujar_sombra(frame, px, py, int(25 * esc_pin * 10 * s_ratio), int(8 * esc_pin * 10 * s_ratio))

                        # Ajustar anclaje para iconos más pequeños
                        frame = render_alfa(frame, img_a_usar, (px/w_f) - 0.025, (py_f/h_f) - 0.06, esc_pin)
                        
                        # Partículas de brillo cerca de los pines
                        if dist < 40: # Solo si el mouse está cerca
                            animation_manager.add_pin_glow_particles(px, py_f)
                    
                    # Etiqueta del sitio
                    color_txt = (255, 255, 255) if dist < 40 else (200, 200, 200)
                    
                    if 'tx_rel' in sitio:
                        pt_t_src = np.array([[[sitio['tx_rel'] * w_m, sitio['ty_rel'] * h_m]]], dtype=np.float32)
                        pt_t_dst = cv2.perspectiveTransform(pt_t_src, self.mapa_matrix)
                        tx, ty = pt_t_dst[0][0]
                        pos_txt = (int(tx), int(ty + float_y))
                    else:
                        pos_txt = (int(px - 50), int(py_f + 10))
                        
                    # frame = dibujar_texto_utf8(frame, sitio['nombre'], pos_txt, 16, color_txt) # Desactivado para simplificar UI

            # cv2.putText(frame, "Selecciona un destino en el mapa", (int(w_f*0.25), 40), 0, 0.8, (255, 255, 255), 2) # Desactivado para simplificar UI
        return frame