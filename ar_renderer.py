import cv2
import numpy as np
import pygame
from utils import render_alfa, dibujar_texto_utf8, dibujar_sombra, apply_glassmorphism, draw_rounded_rect

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

    def render(self, frame, estado, paso, max_pasos, activos, animales_stampida, mouse_x, mouse_y, last_avatar_bbox, monedas, tienda_abierta, marcos_disponibles, marcos_comprados, marco_actual, trivia_fase, trivia_opciones, trivia_opciones_fase2, trivia_errores, trivia_acierto, puzzle_system, planchon_system, ayuda_activa, progreso, sitio_actual_id, fps=0):
        h_f, w_f, _ = frame.shape
        guia_activo = (estado == "guia")

        # --- MARCO DECORATIVO (CAPA DE FONDO) ---
        # Se renderiza antes que cualquier otro elemento para que siempre esté en los bordes y por debajo.
        frame = self.ui_manager.draw_decorative_frame(frame, marco_actual, self.animation_manager)

        if estado == "bienvenida":
            return self.ui_manager.draw_welcome_screen(frame, w_f, h_f, mouse_x, mouse_y, self.animation_manager), None

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

        if self.map_system.modo_seleccion:
            frame = self.map_system.render_map_animation(frame, w_f, h_f, mouse_x, mouse_y, self.animation_manager.anim_frame, self.animation_manager, progreso)
            # Texto instructivo superior con nuevo mensaje y color negro
            s1_completado = progreso.get('s1', False)
            txt_mapa = "¿cual es el siguiente sitio?" if s1_completado else "selecciona el primer sitio turistico para desbloquear los otros" # This text remains
            
            if s1_completado:
                # Solo dibujamos el texto en pantalla si ya se completó el sitio 1
                tw = cv2.getTextSize(txt_mapa, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0][0]
                box_w, box_h = tw + 45, 65
                bx1 = (w_f - box_w) // 2
                by1 = h_f - box_h - 25
                apply_glassmorphism(frame, bx1, by1, bx1 + box_w, by1 + box_h, blur_strength=15, alpha=0.3, border_radius=15)
                frame = dibujar_texto_utf8(frame, txt_mapa, (bx1 + 22, by1 + 15), 20, (0, 0, 0))

            last_avatar_bbox = None # No hay avatar visible en modo selección
        elif not guia_activo:
            # Avatar de bienvenida durante el escaneo (Lado Izquierdo)
            if self.ui_manager.avatar_6 is not None: # Usamos el nuevo avatar_6
                frame = render_alfa(frame, self.ui_manager.avatar_6, 0.05, 0.25, 0.30)

            if self.ui_manager.img_escaner is not None:
                # Renderizar la interfaz del escáner un poco más grande
                frame = render_alfa(frame, self.ui_manager.img_escaner, 0.45, 0.15, 0.70)
            
        else:
            last_avatar_bbox = None # Resetear en cada frame para evitar clics fantasma
            
            # Lógica para determinar si el avatar y la burbuja han terminado su discurso/animación
            is_finished = True
            # 1. Verificar si el audio (TTS) sigue ocupado
            if pygame.mixer.get_init() and pygame.mixer.Channel(1).get_busy():
                is_finished = False
            # 2. Verificar si la burbuja de texto sigue animándose
            bu_anim = activos.get('burbujas', {}).get(paso)
            if bu_anim and bu_anim.frames and bu_anim.current_frame < len(bu_anim.frames) - 1:
                is_finished = False
            # 3. Verificar si el avatar sigue animándose
            av_anim = activos.get('avatars', {}).get(paso)
            if av_anim and av_anim.frames and av_anim.current_frame < len(av_anim.frames) - 1:
                is_finished = False

            # ------ INICIO LÓGICA PASO 4 (MAPA 3D) ------
            # Sitio 1: Paso 4 | Sitio 2 y 3: Paso 3
            if (paso == 4 and sitio_actual_id == 'sitio1') or (paso == 3 and sitio_actual_id in ['sitio_2', 'sitio_3']):
                duracion_caida = 40
                fall_prog = min(self.animation_manager.anim_frame / duracion_caida, 1.0)

                # Renderizado del Mapa (Solo si existe el activo)
                if activos.get('mapa_img') is not None:
                    duracion_materializacion = 30
                    mat_prog = min(self.animation_manager.anim_frame / duracion_materializacion, 1.0)
                    mapa_original = activos['mapa_img']
                    h_m, w_m = mapa_original.shape[:2]
                    mapa_animado = mapa_original.copy()
                    
                    if mapa_animado.shape[2] == 4:
                        map_noise_mask = activos.get('mapa_mask')
                        if map_noise_mask is not None:
                            mask = (map_noise_mask < mat_prog).astype(np.uint8) * 255
                            mapa_animado[:, :, 3] = cv2.bitwise_and(mapa_animado[:, :, 3], mask)
                    
                    escala_base, w_target = 0.8, w_f * 0.8
                    h_target = h_m * (w_target / w_m)
                    center_x, bottom_y = w_f / 2, h_f * 0.9
                    
                    pts_inicio = np.float32([[center_x - w_target/2, bottom_y - h_target], [center_x + w_target/2, bottom_y - h_target], [center_x - w_target/2, bottom_y], [center_x + w_target/2, bottom_y]])
                    pts_fin = np.float32([[center_x - (w_target/2) * 0.85, bottom_y - (h_target * 0.3)], [center_x + (w_target/2) * 0.85, bottom_y - (h_target * 0.3)], [center_x - w_target/2, bottom_y], [center_x + w_target/2, bottom_y]])
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
                                pts_dst[i][1] += (influencia * 35 + np.sin(self.animation_manager.anim_frame * 0.2) * 4 * influencia) * self.animation_manager.hover_mapa_anim

                    try:
                        matrix = cv2.getPerspectiveTransform(np.float32([[0, 0], [w_m, 0], [0, h_m], [w_m, h_m]]), pts_dst)
                        mapa_warped = cv2.warpPerspective(mapa_animado, matrix, (w_f, h_f), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
                        frame = render_alfa(frame, mapa_warped, 0, 0, 1.0)
                    except:
                        pass

                # --- SELECCIÓN INTELIGENTE DE ACTIVO (SITIO 1, 2 Y 3) ---
                # Priorizamos foto_h para los sitios históricos (2 y 3) en su paso de transición
                if sitio_actual_id in ['sitio_2', 'sitio_3'] and paso == 3:
                    img_pop = activos.get('foto_h') if activos.get('foto_h') is not None else activos.get('pop_up_img')
                else:
                    img_pop = activos.get('pop_up_img')

                if fall_prog >= 1.0 and img_pop is not None:
                    pop_prog = min((self.animation_manager.anim_frame - duracion_caida) / 30.0, 1.0)
                    flotacion = np.sin(self.animation_manager.anim_frame * 0.1) * 0.02
                    
                    # --- ANIMACIÓN CINEMATOGRÁFICA (FADE + SCALE + GLOW) ---
                    img_to_render = img_pop.copy()
                    # Aplicar Fade suave manipulando el canal alfa
                    if img_to_render.shape[2] == 4:
                        img_to_render[:, :, 3] = (img_to_render[:, :, 3] * pop_prog).astype(np.uint8)
                    
                    # Trayectoria unificada para todos los sitios: emerge del mapa en diagonal a la izquierda
                    esc_pop = 0.4 * pop_prog
                    x_pop = 0.42 - (0.35 * pop_prog)
                    y_pop = 0.6 - (0.3 * pop_prog) + flotacion + (0.05 * self.animation_manager.hover_mapa_anim)
                    
                    # Ahora que x_pop y y_pop están definidos, añadir partículas de glow
                    if 0.1 < pop_prog < 0.2:
                        self.animation_manager.add_pin_glow_particles(w_f * x_pop, h_f * y_pop, 2)

                    frame = render_alfa(frame, img_to_render, x_pop, y_pop, esc_pop)
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
            # En el paso 5 no renderizamos el avatar estándar ni su burbuja, 
            # ya que usamos el avatar especial de 'duda' dentro de la interfaz de trivia.
            av_handler = activos['avatars'].get(paso)
            
            # Condición especial: en el sitio 2 (paso 4), ocultamos el avatar hasta resolver el puzzle
            puede_mostrar_av = not (sitio_actual_id == 'sitio_2' and paso == 4 and not puzzle_system.completado)
            
            if av_handler and puede_mostrar_av and not (sitio_actual_id == 'sitio1' and paso == 5):
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
                    
                    # Se ajusta x_porc para el paso 2 de 0.20 a 0.32 para no tapar el botón de saltar
                    x_porc = (w_f - w_esc) / (2.0 * w_f) if paso == 1 else (0.32 if paso == 2 else 0.40)
                    y_porc = 0.35

                    # --- LÓGICA DE CAÍDA Y POLVO ---
                    if not hasattr(av_handler, 'spawn_timer'): av_handler.spawn_timer = 0
                    if not hasattr(av_handler, 'dust_done'): av_handler.dust_done = False
                    
                    av_handler.spawn_timer += 1
                    bounce_offset = 0
                    """ # Comentamos o eliminamos el efecto de rebote
                    if av_handler.spawn_timer < 20:
                        t = av_handler.spawn_timer / 20.0
                        # El avatar sube y baja siguiendo una curva de seno amortiguada para un aterrizaje suave
                        bounce_offset = np.sin(t * np.pi) * 0.08 * (1.0 - t)
                        
                        # El impacto ocurre justo cuando termina el movimiento de caída (frame 20)
                        if av_handler.spawn_timer >= 19 and not av_handler.dust_done:
                            av_handler.dust_done = True
                    """

                    y_porc_final = y_porc - bounce_offset
                    x_px, y_px = int(w_f * x_porc), int(h_f * y_porc_final)
                    
                    ry_sombra = h_esc // 15
                    # La sombra permanece fija en el "suelo" (y_porc original) para dar profundidad al salto
                    dibujar_sombra(frame, x_px + w_esc // 2, int(h_f * y_porc) + h_esc - ry_sombra, w_esc // 2.5, ry_sombra)
                    
                    last_avatar_bbox = (x_px, y_px, w_esc, h_esc)
                    frame = render_alfa(frame, img_av, x_porc, y_porc_final, esc)
                    
                    bu = activos['burbujas'].get(paso)
                    if bu and img_av is not None and not (sitio_actual_id == 'sitio1' and paso == 5):
                        target_bubble_scale = 0.9
                        # Eliminamos e_scale para que la burbuja no crezca, sino que aparezca a tamaño real
                        e_scale = 1.0 
                        # Ajuste específico para el final de los sitios (paso 6 en sitio 1, paso 5 en sitio 2 y 3)
                        es_final = (paso == max_pasos)
                        x_bu = x_porc # Alineado con el avatar
                        y_bu = y_porc_final - 0.42 
                        frame = render_alfa(frame, bu.get_frame(), x_bu, y_bu, target_bubble_scale)

            # --- RENDERIZADO DE INTERFAZ DE TRIVIA (PASO 5) ---
            if paso == 5 and sitio_actual_id == 'sitio1':
                if trivia_fase == 1:
                    frame = self.ui_manager.draw_trivia_phase1(frame, w_f, h_f, trivia_opciones, trivia_errores, trivia_acierto, mouse_x, mouse_y, activos.get('avatar_trivia'))
                else:
                    frame = self.ui_manager.draw_trivia_phase2(frame, w_f, h_f, trivia_opciones_fase2, trivia_errores, trivia_acierto, mouse_x, mouse_y, self.animation_manager, activos.get('avatar_trivia'))

            # --- RENDERIZADO DEL ROMPECABEZAS REALISTA ---
            if sitio_actual_id == 'sitio_2' and paso == 4 and puzzle_system.activo:
                # Actualizar el centro del área de armado según el tamaño de la ventana
                puzzle_system.centro_target = (w_f // 2, h_f // 2)
                
                # Dibujar guía visual del puzzle (rectángulo semitransparente)
                px1 = puzzle_system.centro_target[0] - (puzzle_system.w_puzzle // 2)
                py1 = puzzle_system.centro_target[1] - (puzzle_system.h_puzzle // 2)
                px2 = px1 + puzzle_system.w_puzzle
                py2 = py1 + puzzle_system.h_puzzle
                
                overlay = frame.copy()
                cv2.rectangle(overlay, (px1, py1), (px2, py2), (255, 255, 255), 2)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                
                # Dibujar la imagen guía "fantasma" de fondo para ayudar al usuario
                if puzzle_system.img_guia is not None:
                    frame = render_alfa(frame, puzzle_system.img_guia, px1/w_f, py1/h_f, 1.0)
                
                for p in puzzle_system.piezas:
                    # Renderizar cada pieza con su forma y contorno
                    frame = render_alfa(frame, p.img, p.x/w_f, p.y/h_f, 1.0)

                if puzzle_system.completado:
                    # Mensaje de éxito si el usuario termina
                    msg = "¡ROMPECABEZAS COMPLETADO!"
                    tw, th = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
                    apply_glassmorphism(frame, w_f//2 - tw//2 - 20, h_f//2 - th//2 - 20, w_f//2 + tw//2 + 20, h_f//2 + th//2 + 20)
                    frame = dibujar_texto_utf8(frame, msg, (w_f//2 - tw//2, h_f//2 - th//2), 30, (0, 255, 0))
            
            # --- RENDERIZADO DEL MINIJUEGO DE PLANCHONES (SITIO 3) ---
            if sitio_actual_id == 'sitio_3' and paso == 4:
                # Delegamos el renderizado completo al sistema especializado
                frame = planchon_system.dibujar(frame, self.animation_manager.anim_frame, self.animation_manager)

            # Se muestra la foto histórica al final (paso 6) en el sitio 1, pero se quita en el sitio 2 paso 5 por petición
            if paso == max_pasos and activos['foto_h'] is not None and sitio_actual_id != 'sitio_2':
                frame = render_alfa(frame, activos['foto_h'], 0.10, 0.10, 0.3)

            # --- BOTÓN DE FINALIZACIÓN (APARECE AL FINAL DE CADA SITIO) ---
            es_fin_s1 = (paso == 6 and sitio_actual_id == 'sitio1')
            es_fin_s2 = (paso == 5 and sitio_actual_id == 'sitio_2')
            es_fin_s3 = (paso == 5 and sitio_actual_id == 'sitio_3')

            # Si es el final del sitio y ya terminó de hablar, mostramos el botón de salida
            if (es_fin_s1 or es_fin_s2 or es_fin_s3) and is_finished:
                frame = self.ui_manager.draw_finish_site_button(frame, w_f, h_f, mouse_x, mouse_y)
            else:
                # --- RENDERIZADO DE BOTONES DE NAVEGACIÓN ---
                show_next = True
                # REGLA: El botón de siguiente NO SALE hasta que terminen los GIFs y el Audio
                if not is_finished:
                    show_next = False # Ocultar "Siguiente" hasta que termine la animación/audio

                # Ocultar "Siguiente" en Trivia de Sitio 1, Puzzle incompleto de Sitio 2, o en cualquier paso de Felicitaciones
                if sitio_actual_id == 'sitio1' and paso == 5: show_next = False
                if sitio_actual_id == 'sitio_2' and paso == 4 and not puzzle_system.completado: show_next = False
                if sitio_actual_id == 'sitio_3' and paso == 4 and not planchon_system.completado: show_next = False
                if paso == max_pasos: show_next = False
                
                show_back = True
                if sitio_actual_id == 'sitio_3' and paso == 4 and not planchon_system.completado:
                    show_back = False
                frame = self.ui_manager.draw_navigation_buttons(frame, w_f, h_f, paso, max_pasos, mouse_x, mouse_y, self.animation_manager, show_next, show_back)

            # --- INTERFAZ GLOBAL (MONEDAS Y TIENDA) ---
            frame = self.ui_manager.draw_hud(frame, w_f, h_f, paso, max_pasos, monedas, mouse_x, mouse_y, self.animation_manager)

            # Siempre llamamos a draw_shop_menu para permitir la animación de entrada y salida (slide)
            frame = self.ui_manager.draw_shop_menu(frame, w_f, h_f, marcos_disponibles, marcos_comprados, marco_actual, self.animation_manager, mouse_x, mouse_y, tienda_abierta, monedas)

        # --- PROFILER PROFESIONAL ---
        if fps > 0:
            debug_txt = f"FPS: {fps:.1f} | MEM: {len(self.animation_manager.particles)} P | ST: {sitio_actual_id}"
            # Caja pequeña y minimalista
            apply_glassmorphism(frame, w_f-220, h_f-35, w_f-10, h_f-5, blur_strength=5, alpha=0.5, border_radius=5)
            dibujar_texto_utf8(frame, debug_txt, (w_f-210, h_f-30), 12, (255, 255, 255))

        # Renderizar partículas
        self.animation_manager.render_particles(frame)

        return frame, last_avatar_bbox

    def release_camera(self):
        self.cap.release()