import cv2
import numpy as np
from utils import render_alfa, dibujar_texto_utf8, load_ui_asset, draw_rounded_rect, apply_glassmorphism

class UIManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir

        # Cargar botones de interfaz
        self.btn_sig = load_ui_asset('next.png', self.base_dir)
        self.btn_salt = load_ui_asset('skip.png', self.base_dir)
        self.btn_back = load_ui_asset('back.png', self.base_dir)
        self.btn_input = load_ui_asset('input_box.png', self.base_dir)
        self.img_pregunta = load_ui_asset('pregunta.png', self.base_dir)
        self.avatar_5 = load_ui_asset('avatar_5.png', self.base_dir)
        self.bg_opciones_1 = load_ui_asset('fondo_opciones.png', self.base_dir)
        self.bg_opciones_2 = load_ui_asset('fondo_opciones_2.png', self.base_dir)
        self.img_escaner = load_ui_asset('fondo_escaner.png', self.base_dir)

        # Igualar el tamaño del botón 'saltar' y 'atrás' al botón 'siguiente' para mantener consistencia
        if self.btn_sig is not None:
            h, w = self.btn_sig.shape[:2]
            if self.btn_salt is not None:
                self.btn_salt = cv2.resize(self.btn_salt, (w, h), interpolation=cv2.INTER_AREA)
            if self.btn_back is not None:
                self.btn_back = cv2.resize(self.btn_back, (w, h), interpolation=cv2.INTER_AREA)

        # Cargar icono de tienda y moneda (desde ShopSystem)
        self.btn_tienda = load_ui_asset('shop.png', self.base_dir)
        self.btn_moneda = load_ui_asset('coin.png', self.base_dir)

    def draw_hud(self, frame, w_f, h_f, paso, max_pasos, monedas, mouse_x, mouse_y, animation_manager):
        # Dibujar Viñeta Cinematográfica (Bordes oscuros)
        self._draw_vignette(frame, w_f, h_f)
        
        # Barra superior con glassmorphism
        frame = apply_glassmorphism(frame, 0, 0, w_f, int(h_f * 0.08), blur_strength=25, alpha=0.2, border_color=(200, 200, 200), border_thickness=1, border_radius=0)

        # Dibujar contador de monedas (cápsula elegante)
        coin_x1, coin_y1 = int(w_f * 0.02), int(h_f * 0.015)
        coin_x2, coin_y2 = int(w_f * 0.15), int(h_f * 0.065)
        draw_rounded_rect(frame, (coin_x1, coin_y1), (coin_x2, coin_y2), (50, 50, 50), 20, -1, alpha=0.4) # Fondo
        draw_rounded_rect(frame, (coin_x1, coin_y1), (coin_x2, coin_y2), (150, 150, 150), 20, 2) # Borde

        if self.btn_moneda is not None:
            frame = render_alfa(frame, self.btn_moneda, (coin_x1 + 5)/w_f, (coin_y1 + 5)/h_f, 0.025)
            frame = dibujar_texto_utf8(frame, str(monedas), (coin_x1 + 50, coin_y1 + 10), 20, (255, 255, 255))
        else:
            frame = dibujar_texto_utf8(frame, f"MONEDAS: {monedas}", (coin_x1 + 10, coin_y1 + 10), 20, (255, 255, 255))

        # Barra de progreso visual (reemplaza "PASO X / Y")
        self._draw_progress_bar(frame, w_f, h_f, paso, max_pasos)

        # Botón Tienda
        hover_tienda = self.is_hovering_shop_button(mouse_x, mouse_y, w_f, h_f)
        animation_manager.hover_tienda_anim = min(1.0, animation_manager.hover_tienda_anim + 0.3) if hover_tienda else max(0.0, animation_manager.hover_tienda_anim - 0.3)

        if self.btn_tienda is not None:
            target_h_tienda = h_f * 0.06 # Más pequeño para la esquina
            base_scale_tienda = target_h_tienda / self.btn_tienda.shape[0]
            
            y_tienda = 0.01 + (0.005 * animation_manager.hover_tienda_anim) # Ligeramente más abajo al hacer hover
            x_tienda = 0.92 - (0.005 * animation_manager.hover_tienda_anim) # Ligeramente a la izquierda al hacer hover
            esc_tienda = base_scale_tienda + (0.01 * animation_manager.hover_tienda_anim)
            frame = render_alfa(frame, self.btn_tienda, x_tienda, y_tienda, esc_tienda)
        else:
            color_tienda = (0, 140, 255) # Fallback
            cv2.rectangle(frame, (int(w_f*0.9), int(h_f*0.01)), (int(w_f*0.98), int(h_f*0.07)), color_tienda, -1)
            cv2.putText(frame, "SHOP", (int(w_f*0.92), int(h_f*0.05)), 0, 0.4, (255, 255, 255), 1)

        # Botón Salir App (X Roja en círculo oscuro)
        exit_x, exit_y = int(w_f * 0.98), int(h_f * 0.04)
        exit_r = 15
        is_hover_exit = np.sqrt((mouse_x - exit_x)**2 + (mouse_y - exit_y)**2) < exit_r
        exit_color = (0, 0, 180) if is_hover_exit else (40, 40, 40)
        cv2.circle(frame, (exit_x, exit_y), exit_r, exit_color, -1)
        cv2.circle(frame, (exit_x, exit_y), exit_r, (255, 255, 255), 1)
        d = 5
        cv2.line(frame, (exit_x - d, exit_y - d), (exit_x + d, exit_y + d), (255, 255, 255), 2)
        cv2.line(frame, (exit_x + d, exit_y - d), (exit_x - d, exit_y + d), (255, 255, 255), 2)

        # Dibujar pulsos de feedback
        for x, y, r, a in animation_manager.button_pulses:
            overlay = frame.copy()
            cv2.circle(overlay, (int(x), int(y)), int(r), (255, 255, 255), 2)
            cv2.addWeighted(overlay, a/255.0, frame, 1.0 - a/255.0, 0, frame)

        return frame

    def _draw_vignette(self, frame, w, h):
        """Añade un overlay de bordes oscuros para profundidad."""
        overlay = frame.copy()
        cv2.rectangle(overlay, (0,0), (w, h), (0,0,0), -1)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (w//2, h//2), (int(w*0.8), int(h*0.8)), 0, 0, 360, 255, -1)
        mask = cv2.GaussianBlur(mask, (int(w*0.4)|1, int(w*0.4)|1), 0)
        mask_inv = cv2.bitwise_not(mask)
        frame[:] = cv2.addWeighted(frame, 1.0, cv2.bitwise_and(overlay, overlay, mask=mask_inv), 0.4, 0)

    def _draw_progress_bar(self, frame, w_f, h_f, paso, max_pasos):
        bar_y = int(h_f * 0.03)
        bar_height = int(h_f * 0.02)
        bar_width = int(w_f * 0.3)
        bar_x = int(w_f * 0.5 - bar_width / 2)

        # Fondo de la barra
        draw_rounded_rect(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (50, 50, 50), 10, -1, alpha=0.4)
        draw_rounded_rect(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (150, 150, 150), 10, 1)

        # Progreso
        progress_width = int(bar_width * (paso / max_pasos))
        draw_rounded_rect(frame, (bar_x, bar_y), (bar_x + progress_width, bar_y + bar_height), (0, 200, 255), 10, -1, alpha=0.6)

        # Nodos
        for i in range(max_pasos):
            node_x = bar_x + int(bar_width * (i / (max_pasos - 1))) if max_pasos > 1 else bar_x + bar_width // 2
            node_color = (0, 255, 255) if i < paso else (100, 100, 100)
            node_radius = 8 if i < paso else 6
            cv2.circle(frame, (node_x, bar_y + bar_height // 2), node_radius, node_color, -1)
            cv2.circle(frame, (node_x, bar_y + bar_height // 2), node_radius + 2, (200, 200, 200), 1)

        # Texto del paso actual
        frame = dibujar_texto_utf8(frame, f"PASO {paso}/{max_pasos}", (bar_x + bar_width + 20, bar_y + 5), 18, (255, 255, 255))

    def draw_navigation_buttons(self, frame, w_f, h_f, paso, max_pasos, mouse_x, mouse_y, animation_manager):
        # LÓGICA DE INTERACTIVIDAD DE BOTONES
        hover_sig = mouse_x > w_f * 0.7 and mouse_y > h_f * 0.75
        hover_back = mouse_x < w_f * 0.18 and mouse_y > h_f * 0.75
        hover_salt = 0.18 * w_f <= mouse_x < 0.38 * w_f and mouse_y > h_f * 0.75

        # Suavizado de la animación (incremento/decremento gradual)
        animation_manager.hover_sig_anim = min(1.0, animation_manager.hover_sig_anim + 0.3) if hover_sig else max(0.0, animation_manager.hover_sig_anim - 0.3)
        animation_manager.hover_back_anim = min(1.0, animation_manager.hover_back_anim + 0.3) if hover_back else max(0.0, animation_manager.hover_back_anim - 0.3)
        animation_manager.hover_salt_anim = min(1.0, animation_manager.hover_salt_anim + 0.3) if hover_salt else max(0.0, animation_manager.hover_salt_anim - 0.3)

        # Aplicar efecto de "levante" y escalar dinámicamente según la pantalla
        target_h_nav = h_f * 0.16 # 16% de la altura de la pantalla (botones más grandes)

        if self.btn_sig is not None and paso != 5:
            base_scale = target_h_nav / self.btn_sig.shape[0]
            y_btn = 0.8 - (0.03 * animation_manager.hover_sig_anim)
            esc_btn = base_scale + (0.02 * animation_manager.hover_sig_anim)
            frame = render_alfa(frame, self.btn_sig, 0.75, y_btn, esc_btn)

        if self.btn_back is not None:
            y_btn = 0.8 - (0.03 * animation_manager.hover_back_anim)
            esc_btn = 0.18 + (0.02 * animation_manager.hover_back_anim)
            frame = render_alfa(frame, self.btn_back, 0.05, y_btn, esc_btn)

        if self.btn_salt is not None and paso != 5:
            base_scale = (target_h_nav / self.btn_salt.shape[0]) * 1.25
            y_btn = 0.78 - (0.03 * animation_manager.hover_salt_anim)
            esc_btn = base_scale + (0.02 * animation_manager.hover_salt_anim)
            frame = render_alfa(frame, self.btn_salt, 0.19, y_btn, esc_btn)
        
        return frame

    def draw_shop_menu(self, frame, w_f, h_f, outfits_disponibles, outfits_comprados, atuendo_actual, animation_manager, mouse_x, mouse_y, tienda_abierta, monedas):
        # Lógica de slide del panel desde la derecha
        if tienda_abierta:
            animation_manager.shop_panel_prog = min(1.0, animation_manager.shop_panel_prog + 0.1)
        else:
            animation_manager.shop_panel_prog = max(0.0, animation_manager.shop_panel_prog - 0.1)
            
        if animation_manager.shop_panel_prog <= 0:
            return frame
        
        panel_w = 300
        offset_x = int(panel_w * (1.0 - animation_manager.shop_panel_prog))
        x1, y1 = w_f - panel_w + offset_x, 0
        
        # Fondo de panel Glassmorphism
        frame = apply_glassmorphism(frame, x1, y1, w_f, h_f, blur_strength=30, alpha=0.4, border_radius=0)
        frame = dibujar_texto_utf8(frame, "TIENDA PREMIUM", (x1 + 40, 40), 22, (255, 255, 255))

        # Botón Cerrar (X) visible con feedback
        close_x, close_y = w_f - 40 + offset_x, 40
        close_r = 15
        is_hover_close = np.sqrt((mouse_x - close_x)**2 + (mouse_y - close_y)**2) < close_r
        
        # Color del botón (cambia a rojo suave en hover para destacar)
        btn_color = (60, 60, 220) if is_hover_close else (80, 80, 80)
        cv2.circle(frame, (close_x, close_y), close_r, btn_color, -1)
        cv2.circle(frame, (close_x, close_y), close_r, (255, 255, 255), 2)
        # Dibujar la X estilizada con líneas blancas
        d = 6
        cv2.line(frame, (close_x - d, close_y - d), (close_x + d, close_y + d), (255, 255, 255), 2)
        cv2.line(frame, (close_x + d, close_y - d), (close_x - d, close_y + d), (255, 255, 255), 2)

        for i, outfit in enumerate(outfits_disponibles):
            y_box = 100 + i * 110 + animation_manager.shop_scroll_y
            is_hover = x1 + 20 < mouse_x < w_f - 20 and y_box < mouse_y < y_box + 100
            
            # Optimización: No dibujar si el recuadro está fuera de la pantalla
            if y_box + 100 < 0 or y_box > h_f: continue

            # Tarjeta de producto moderna
            card_color = (80, 80, 80) if not is_hover else (120, 100, 60)
            draw_rounded_rect(frame, (x1 + 20, y_box), (w_f - 20, y_box + 90), card_color, 15, -1, alpha=0.6)
            
            comprado = outfit["id"] in outfits_comprados
            
            if outfit["id"] == atuendo_actual:
                status = "[PUESTO]"
                price_color = (0, 255, 0) # Green
            elif comprado:
                status = "[COMPRADO]"
                price_color = (0, 255, 0) # Green
            else:
                status = f"${outfit['precio']}"
                price_color = (0, 255, 0) if monedas >= outfit["precio"] else (0, 0, 255) # Green if enough, Red if not
            
            frame = dibujar_texto_utf8(frame, outfit["nombre"], (x1 + 40, y_box + 15), 18, (255, 255, 255))
            frame = dibujar_texto_utf8(frame, status, (x1 + 40, y_box + 45), 16, price_color)

        return frame

    def draw_trivia_phase1(self, frame, w_f, h_f, trivia_opciones, trivia_errores, trivia_acierto, mouse_x, mouse_y):
        # 1. Imagen de fondo (Alineada a la derecha, más pequeña)
        if self.bg_opciones_1 is not None:
            target_h_bg = h_f * 0.65
            base_scale_bg = target_h_bg / self.bg_opciones_1.shape[0]
            w_bg_px = self.bg_opciones_1.shape[1] * base_scale_bg
            x_porc_bg = (w_f - w_bg_px - (w_f * 0.02)) / w_f
            
            frame = render_alfa(frame, self.bg_opciones_1, x_porc_bg, 0.15, base_scale_bg)
            
            x_img, y_img = w_f * x_porc_bg, h_f * 0.15
            w_img, h_img = w_bg_px, target_h_bg
        else:
            x_img, y_img, w_img, h_img = w_f * 0.35, h_f * 0.1, w_f * 0.6, h_f * 0.8

        # 2. Imagen del avatar (Izquierda)
        if self.avatar_5 is not None:
            frame = render_alfa(frame, self.avatar_5, 0.02, 0.20, 0.6)
        
        # 3. Lógica de renderizado de las casillas en el lado derecho del mapa
        for i, anio in enumerate(trivia_opciones):
            x1 = int(x_img + w_img * 0.69)
            x2 = int(x_img + w_img * 0.92)
            y1_base = int(y_img + h_img * (0.31 + i * 0.15))
            y2_base = int(y1_base + h_img * 0.09)
            
            hover_op = x1 < mouse_x < x2 and y1_base < mouse_y < y2_base
            
            overlay = frame.copy()
            draw_rect = False
            
            if anio in trivia_errores:
                cv2.rectangle(overlay, (x1, y1_base), (x2, y2_base), (0, 0, 255), -1) # Rojo
                draw_rect = True
            elif anio == trivia_acierto:
                cv2.rectangle(overlay, (x1, y1_base), (x2, y2_base), (0, 255, 0), -1) # Verde
                draw_rect = True
            elif hover_op:
                cv2.rectangle(overlay, (x1, y1_base), (x2, y2_base), (255, 255, 255), -1) # Hover blanco
                draw_rect = True
                
            if draw_rect:
                cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)
                
            texto_anio = str(anio)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.0
            thickness = 2
            text_size, _ = cv2.getTextSize(texto_anio, font, font_scale, thickness)
            text_w, text_h = text_size
            
            x_text = x1 + ((x2 - x1) - text_w) // 2
            y_text = y1_base + ((y2_base - y1_base) + text_h) // 2
            
            cv2.putText(frame, texto_anio, (x_text, y_text), font, font_scale, (0, 0, 0), thickness)
        return frame

    def draw_trivia_phase2(self, frame, w_f, h_f, trivia_opciones_fase2, trivia_errores, trivia_acierto, mouse_x, mouse_y, animation_manager):
        if self.img_pregunta is not None:
            scale_pregunta = 0.55
            w_preg_px = self.img_pregunta.shape[1] * scale_pregunta
            x_porc_preg = (w_f - w_preg_px) / 2 / w_f
            frame = render_alfa(frame, self.img_pregunta, x_porc_preg, 0.02, scale_pregunta)
            text_x = int(w_f * x_porc_preg + w_preg_px * 0.12)
            text_y = int(h_f * 0.02 + self.img_pregunta.shape[0] * scale_pregunta * 0.58)
            
            frame = dibujar_texto_utf8(frame, "¿Quien tomó esta foto?", (text_x, text_y), 24, (0, 0, 0))
        else:
            frame = dibujar_texto_utf8(frame, "¿Quien tomó esta foto?", (int(w_f*0.35), int(h_f*0.10)), 26, (0, 0, 0))
        
        if self.bg_opciones_2 is not None:
            target_h_bg = h_f * 0.70
            base_scale_bg = target_h_bg / self.bg_opciones_2.shape[0]
            w_bg_px = self.bg_opciones_2.shape[1] * base_scale_bg
            x_porc_bg = (w_f - w_bg_px) / 2 / w_f
            
            frame = render_alfa(frame, self.bg_opciones_2, x_porc_bg, 0.35, base_scale_bg)
            
            x_img, y_img = w_f * x_porc_bg, h_f * 0.35
            w_img, h_img = w_bg_px, target_h_bg
        else:
            x_img, y_img, w_img, h_img = w_f * 0.20, h_f * 0.35, w_f * 0.60, h_f * 0.70

        for i, nombre in enumerate(trivia_opciones_fase2):
            x1 = int(x_img + w_img * 0.15)
            x2 = int(x_img + w_img * 0.85)
            y1_base = int(y_img + h_img * (0.19 + i * 0.185))
            y2_base = int(y1_base + h_img * 0.10)
            
            hover_op = x1 < mouse_x < x2 and y1_base < mouse_y < y2_base
            
            animation_manager.hover_trivia_anims_2[i] = min(1.0, animation_manager.hover_trivia_anims_2[i] + 0.3) if hover_op else max(0.0, animation_manager.hover_trivia_anims_2[i] - 0.3)
            y_offset = int(h_f * 0.015 * animation_manager.hover_trivia_anims_2[i])
            
            y1_anim = y1_base - y_offset
            y2_anim = y2_base - y_offset
            
            overlay = frame.copy()
            draw_rect = False
            
            if nombre in trivia_errores:
                cv2.rectangle(overlay, (x1, y1_anim), (x2, y2_anim), (0, 0, 255), -1) # Rojo
                draw_rect = True
            elif nombre == trivia_acierto:
                cv2.rectangle(overlay, (x1, y1_anim), (x2, y2_anim), (0, 255, 0), -1) # Verde
                draw_rect = True
                
            if draw_rect:
                cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)
                
            longitud_estimada = len(nombre) * 6
            x_text = x1 + int(((x2 - x1) - longitud_estimada) / 2)
            y_text = y1_anim + int((y2_anim - y1_anim) * 0.50) 
            frame = dibujar_texto_utf8(frame, nombre, (x_text, y_text), 15, (0, 0, 0))
        return frame

    def is_hovering_shop_button(self, mouse_x, mouse_y, w_f, h_f):
        return w_f * 0.85 < mouse_x < w_f * 0.98 and h_f * 0.01 < mouse_y < h_f * 0.15