import cv2
import numpy as np
from utils import render_alfa, dibujar_texto_utf8, dibujar_sombra, apply_glassmorphism

class ARRenderer:
    def __init__(self, base_dir, map_system, ui_manager, animation_manager):
        self.base_dir = base_dir
        self.map_system = map_system
        self.ui_manager = ui_manager
        self.animation_manager = animation_manager

        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print("Error: No se pudo abrir la cámara.")
            exit()

    def render(self, frame, guia_activo, paso, max_pasos, activos, animales_stampida, mouse_x, mouse_y, last_avatar_bbox, monedas, tienda_abierta, outfits_disponibles, outfits_comprados, atuendo_actual, trivia_fase, trivia_opciones, trivia_opciones_fase2, trivia_errores, trivia_acierto):
        h_f, w_f, _ = frame.shape

        # --- EFECTO CINEMÁTICO DE ZOOM Y NOMBRE ---
        if self.animation_manager.cinematic_prog > 0:
            prog = self.animation_manager.cinematic_prog
            # Zoom suave
            zoom = 1.0 + (prog * 0.1)
            M = cv2.getRotationMatrix2D((w_f/2, h_f/2), 0, zoom)
            frame = cv2.warpAffine(frame, M, (w_f, h_f))
            # Oscurecer fondo
            overlay = frame.copy()
            cv2.rectangle(overlay, (0,0), (w_f, h_f), (0,0,0), -1)
            frame = cv2.addWeighted(overlay, prog * 0.5, frame, 1.0 - (prog * 0.5), 0)
            # Nombre del lugar
            # Posicionado debajo del HUD de monedas (aprox y=0.10) y más pequeño (tamaño 25)
            frame = dibujar_texto_utf8(frame, self.animation_manager.cinematic_name, (int(w_f*0.02), int(h_f*0.10)), 25, (255,255,255))

        # Aplicar desenfoque global si hay una transición activa
        if self.animation_manager.transition_active and self.animation_manager.blur_amount > 0:
            # El tamaño del kernel (ksize) debe ser impar y mayor que cero para OpenCV
            ksize = self.animation_manager.blur_amount
            if ksize % 2 == 0: ksize += 1
            frame = cv2.GaussianBlur(frame, (ksize, ksize), 0)

        if self.map_system.modo_seleccion:
            frame = self.map_system.render_map_animation(frame, w_f, h_f, mouse_x, mouse_y, self.animation_manager.anim_frame, self.animation_manager)
            # Texto "Selecciona un destino"
            text_x = int(w_f * 0.5 - cv2.getTextSize("Selecciona un destino en el mapa", cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0][0] / 2)
            apply_glassmorphism(frame, text_x - 20, 20, text_x + cv2.getTextSize("Selecciona un destino en el mapa", cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0][0] + 20, 60, blur_strength=15, alpha=0.3, border_radius=10)
            frame = dibujar_texto_utf8(frame, "Selecciona un destino en el mapa", (text_x, 30), 20, (255, 255, 255))
            last_avatar_bbox = None # No hay avatar visible en modo selección
        elif not guia_activo:
            if self.ui_manager.img_escaner is not None:
                img_full = cv2.resize(self.ui_manager.img_escaner, (w_f, h_f), interpolation=cv2.INTER_AREA)
                frame = render_alfa(frame, img_full, 0.0, 0.0, 1.0)
            
            text_x = int(w_f * 0.5 - cv2.getTextSize("ESCANEE QR", cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0][0] / 2)
            apply_glassmorphism(frame, text_x - 20, int(h_f * 0.95), text_x + cv2.getTextSize("ESCANEE QR", cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0][0] + 20, int(h_f * 0.99), blur_strength=15, alpha=0.3, border_radius=10)
            cv2.putText(frame, "ESCANEE QR", (text_x, int(h_f * 0.98)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            last_avatar_bbox = None # No hay avatar visible cuando no está activo el guía
        else:
            last_avatar_bbox = None # Resetear en cada frame para evitar clics fantasma
            
            # ------ INICIO LÓGICA PASO 4 (MAPA 3D) ------
            if paso == 4 and activos.get('mapa_img') is not None:
                duracion_caida = 40
                duracion_materializacion = 30
                
                fall_prog = min(self.animation_manager.anim_frame / duracion_caida, 1.0)
                mat_prog = min(self.animation_manager.anim_frame / duracion_materializacion, 1.0)
                
                mapa_original = activos['mapa_img']
                h_m, w_m = mapa_original.shape[:2]
                
                mapa_animado = mapa_original.copy()
                if activos['mapa_img'] is not None and mapa_animado.shape[2] == 4:
                    # Usar máscara pre-generada para evitar parpadeo constante
                    map_noise_mask = activos.get('mapa_mask')
                    if map_noise_mask is not None:
                        mask = (map_noise_mask < mat_prog).astype(np.uint8) * 255
                        mapa_animado[:, :, 3] = cv2.bitwise_and(mapa_animado[:, :, 3], mask)
                
                escala_base = 0.8
                w_target = w_f * escala_base
                h_target = h_m * (w_target / w_m)
                
                center_x = w_f / 2
                bottom_y = h_f * 0.9
                
                pts_inicio = np.float32([
                    [center_x - w_target/2, bottom_y - h_target], [center_x + w_target/2, bottom_y - h_target],
                    [center_x - w_target/2, bottom_y], [center_x + w_target/2, bottom_y]
                ])
                
                persp_suelo = 0.85
                pts_fin = np.float32([
                    [center_x - (w_target/2) * persp_suelo, bottom_y - (h_target * 0.3)],
                    [center_x + (w_target/2) * persp_suelo, bottom_y - (h_target * 0.3)],
                    [center_x - w_target/2, bottom_y], [center_x + w_target/2, bottom_y]
                ])
                
                pts_dst = pts_inicio + (pts_fin - pts_inicio) * fall_prog
                
                if fall_prog >= 1.0:
                    cnt_mapa = pts_dst.reshape((-1, 1, 2)).astype(np.int32)
                    is_over_map = cv2.pointPolygonTest(cnt_mapa, (mouse_x, mouse_y), False) >= 0
                    
                    self.animation_manager.hover_mapa_anim = min(1.0, self.animation_manager.hover_mapa_anim + 0.1) if is_over_map else max(0.0, self.animation_manager.hover_mapa_anim - 0.1)
                    
                    if self.animation_manager.hover_mapa_anim > 0:
                        for i in range(4):
                            px, py = pts_dst[i]
                            dist = np.sqrt((px - mouse_x)**2 + (py - mouse_y)**2)
                            influencia = max(0, 1.0 - dist / 350.0)
                            hundimiento = (influencia * 35 + np.sin(self.animation_manager.anim_frame * 0.2) * 4 * influencia) * self.animation_manager.hover_mapa_anim
                            pts_dst[i][1] += hundimiento

                pts_src = np.float32([[0, 0], [w_m, 0], [0, h_m], [w_m, h_m]])
                
                try:
                    matrix = cv2.getPerspectiveTransform(pts_src, pts_dst)
                    mapa_warped = cv2.warpPerspective(mapa_animado, matrix, (w_f, h_f), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
                    frame = render_alfa(frame, mapa_warped, 0, 0, 1.0)
                except:
                    frame = render_alfa(frame, mapa_animado, 0.1, 0.6, 0.8)

                if fall_prog >= 1.0 and activos.get('pop_up_img') is not None:
                    pop_prog = min((self.animation_manager.anim_frame - duracion_caida) / 30.0, 1.0)
                    flotacion = np.sin(self.animation_manager.anim_frame * 0.1) * 0.02
                    esc_pop = 0.4 * pop_prog
                    y_pop = 0.6 - (0.3 * pop_prog) + flotacion + (0.05 * self.animation_manager.hover_mapa_anim)
                    x_pop = 0.45 - (0.35 * pop_prog)
                    frame = render_alfa(frame, activos['pop_up_img'], x_pop, y_pop, esc_pop)
                
            # ------ FIN LÓGICA PASO 4 ------

            # --- RENDERIZADO DEL SUELÓN (PASO 2) ---
            if paso == 2 and activos.get('suelo_textura') is not None:
                tex_s = activos['suelo_textura']
                h_s, w_s = tex_s.shape[:2]
                pts_src = np.float32([[0,0], [w_s,0], [0,h_s], [w_s,h_s]])
                pts_dst = np.float32([[w_f*0.2, h_f*0.75], [w_f*0.8, h_f*0.75], [-w_f*0.5, h_f], [w_f*1.5, h_f]])
                M_suelo = cv2.getPerspectiveTransform(pts_src, pts_dst)
                suelo_warped = cv2.warpPerspective(tex_s, M_suelo, (w_f, h_f), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
                frame = render_alfa(frame, suelo_warped, 0, 0, 1.0)

            # --- LÓGICA DE ESTAMPIDA (PASO 2) ---
            if paso == 2:
                v_frame = activos['vaca_gif'].get_frame() if activos.get('vaca_gif') else None
                i_frame = activos['iguana_gif'].get_frame() if activos.get('iguana_gif') else None
                
                for animal in animales_stampida:
                    img = v_frame if animal['t'] == 'vaca' else i_frame
                    if img is not None:
                        frame = render_alfa(frame, img, animal['x'], animal['y'], animal['esc'])

            # --- RENDERIZADO DEL PORTÓN (PASO 2) ---
            if paso == 2 and activos.get('porton') is not None:
                frame = render_alfa(frame, activos['porton'], 0.10, 0.02, 1.1)

            # ------ RENDERIZADO DE AVATAR CON SOMBRA ------
            av_handler = activos['avatars'].get(paso)
            if av_handler:
                if paso == 2 and av_handler.current_frame >= len(av_handler.frames) - 1:
                    img_av = None
                else:
                    img_av = av_handler.get_frame()

                if img_av is not None:
                    if paso == 2:
                        h_a, w_a = img_av.shape[:2]
                        pts1 = np.float32([[0,0], [w_a,0], [0,h_a], [w_a,h_a]])
                        pts2 = np.float32([[0, 0], [w_a, h_a*0.12], [0, h_a], [w_a, h_a*0.88]])
                        matrix_rot = cv2.getPerspectiveTransform(pts1, pts2)
                        img_av = cv2.warpPerspective(img_av, matrix_rot, (w_a, h_a), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))

                    h_orig, w_orig = img_av.shape[:2]
                    esc = 0.7
                    w_esc, h_esc = int(w_orig * esc), int(h_orig * esc)
                    
                    x_porc = (w_f - w_esc) / (2.0 * w_f) if paso == 1 else (0.20 if paso == 2 else 0.40)
                    y_porc = 0.35

                    # --- LÓGICA DE CAÍDA Y POLVO ---
                    if not hasattr(av_handler, 'spawn_timer'): av_handler.spawn_timer = 0
                    if not hasattr(av_handler, 'dust_done'): av_handler.dust_done = False
                    
                    av_handler.spawn_timer += 1
                    bounce_offset = 0
                    
                    if av_handler.spawn_timer < 20:
                        t = av_handler.spawn_timer / 20.0
                        # El avatar sube y baja siguiendo una curva de seno amortiguada para un aterrizaje suave
                        bounce_offset = np.sin(t * np.pi) * 0.08 * (1.0 - t)
                        
                        # El impacto ocurre justo cuando termina el movimiento de caída (frame 20)
                        if av_handler.spawn_timer >= 19 and not av_handler.dust_done:
                            av_handler.dust_done = True
                            foot_x = int(w_f * x_porc) + (w_esc // 2)
                            foot_y = int(h_f * y_porc) + h_esc - 10
                            self.animation_manager.add_dust_particles(foot_x, foot_y)

                    y_porc_final = y_porc - bounce_offset
                    x_px, y_px = int(w_f * x_porc), int(h_f * y_porc_final)
                    
                    ry_sombra = h_esc // 15
                    # La sombra permanece fija en el "suelo" (y_porc original) para dar profundidad al salto
                    dibujar_sombra(frame, x_px + w_esc // 2, int(h_f * y_porc) + h_esc - ry_sombra, w_esc // 2.5, ry_sombra)
                    
                    last_avatar_bbox = (x_px, y_px, w_esc, h_esc)
                    frame = render_alfa(frame, img_av, x_porc, y_porc_final, esc)
                    
                    bu = activos['burbujas'].get(paso)
                    if bu and paso != 5 and img_av is not None:
                        # --- ANIMACIÓN DE ESCALA POP-IN PARA LA BURBUJA ---
                        # Calculamos la escala basada en el frame actual del GIF para el efecto de aparición
                        target_bubble_scale = 0.9
                        # El pop-in se completa en los primeros 10 frames (muy rápido)
                        pop_prog = min(1.0, bu.current_frame / 10.0)
                        # Aplicamos un suavizado Out Cubic para que el crecimiento sea elegante
                        e_scale = 1 - (1 - pop_prog)**3
                        # La burbuja sigue el rebote del avatar para mantener la conexión
                        frame = render_alfa(frame, bu.get_frame(), x_porc, y_porc_final - 0.40, target_bubble_scale * e_scale)

            # --- RENDERIZADO DE INTERFAZ DE TRIVIA (PASO 5) ---
            if paso == 5:
                if trivia_fase == 1:
                    frame = self.ui_manager.draw_trivia_phase1(frame, w_f, h_f, trivia_opciones, trivia_errores, trivia_acierto, mouse_x, mouse_y)
                else:
                    frame = self.ui_manager.draw_trivia_phase2(frame, w_f, h_f, trivia_opciones_fase2, trivia_errores, trivia_acierto, mouse_x, mouse_y, self.animation_manager)

            if paso == max_pasos and activos['foto_h'] is not None:
                frame = render_alfa(frame, activos['foto_h'], 0.10, 0.10, 0.3)

            # --- RENDERIZADO DE BOTONES DE NAVEGACIÓN ---
            frame = self.ui_manager.draw_navigation_buttons(frame, w_f, h_f, paso, max_pasos, mouse_x, mouse_y, self.animation_manager)

            # --- INTERFAZ GLOBAL (MONEDAS Y TIENDA) ---
            frame = self.ui_manager.draw_hud(frame, w_f, h_f, paso, max_pasos, monedas, mouse_x, mouse_y, self.animation_manager)

            # Siempre llamamos a draw_shop_menu para permitir la animación de entrada y salida (slide)
            frame = self.ui_manager.draw_shop_menu(frame, w_f, h_f, outfits_disponibles, outfits_comprados, atuendo_actual, self.animation_manager, mouse_x, mouse_y, tienda_abierta, monedas)

        # Renderizar partículas
        self.animation_manager.render_particles(frame)

        # Aplicar fade global si hay una transición activa
        if self.animation_manager.transition_active and self.animation_manager.fade_alpha > 0:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w_f, h_f), (0, 0, 0), -1)
            cv2.addWeighted(overlay, self.animation_manager.fade_alpha, frame, 1.0 - self.animation_manager.fade_alpha, 0, frame)

        return frame, last_avatar_bbox

    def release_camera(self):
        self.cap.release()