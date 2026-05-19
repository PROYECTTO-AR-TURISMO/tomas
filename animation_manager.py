import numpy as np
import cv2
import random
import os
from utils import load_ui_asset

class Particle:
    def __init__(self, x, y, color, size, vx, vy, life, p_type="normal", img=None):
        self.x = x
        self.y = y
        self.color = color
        self.size = size
        self.vx = vx
        self.vy = vy
        self.life = life # Vida útil de la partícula
        self.alpha = 255 # Opacidad inicial
        self.p_type = p_type
        self.img = img
        self.angle = random.uniform(0, 360)
        self.rot_speed = random.uniform(-5, 5)

    def update(self):
        if self.p_type == "firefly":
            self.vx += random.uniform(-0.1, 0.1)
            self.vy += random.uniform(-0.1, 0.1)
        elif self.p_type == "leaf":
            # Simular turbulencia: pequeños cambios aleatorios en la trayectoria
            self.vx += random.uniform(-0.05, 0.05)
            self.vy += random.uniform(-0.15, 0.15)
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        self.alpha = max(0, self.alpha - (255 / 60)) # Desvanecer con el tiempo
        self.angle += self.rot_speed

    def is_alive(self):
        return self.life > 0 and self.alpha > 0

    def draw(self, overlay):
        """Dibuja la partícula en una capa de overlay para mayor eficiencia."""
        if self.is_alive():
            if self.p_type == "leaf" and self.img is not None:
                # Renderizado de imagen de hoja con rotación y escala
                h, w = self.img.shape[:2]
                s = self.size / 10.0  # Escalar imagen según el tamaño de la partícula
                nw, nh = int(w * s), int(h * s)
                if nw <= 0 or nh <= 0: return
                
                # Redimensionar y rotar
                leaf_res = cv2.resize(self.img, (nw, nh))
                M = cv2.getRotationMatrix2D((nw//2, nh//2), self.angle, 1.0)
                leaf_rot = cv2.warpAffine(leaf_res, M, (nw, nh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
                
                # Coordenadas de destino con soporte para recortes en los bordes
                H, W = overlay.shape[:2]
                ix, iy = int(self.x - nw//2), int(self.y - nh//2)
                
                x1, x2 = max(0, ix), min(W, ix + nw)
                y1, y2 = max(0, iy), min(H, iy + nh)
                
                if x1 >= x2 or y1 >= y2: return
                
                # Región de interés de la hoja y del fondo
                leaf_roi = leaf_rot[y1-iy : y2-iy, x1-ix : x2-ix]
                img_roi = overlay[y1:y2, x1:x2]
                
                # Mezcla alfa optimizada con NumPy
                alpha_s = (leaf_roi[:, :, 3] / 255.0)[:, :, np.newaxis]
                img_roi[:] = (alpha_s * leaf_roi[:, :, :3] + (1.0 - alpha_s) * img_roi).astype(np.uint8)
            else:
                cv2.circle(overlay, (int(self.x), int(self.y)), int(self.size), self.color, -1)

class AnimationManager:
    def __init__(self, base_dir=None):
        self.anim_frame = 0 # Contador global para todas las animaciones
        
        # Variables para interactividad de botones
        self.hover_sig_anim = 0.0  # 0.0 a 1.0 para suavizar la animación
        self.hover_back_anim = 0.0
        self.hover_salt_anim = 0.0
        self.hover_tienda_anim = 0.0

        # Animaciones de trivia
        self.hover_trivia_anims = [0.0, 0.0, 0.0, 0.0] # Animación para cada opción de la trivia
        self.hover_trivia_anims_2 = [0.0, 0.0, 0.0, 0.0] # Animación para la segunda trivia

        # Animación de mapa
        self.hover_mapa_anim = 0.0 # Efecto de fluido/hundimiento para el mapa
        self.hover_popup_anim = 0.0 # Animación para el efecto de onda del pop-up

        # Cinemática de selección
        self.cinematic_active = False
        self.cinematic_prog = 0.0 # 0.0 a 1.0
        self.cinematic_name = ""
        self.shop_panel_prog = 0.0 # 0.0 a 1.0 (para el slide)
        self.button_pulses = [] # Lista de (x, y, r, alpha)
        self.shop_scroll_y = 0 # Desplazamiento vertical del menú
        
        # Animación de Marco Decorativo
        self.frame_transition_alpha = 1.0 # 0.0 a 1.0

        # Cargar asset de hoja
        self.leaf_img = load_ui_asset('hoja.png', base_dir) if base_dir else None

        # Transiciones cinematográficas
        self.transition_active = False
        self.fade_alpha = 0.0 # 0.0 (transparente) a 1.0 (opaco)
        self.blur_amount = 0 # Fuerza del desenfoque
        self.transition_duration = 30 # frames
        self.transition_timer = 0

        # Sistema de partículas
        self.particles = []
        self.max_particles = 100 # Límite para optimización

    def update(self, mouse_x, mouse_y, show_leaves=False):
        self.anim_frame += 1
        self._update_transitions()
        self._update_cinematic()
        self._update_ui_anims()
        self._update_particles()
        # Suavizar transición del marco
        self.frame_transition_alpha = min(1.0, self.frame_transition_alpha + 0.05)
        self._generate_ambient_particles(show_leaves)

    def _generate_ambient_particles(self, show_leaves):
        # Luciérnagas constantes
        if random.random() < 0.05:
            self.add_firefly_particles(random.randint(0, 1280), random.randint(0, 720), 1)
        
        # Hojas con la brisa
        if show_leaves and random.random() < 0.15:
            self.add_leaf_particles(random.randint(-100, -20), random.randint(0, 600), random.randint(1, 3))

    def _update_cinematic(self):
        if self.cinematic_active:
            self.cinematic_prog = min(1.0, self.cinematic_prog + 0.02)
            if self.cinematic_prog >= 1.0:
                self.cinematic_active = False # Se desactiva al terminar
        else:
            self.cinematic_prog = max(0.0, self.cinematic_prog - 0.05)

    def start_cinematic(self, name):
        self.cinematic_active = True
        self.cinematic_prog = 0.0
        self.cinematic_name = name

    def _update_ui_anims(self):
        # Actualizar pulsos de botones
        self.button_pulses = [(x, y, r+2, a-10) for x, y, r, a in self.button_pulses if a > 0]

    def add_button_pulse(self, x, y):
        self.button_pulses.append([x, y, 5, 150])

    def _update_transitions(self):
        if self.transition_active:
            self.transition_timer += 1
            progress = self.transition_timer / self.transition_duration
            
            if progress < 0.5: # Fade out
                self.fade_alpha = progress * 2
                self.blur_amount = int(progress * 2 * 15) # Max blur 15
            else: # Fade in
                self.fade_alpha = 1.0 - ((progress - 0.5) * 2)
                self.blur_amount = int((1.0 - ((progress - 0.5) * 2)) * 15)
            
            if self.transition_timer >= self.transition_duration:
                self.transition_active = False
                self.fade_alpha = 0.0
                self.blur_amount = 0
                self.transition_timer = 0

    def start_transition(self):
        self.transition_active = True
        self.transition_timer = 0

    def _update_particles(self):
        # Eliminar partículas muertas
        self.particles = [p for p in self.particles if p.is_alive()]

        # Añadir nuevas partículas si hay espacio (partículas flotantes de fondo)
        if len(self.particles) < self.max_particles:
            if random.random() < 0.1: # Probabilidad de generar una nueva partícula
                x = random.randint(0, 1280)
                y = random.randint(0, 720)
                color = (random.randint(150, 255), random.randint(150, 255), random.randint(150, 255)) # Colores claros
                size = random.uniform(1, 3)
                vx = random.uniform(-0.5, 0.5)
                vy = random.uniform(-0.5, 0.5)
                life = random.randint(60, 180) # Larga vida
                self.particles.append(Particle(x, y, color, size, vx, vy, life))

        # Actualizar todas las partículas
        for p in self.particles:
            p.update()

    def add_coin_particles(self, x, y, count=10):
        for _ in range(count):
            color = (0, 215, 255) # Dorado
            size = random.uniform(2, 5)
            vx = random.uniform(-3, 3)
            vy = random.uniform(-5, -1)
            life = random.randint(30, 60)
            self.particles.append(Particle(x, y, color, size, vx, vy, life))

    def add_dust_particles(self, x, y, count=60):
        """Crea una explosión de polvo densa y visible."""
        for _ in range(count):
            color = (60, 90, 120) # Color tierra más denso (BGR)
            size = random.uniform(4, 12) # Partículas mucho más grandes
            vx = random.uniform(-6, 6) # Expansión lateral rápida
            vy = random.uniform(-4, -1) # El polvo salta hacia arriba
            life = random.randint(40, 90)
            self.particles.append(Particle(x, y, color, size, vx, vy, life))

    def add_firefly_particles(self, x, y, count=1):
        for _ in range(count):
            color = (150, 255, 255) # Amarillo neón
            size = random.uniform(1, 2)
            vx = random.uniform(-0.5, 0.5)
            vy = random.uniform(-0.5, 0.5)
            life = random.randint(100, 200)
            self.particles.append(Particle(x, y, color, size, vx, vy, life, "firefly"))

    def add_leaf_particles(self, x, y, count=1):
        for _ in range(count):
            color = (40, 100, 40) # Fallback verde
            size = random.uniform(0.3, 0.7) # Hojas más pequeñas solicitadas
            vx = random.uniform(5.0, 9.0)   # Velocidad base horizontal
            vy = random.uniform(-0.5, 0.5)  # Inclinación inicial leve
            life = random.randint(300, 500)
            self.particles.append(Particle(x, y, color, size, vx, vy, life, "leaf", self.leaf_img))

    def add_pin_glow_particles(self, x, y, count=5):
        for _ in range(count):
            color = (255, 255, 0) # Amarillo brillante
            size = random.uniform(1, 3)
            vx = random.uniform(-1, 1)
            vy = random.uniform(-1, 1)
            life = random.randint(10, 20)
            self.particles.append(Particle(x, y, color, size, vx, vy, life))

    def render_particles(self, frame):
        """Dibuja las partículas con mayor contraste para que sean visibles."""
        if not self.particles: return
        
        overlay = frame.copy()
        for p in self.particles:
            p.draw(overlay)
            
        # Aumentamos el peso del overlay para que las partículas se vean sólidas
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)