import cv2
import numpy as np
import os
import random
from utils import load_ui_asset, render_alfa, dibujar_sombra, apply_glassmorphism, dibujar_texto_utf8, draw_rounded_rect

class PlanchonSystem:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        # --- FÍSICA AVANZADA ---
        self.x_planchon, self.y_planchon = 0.2, 0.14
        self.target_x, self.target_y = 0.2, 0.14
        self.velocidad_x = 0.0
        self.velocidad_y = 0.0
        self.aceleracion = 0.003
        self.friccion = 0.94
        self.rotacion = 0.0
        self.target_rotacion = 0.0
        
        # Configuración de Origen y Destino (pos_destino ajustado para no salir del río)
        self.pos_origen = (0.2, 0.14) # Ajustado para que el casco toque la orilla superior
        self.pos_destino = (0.8, 0.55) # Detener el barco un poco antes

        self.dragging = False # Nuevo estado para arrastre
        self.timer_inicio = 0 # Temporizador para el anuncio inicial

        # Estados: 'anuncio_inicio', 'tutorial', 'esperando_carga', 'cargando', 'navegando', 'descargando', 'completado'
        self.estado_juego = 'anuncio_inicio'
        self.tutorial_completado = False
        
        self.pasajeros_a_bordo = 0
        self.pasajeros_esperando = random.choice([3, 6, 9]) # Iniciar con personas ya ahí
        # self.iconos_orilla ya no se usa para iconos individuales
        self.pasajeros_animando = []
        self.pasajeros_en_destino_final = []
        self.entidades_pasajeros = [] 
        
        self.total_pasajeros_entregados = 0
        self.objetivo_total = 18 
        self.viajes_completados = 0
        self.objetivo_viajes = 3 # El barco debe hacer 3 viajes
        self.recompensa_viaje = 250
        self.estado_mensajes = ""
        self.activo = False
        self.completado = False

        # Assets (img_persona_base y img_icon_personas ya no se usan para dibujar pasajeros individuales a bordo)
        self.img_planchon = load_ui_asset('planchon_iso.png', self.base_dir)
        self.img_persona_base = load_ui_asset('persona_1.png', self.base_dir)
        self.img_guante = load_ui_asset('guante.png', self.base_dir)
        self.img_icon_personas = load_ui_asset('icon_personas.png', self.base_dir)
        self.img_orilla = load_ui_asset('orilla.png', self.base_dir)
        
        if self.img_persona_base is None: self.img_persona_base = load_ui_asset('persona.png', self.base_dir)
        
        # Caché de resolución para cálculos de hitbox precisos
        # Se inicializa con valores estándar, pero se actualiza en cada frame en dibujar()
        self.last_w = 1280
        self.last_h = 720

        # Caché de orillas optimizado
        self.cache_orilla_top = None
        self.cache_orilla_bot = None
        self.last_res = (0, 0)

        # Caché de agua animada
        self.river_frames = []
        self._cargar_frames_rio()
        

    def _cargar_frames_rio(self):
        """Carga y optimiza los frames del agua en memoria."""
        path_rio = os.path.join(self.base_dir, 'assets', 'river_frames')
        if os.path.exists(path_rio):
            files = sorted([f for f in os.listdir(path_rio) if f.endswith('.png')])
            for f in files:
                img = cv2.imread(os.path.join(path_rio, f), cv2.IMREAD_UNCHANGED)
                if img is not None:
                    # Asegurar que el frame del río tenga canal alfa para el renderizador optimizado
                    if len(img.shape) == 3 or img.shape[2] == 3:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                    # Pre-resize para optimizar renderizado
                    self.river_frames.append(cv2.resize(img, (1280, 400))) 

    def reset(self):
        self.estado_juego = 'anuncio_inicio'
        self.timer_inicio = 0
        self.tutorial_completado = False
        self.pasajeros_a_bordo = 0
        self.pasajeros_esperando = random.choice([3, 6, 9]) # Personas ya presentes
        self.total_pasajeros_entregados = 0
        self.velocidad_x, self.velocidad_y = 0.0, 0.0 # Reiniciar velocidad
        self.pasajeros_animando = []
        self.pasajeros_en_destino_final = []
        self.entidades_pasajeros = []
        self.viajes_completados = 0
        self.completado = False
        self.estado_mensajes = "Capitán, arrastra el planchón al origen para recoger turistas."
        self.x_planchon, self.y_planchon = 0.2, 0.14 # Posición inicial en el muelle
        self.target_x, self.target_y = 0.2, 0.14 # Iniciar estático en el muelle
        self.dragging = False
        self.rotacion = 0.0

    def manejar_mouse(self, event, x_rel, y_rel):
        if not self.activo or self.completado:
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            # Si estamos en el anuncio de inicio, cualquier toque lo quita para empezar
            if self.estado_juego == 'anuncio_inicio':
                self.estado_juego = 'tutorial'
                return

            # --- DETECCIÓN DE BOTONES EN EL HUD ---
            if y_rel > 0.84:
                # Botón Ir al Origen (Flecha Arriba)
                if 0.55 < x_rel < 0.65:
                    self.target_x, self.target_y = self.pos_origen
                    self.estado_mensajes = "Navegando hacia el muelle de origen..."
                
                # Botón Ir al Destino (Flecha Abajo)
                if 0.67 < x_rel < 0.77:
                    self.target_x, self.target_y = self.pos_destino
                    self.estado_mensajes = "Navegando hacia el destino..."

                # Botón Acción (Embarcar / Desembarcar)
                if 0.26 < x_rel < 0.50:
                    dist_origen = np.sqrt((self.x_planchon - self.pos_origen[0])**2 + (self.y_planchon - self.pos_origen[1])**2)
                    dist_destino = np.sqrt((self.x_planchon - self.pos_destino[0])**2 + (self.y_planchon - self.pos_destino[1])**2)
                    
                    # Lógica de Embarque
                    if dist_origen < 0.05 and self.pasajeros_esperando > 0:
                        for _ in range(self.pasajeros_esperando // 3):
                            start_x_anim = self.pos_origen[0] + random.uniform(-0.04, 0.04)
                            start_y_anim = self.pos_origen[1] - 0.08 + random.uniform(-0.02, 0.02)
                            self.pasajeros_animando.append({
                                "x": start_x_anim, "y": start_y_anim, 
                                "start_x": start_x_anim, "start_y": start_y_anim,
                                "t_anim": 0.0, "anim_mode": "to_boat"
                            })
                        self.pasajeros_a_bordo += self.pasajeros_esperando
                        self._generar_pasajeros_visuales_bordo()
                        self.pasajeros_esperando = 0
                        self.estado_mensajes = "¡Pasajeros a bordo! Rumbo al destino."
                    
                    # Lógica de Desembarque
                    elif dist_destino < 0.05 and self.pasajeros_a_bordo > 0:
                        self.estado_juego = 'descargando'
                        self._iniciar_animacion_descarga()

        # Dragging desactivado para movimiento por botones

    def actualizar(self, animation_manager):
        if not self.activo or self.completado:
            return

        # Lógica del anuncio inicial (esperando interacción del usuario)
        if self.estado_juego == 'anuncio_inicio':
            return

        if self.estado_juego == 'tutorial' and self.dragging:
            self.estado_juego = 'esperando_carga'
            self.tutorial_completado = True

        # --- FÍSICA VECTORIAL CON INERCIA Y RESTRICCIÓN A LA LÍNEA ---
        # Calcular la fuerza de atracción hacia el target
        force_x = (self.target_x - self.x_planchon) * self.aceleracion
        force_y = (self.target_y - self.y_planchon) * self.aceleracion

        # Aplicar la fuerza a la velocidad
        self.velocidad_x += force_x
        self.velocidad_y += force_y

        # Aplicar el "drift" del río (pequeña perturbación horizontal)
        drift_x = 0.0003 * np.sin(animation_manager.anim_frame * 0.03)
        self.velocidad_x += drift_x 
        
        # Aplicar fricción (resistencia del agua) a la velocidad
        self.velocidad_x *= self.friccion
        self.velocidad_y *= self.friccion

        # Actualizar la posición del planchón
        self.x_planchon += self.velocidad_x
        self.y_planchon += self.velocidad_y

        # Proyectar la posición actual del planchón sobre la línea definida por pos_origen y pos_destino
        P0 = self.pos_origen
        P1 = self.pos_destino # Ahora P1 está dentro del río
        dx = P1[0] - P0[0]
        dy = P1[1] - P0[1]
        length_sq = dx*dx + dy*dy

        if length_sq > 0:
            t = ((self.x_planchon - P0[0]) * dx + (self.y_planchon - P0[1]) * dy) / length_sq
            t = np.clip(t, 0, 1) # Asegurarse de que el planchón se mantenga dentro del segmento
            self.x_planchon = P0[0] + t * dx
            self.y_planchon = P0[1] + t * dy
        
        # --- ROTACIÓN ORGÁNICA ---
        self.target_rotacion = np.clip(self.velocidad_x * 800, -8, 8)
        self.rotacion += (self.target_rotacion - self.rotacion) * 0.1
        
        # --- ANIMACIÓN PROGRESIVA DE PASAJEROS ---
        for p in self.pasajeros_animando[:]:
            p['t_anim'] += 0.08
            if p['anim_mode'] == 'to_boat':
                ease = 1 - (1 - p['t_anim'])**2
                p['x'] = p['start_x'] + (self.x_planchon - p['start_x']) * ease
                p['y'] = p['start_y'] + (self.y_planchon - p['start_y']) * ease
                if p['t_anim'] >= 1.0: # Cuando la animación termina, el pasajero ya está "a bordo"
                    # La lógica de sumar pasajeros a bordo ya se hizo en manejar_mouse
                    # Solo necesitamos remover la animación
                    self.pasajeros_animando.remove(p)
            elif p['anim_mode'] == 'to_shore':
                ease = 1 - (1 - p['t_anim'])**2
                p['x'] = self.x_planchon + (p['end_x'] - self.x_planchon) * ease
                p['y'] = self.y_planchon + (p['end_y'] - self.y_planchon) * ease
                if p['t_anim'] >= 1.0:
                    self.total_pasajeros_entregados += 3
                    self.pasajeros_en_destino_final.append({"x": p['x'], "y": p['y']}) # Mantener para visualización de "descargados"
                    self.pasajeros_animando.remove(p)
                    if self.pasajeros_a_bordo == 0 and not self.pasajeros_animando:
                        self.finalizar_viaje()

        # --- GENERACIÓN DE ESTELA Y PARTÍCULAS ---
        if abs(self.velocidad_x) + abs(self.velocidad_y) > 0.003:
            animation_manager.add_pin_glow_particles(self.x_planchon * 1280, self.y_planchon * 720, 1)
            if animation_manager.anim_frame % 5 == 0:
                # Burbujas de agua detrás del planchón
                animation_manager.add_firefly_particles((self.x_planchon - self.velocidad_x*10) * 1280, (self.y_planchon + 0.05) * 720, 1)

        # Eliminado el auto-trigger de descarga al llegar al destino

    def _iniciar_animacion_descarga(self):
        grupos = self.pasajeros_a_bordo // 3
        self.pasajeros_a_bordo = 0
        self.entidades_pasajeros = []
        for _ in range(grupos): # Animamos por grupos de 3
            self.pasajeros_animando.append({
                "x": self.x_planchon, "y": self.y_planchon,
                "end_x": self.pos_destino[0] + random.uniform(0.05, 0.10), # Al otro lado (derecha)
                "end_y": self.pos_destino[1] + random.uniform(0.15, 0.22), # Aún más abajo
                "anim_mode": 'to_shore',
                "t_anim": 0.0,
            })

    def finalizar_viaje(self):
        self.viajes_completados += 1
        if self.viajes_completados >= self.objetivo_viajes: # El juego termina al completar los 3 viajes
            self.completado = True
        else:
            self.pasajeros_esperando = random.choice([3, 6, 9]) # Nuevas personas aparecen
            self.estado_juego = 'esperando_carga'
            self.estado_mensajes = f"Viaje {self.viajes_completados}/3 completado. Vuelve por más turistas."

    def _generar_pasajeros_visuales_bordo(self):
        """Genera las entidades visuales para los pasajeros a bordo del planchón."""
        self.entidades_pasajeros = []
        if self.img_persona_base is None: return
        
        # Distribuir pasajeros dentro del área del planchón
        for i in range(self.pasajeros_a_bordo):
            # Posiciones relativas dentro del planchón (ajustadas al renderizado del barco)
            ox_offset = random.uniform(-0.03, 0.03) # Offset horizontal relativo al centro del barco
            oy_offset = random.uniform(-0.01, 0.01) # Offset vertical relativo al centro del barco
            escala_var = random.uniform(0.08, 0.10) # Escala para personas individuales
            self.entidades_pasajeros.append({
                "img": self.img_persona_base,
                "ox": ox_offset, "oy": oy_offset,
                "id": random.random(), "esc": escala_var
            })

    def dibujar(self, frame, anim_frame, animation_manager):
        h_f, w_f = frame.shape[:2]
        self.last_w, self.last_h = w_f, h_f
        
        # 1. RENDERIZADO DEL RÍO (FONDO ANIMADO)
        rio_y1, rio_y2 = int(h_f * 0.22), int(h_f * 0.78)
        rio_h = rio_y2 - rio_y1
        if self.river_frames:
            idx = (anim_frame // 2) % len(self.river_frames)
            # OPTIMIZACIÓN: Solo redimensionar si el ancho de ventana cambió
            agua = self.river_frames[idx]
            if agua.shape[1] != w_f: agua = cv2.resize(agua, (w_f, rio_h))
            frame[rio_y1:rio_y2, :] = render_alfa(frame[rio_y1:rio_y2, :], agua, 0, 0, 1.0)

        # 1.5 RENDERIZADO DE ORILLAS (TEXTURA PNG)
        if self.img_orilla is not None:
            # Actualizar caché si la resolución cambia
            if (w_f, h_f) != self.last_res:
                self.cache_orilla_top = cv2.resize(self.img_orilla, (w_f, rio_y1))
                # Invertir para que no parezca espejo exacto
                self.cache_orilla_top = cv2.flip(self.cache_orilla_top, 0)
                self.cache_orilla_bot = cv2.resize(self.img_orilla, (w_f, h_f - rio_y2))
                self.last_res = (w_f, h_f)

            # Dibujar con render_alfa para respetar transparencias de arena/vegetación
            frame[0:rio_y1, :] = render_alfa(frame[0:rio_y1, :], self.cache_orilla_top, 0, 0, 1.0)
            frame[rio_y2:h_f, :] = render_alfa(frame[rio_y2:h_f, :], self.cache_orilla_bot, 0, 0, 1.0)

            # Sombras cinemáticas de profundidad en los bordes del agua
            dibujar_sombra(frame, w_f//2, rio_y1 + 5, w_f//2, 15, alpha=0.4) # Sombra superior
            dibujar_sombra(frame, w_f//2, rio_y2 - 5, w_f//2, 15, alpha=0.4) # Sombra inferior
        
        # 3. FLECHAS DE DIRECCIÓN (Sutiles)
        self._dibujar_trayecto_guiado(frame, anim_frame, w_f, h_f)

        # 2. RENDERIZADO DEL PLANCHÓN
        py_render = self.y_planchon + np.sin(anim_frame * 0.08) * 0.005
        if self.img_planchon is not None:
            dibujar_sombra(frame, self.x_planchon * w_f, (py_render + 0.04) * h_f, w_f*0.07, h_f*0.02, alpha=0.3)
            frame = render_alfa(frame, self.img_planchon, self.x_planchon - 0.1, py_render - 0.06, 0.5)

        # 3. RENDERIZADO DE PASAJEROS
        # Iconos de pasajeros animando (bolitas flotantes/iconos)
        for p in self.pasajeros_animando:
            frame = render_alfa(frame, self.img_icon_personas, p['x'], p['y'], 0.08)
            
        # En destino (finalizados)
        for p in self.pasajeros_en_destino_final:
            frame = render_alfa(frame, self.img_icon_personas, p['x'], p['y'], 0.10) # Más grande

        # 4. PASAJEROS INDIVIDUALES A BORDO (Dentro del barco)
        for p in self.entidades_pasajeros:
            # Pequeña animación de "idle"
            p_idle = np.sin(anim_frame * 0.1 + p['id']) * 0.005
            frame = render_alfa(frame, p['img'], self.x_planchon - 0.1 + p['ox'], py_render - 0.06 + p['oy'] + p_idle, p['esc'])

        # 5. INDICADORES DE ORIGEN Y DESTINO
        frame = self._dibujar_circulo_indicador(frame, self.pos_origen, "ORIGEN", anim_frame, w_f, h_f, con_personas=True)
        frame = self._dibujar_circulo_indicador(frame, self.pos_destino, "DESTINO", anim_frame, w_f, h_f, transparente=True)

        # 4. TUTORIAL (GUANTE)
        if self.estado_juego == 'tutorial' and self.img_guante is not None and not self.dragging:
            tx = self.x_planchon + 0.05 + np.sin(anim_frame * 0.05) * 0.05
            frame = render_alfa(frame, self.img_guante, tx, self.y_planchon + 0.02, 0.15)

        # 4. INTERFAZ DE USUARIO (HUD LOCAL)
        frame = self._dibujar_hud(frame, w_f, h_f)

        if self.estado_juego == 'anuncio_inicio':
            frame = self._dibujar_anuncio_inicio(frame, w_f, h_f)

        if self.completado:
            frame = self._dibujar_felicitaciones(frame, w_f, h_f)

        return frame

    def _dibujar_circulo_indicador(self, frame, pos, texto, anim_frame, w, h, transparente=False, con_personas=False):
        # Dibujar iconos de personas esperando en la orilla
        if texto == "ORIGEN" and self.pasajeros_esperando > 0:
            num_iconos = self.pasajeros_esperando // 3
            for i in range(num_iconos):
                ix = pos[0] + (i - (num_iconos-1)/2) * 0.06
                iy = pos[1] - 0.08 + np.sin(anim_frame*0.1 + i)*0.005
                frame = render_alfa(frame, self.img_icon_personas, ix, iy, 0.10) # Más grande en la orilla
        return frame

    def _dibujar_trayecto_guiado(self, frame, anim_frame, w, h):
        # Línea diagonal punteada sutil
        p1 = (int(self.pos_origen[0]*w), int(self.pos_origen[1]*h))
        p2 = (int(self.pos_destino[0]*w), int(self.pos_destino[1]*h))
        # cv2.line(frame, p1, p2, (200, 200, 200), 1, cv2.LINE_AA) # Línea borrada visualmente

    def _dibujar_hud(self, frame, w_f, h_f):
        # HUD Expandido para botones
        frame = apply_glassmorphism(frame, int(w_f*0.1), int(h_f*0.84), int(w_f*0.9), int(h_f*0.96), blur_strength=15, alpha=0.4)
        
        # --- BOTONES DE MOVIMIENTO (DERECHA) ---
        # Flecha Arriba
        apply_glassmorphism(frame, int(w_f*0.55), int(h_f*0.86), int(w_f*0.65), int(h_f*0.94), alpha=0.6)
        frame = dibujar_texto_utf8(frame, "↑", (int(w_f*0.59), int(h_f*0.87)), 30, (0, 0, 0))
        
        # Flecha Abajo
        apply_glassmorphism(frame, int(w_f*0.67), int(h_f*0.86), int(w_f*0.77), int(h_f*0.94), alpha=0.6)
        frame = dibujar_texto_utf8(frame, "↓", (int(w_f*0.71), int(h_f*0.87)), 30, (0, 0, 0))

        # --- BOTÓN DE ACCIÓN (CONTEXTUAL) ---
        dist_origen = np.sqrt((self.x_planchon - self.pos_origen[0])**2 + (self.y_planchon - self.pos_origen[1])**2)
        dist_destino = np.sqrt((self.x_planchon - self.pos_destino[0])**2 + (self.y_planchon - self.pos_destino[1])**2)
        
        btn_action_text = ""
        btn_color = (100, 100, 100)
        
        if dist_origen < 0.05 and self.pasajeros_esperando > 0:
            btn_action_text = "EMBARCAR"
            btn_color = (0, 200, 0)
        elif dist_destino < 0.05 and self.pasajeros_a_bordo > 0:
            btn_action_text = "DESEMBARCAR"
            btn_color = (0, 100, 255)

        if btn_action_text:
            apply_glassmorphism(frame, int(w_f*0.26), int(h_f*0.86), int(w_f*0.50), int(h_f*0.94), alpha=0.8, border_color=btn_color)
            frame = dibujar_texto_utf8(frame, btn_action_text, (int(w_f*0.28), int(h_f*0.88)), 20, (0, 0, 0))

        # Mensaje de estado y progreso
        frame = dibujar_texto_utf8(frame, self.estado_mensajes, (int(w_f*0.12), int(h_f*0.845)), 16, (0, 0, 0))
        
        prog_w = int(w_f * 0.1)
        bx, by = int(w_f * 0.79), int(h_f * 0.88)
        cv2.rectangle(frame, (bx, by), (bx + prog_w, by + 10), (50, 50, 50), -1)
        actual_w = int(prog_w * (self.viajes_completados / self.objetivo_viajes))
        cv2.rectangle(frame, (bx, by), (bx + actual_w, by + 10), (0, 255, 150), -1)
        frame = dibujar_texto_utf8(frame, f"{self.viajes_completados}/{self.objetivo_viajes}", (bx + prog_w + 5, by - 5), 12, (0, 0, 0))
        
        return frame

    def _dibujar_anuncio_inicio(self, frame, w_f, h_f):
        overlay = frame.copy()
        cv2.rectangle(overlay, (0,0), (w_f, h_f), (0,0,0), -1)
        frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)
        
        msg = "TRANSPORTA A LOS TURISTAS"
        tw, _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
        frame = dibujar_texto_utf8(frame, msg, (w_f//2 - tw//2, h_f//2 - 40), 32, (0, 255, 100))
        frame = dibujar_texto_utf8(frame, "Lleva a todos a su destino para ganar monedas", (w_f//2 - 190, h_f//2 + 20), 18, (255, 255, 255))
        frame = dibujar_texto_utf8(frame, "(Toca la pantalla para comenzar)", (w_f//2 - 125, h_f//2 + 70), 14, (200, 200, 200))
        return frame

    def _dibujar_felicitaciones(self, frame, w_f, h_f):
        overlay = frame.copy()
        cv2.rectangle(overlay, (0,0), (w_f, h_f), (0,0,0), -1)
        frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)
        
        msg = "¡MISIÓN CUMPLIDA CAPITÁN!"
        tw, _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
        frame = dibujar_texto_utf8(frame, msg, (w_f//2 - tw//2, h_f//2 - 40), 32, (0, 255, 100))
        frame = dibujar_texto_utf8(frame, "Has ganado monedas por tu labor turística", (w_f//2 - 180, h_f//2 + 20), 18, (255, 255, 255))
        return frame

    def obtener_recompensa(self):
        return 250 # Recompensa aumentada por la dificultad profesional