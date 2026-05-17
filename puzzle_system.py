import cv2
import numpy as np
import random

def crear_mascara_pieza(alto, ancho, config, off_x, off_y, pw, ph):
    """
    Genera una máscara binaria para una pieza de puzzle realista.
    config: [arriba, derecha, abajo, izquierda] -> 1: saliente, -1: hueco, 0: plano.
    off_x, off_y: desplazamiento de la pieza base dentro del recorte extendido.
    """
    mask = np.zeros((alto, ancho), dtype=np.uint8)
    
    # Base rectangular: La pieza real ocupa de (off_x, off_y) con tamaño (pw, ph)
    cv2.rectangle(mask, (off_x, off_y), (off_x + pw - 1, off_y + ph - 1), 255, -1)
    
    # Radio de los conectores basado en el tamaño estándar de la pieza
    r = int(min(pw, ph) * 0.2)
    
    # Dibujar conectores según la configuración
    if config[0] != 0: # Arriba
        cv2.circle(mask, (off_x + pw // 2, off_y), r, 255 if config[0] == 1 else 0, -1)
    if config[1] != 0:
        cv2.circle(mask, (off_x + pw, off_y + ph // 2), r, 255 if config[1] == 1 else 0, -1)
    if config[2] != 0:
        cv2.circle(mask, (off_x + pw // 2, off_y + ph), r, 255 if config[2] == 1 else 0, -1)
    if config[3] != 0:
        cv2.circle(mask, (off_x, off_y + ph // 2), r, 255 if config[3] == 1 else 0, -1)
        
    return mask

class PuzzlePiece:
    """Representa una pieza individual del rompecabezas."""
    def __init__(self, img, x, y, correct_rel_x, correct_rel_y):
        self.img = img
        self.x = float(x)
        self.y = float(y)
        self.w = img.shape[1]
        self.h = img.shape[0]
        self.correct_rel_x = correct_rel_x
        self.correct_rel_y = correct_rel_y

    def is_hit(self, x, y):
        """Verifica si un punto (x, y) está sobre la parte opaca de la pieza."""
        if self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h:
            lx, ly = int(x - self.x), int(y - self.y)
            if 0 <= ly < self.h and 0 <= lx < self.w:
                # Comprobar canal alfa para precisión en formas de puzzle
                return self.img[ly, lx, 3] > 0
        return False

class PuzzleSystem:
    def __init__(self):
        self.piezas = []
        self.selected_piece = None
        self.offset_x, self.offset_y = 0, 0
        self.activo = False
        self.completado = False
        self.centro_target = (0, 0)
        self.w_puzzle, self.h_puzzle = 0, 0
        self.img_guia = None # Imagen fantasma de referencia

    def inicializar_puzzle(self, imagen, filas=3, cols=3):
        """Divide la imagen en piezas con formas de puzzle coherentes."""
        if imagen is None: return
        # Redimensionar la imagen original para que sea más pequeña (45% del original)
        imagen = cv2.resize(imagen, None, fx=0.45, fy=0.45, interpolation=cv2.INTER_AREA)
        
        self.piezas = []
        self.activo = True
        self.completado = False
        
        h_img, w_img = imagen.shape[:2]
        if imagen.shape[2] == 3:
            imagen = cv2.cvtColor(imagen, cv2.COLOR_BGR2BGRA)
        
        # Asegurar que la imagen sea 100% opaca antes de aplicar la máscara del puzzle
        imagen[:, :, 3] = 255

        # Crear imagen de guía (fantasma) con opacidad muy baja (20%) para ayudar al usuario
        self.img_guia = imagen.copy()
        self.img_guia[:, :, 3] = (self.img_guia[:, :, 3] * 0.2).astype(np.uint8)

        pw, ph = w_img // cols, h_img // filas
        mh, mw = ph // 4, pw // 4 # Márgenes para los encajes
        self.w_puzzle = w_img
        self.h_puzzle = h_img
        
        # Generar matriz de conectores coherentes (1: saliente, -1: hueco)
        configs = np.zeros((filas, cols, 4), dtype=int)
        for r in range(filas):
            for c in range(cols):
                if r > 0: configs[r, c, 0] = -configs[r-1, c, 2] # Arriba es opuesto al abajo del vecino
                if c > 0: configs[r, c, 3] = -configs[r, c-1, 1] # Izquierda es opuesto al derecha del vecino
                if r < filas - 1: configs[r, c, 2] = random.choice([1, -1])
                if c < cols - 1: configs[r, c, 1] = random.choice([1, -1])

        for r in range(filas):
            for c in range(cols):
                # Recorte extendido para capturar los salientes que sobresalen de la cuadrícula
                x1, y1 = max(0, c*pw - mw), max(0, r*ph - mh)
                x2, y2 = min(w_img, (c+1)*pw + mw), min(h_img, (r+1)*ph + mh)
                img_pieza = imagen[y1:y2, x1:x2].copy()
                
                # Calcular dónde queda la pieza "base" dentro del recorte extendido
                off_x = c * pw - x1
                off_y = r * ph - y1

                # Aplicar máscara de forma realista
                mask = crear_mascara_pieza(y2-y1, x2-x1, configs[r, c], off_x, off_y, pw, ph)
                img_pieza[:, :, 3] = cv2.bitwise_and(img_pieza[:, :, 3], mask)
                
                # Dibujar contornos para visibilidad
                cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(img_pieza, cnts, -1, (255, 255, 255, 255), 1)

                # Rango de aparición más seguro para evitar que las piezas salgan de la pantalla
                px = random.randint(50, 250)
                py = random.randint(150, 400)
                self.piezas.append(PuzzlePiece(img_pieza, px, py, x1, y1))
        
        # Desordenar piezas al inicio
        random.shuffle(self.piezas)

    def manejar_mouse(self, event, x, y):
        """Gestiona el arrastre de piezas para mouse y tacto."""
        if event == cv2.EVENT_LBUTTONDOWN:
            # Buscar pieza de arriba hacia abajo para seleccionar la que esté al frente
            for p in reversed(self.piezas):
                # Si la pieza ya está encajada en su sitio correcto, no permitir volver a moverla
                tx = self.centro_target[0] - (self.w_puzzle // 2) + p.correct_rel_x
                ty = self.centro_target[1] - (self.h_puzzle // 2) + p.correct_rel_y
                if abs(p.x - tx) < 3 and abs(p.y - ty) < 3:
                    continue
                
                if p.is_hit(x, y):
                    self.selected_piece = p
                    self.offset_x = float(x - p.x)
                    self.offset_y = float(y - p.y)
                    # Mover al final de la lista para que se renderice encima de las demás
                    self.piezas.remove(p)
                    self.piezas.append(p)
                    break

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.selected_piece:
                self.selected_piece.x = x - self.offset_x
                self.selected_piece.y = y - self.offset_y

        elif event == cv2.EVENT_LBUTTONUP:
            if self.selected_piece:
                # Snap a posición correcta
                tx = self.centro_target[0] - (self.w_puzzle // 2) + self.selected_piece.correct_rel_x
                ty = self.centro_target[1] - (self.h_puzzle // 2) + self.selected_piece.correct_rel_y
                
                dist = np.sqrt((self.selected_piece.x - tx)**2 + (self.selected_piece.y - ty)**2)
                if dist < 50: # Rango de snapping más amplio para que encajen con facilidad
                    self.selected_piece.x = tx
                    self.selected_piece.y = ty
                
                self.selected_piece = None
                self.verificar_progreso()

    def verificar_progreso(self):
        """Verifica si el puzzle se ha completado."""
        for p in self.piezas:
            tx = self.centro_target[0] - (self.w_puzzle // 2) + p.correct_rel_x
            ty = self.centro_target[1] - (self.h_puzzle // 2) + p.correct_rel_y
            if abs(p.x - tx) > 5 or abs(p.y - ty) > 5:
                return
        if len(self.piezas) > 0:
            self.completado = True