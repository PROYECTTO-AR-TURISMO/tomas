import cv2
import numpy as np
import os
from PIL import Image, ImageSequence, ImageDraw, ImageFont

# --- CLASE PARA MANEJAR ANIMACIONES GIF ---
class GifHandler:
    """Extrae y gestiona los frames de archivos GIF para OpenCV."""
    def __init__(self, filepath):
        self.frames = []
        self.current_frame = 0
        self.paused = False
        self.load_gif(filepath)

    def load_gif(self, filepath):
        if not os.path.exists(filepath):
            return
        try:
            pil_img = Image.open(filepath)
            for frame in ImageSequence.Iterator(pil_img):
                frame_rgba = frame.convert('RGBA')
                opencv_frame = cv2.cvtColor(np.array(frame_rgba), cv2.COLOR_RGBA2BGRA)
                
                # Tratamiento de transparencia para GIFs sin canal alfa nativo
                if not self.tiene_transparencia_real(opencv_frame):
                    gray = cv2.cvtColor(opencv_frame, cv2.COLOR_BGRA2GRAY)
                    _, alpha_mask = cv2.threshold(gray, 5, 255, cv2.THRESH_BINARY)
                    opencv_frame[:, :, 3] = alpha_mask
                
                self.frames.append(opencv_frame)
            if len(self.frames) > 0:
                print(f"  [OK] GIF cargado: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"  [ERROR] Al cargar GIF {filepath}: {e}")

    def tiene_transparencia_real(self, frame):
        return not np.all(frame[:, :, 3] == 255)

    def get_frame(self):
        if not self.frames: return None
        if self.paused:
            return self.frames[0]
        if self.current_frame < len(self.frames) - 1:
            # Avanzamos 2 cuadros por ciclo para aumentar la velocidad (Velocidad x2)
            self.current_frame = min(len(self.frames) - 1, self.current_frame + 2)
        return self.frames[self.current_frame]

# --- FUNCIÓN DE RENDERIZADO CON CANAL ALFA ---
def render_alfa(fondo, img, x_porcentaje, y_porcentaje, escala):
    if img is None or escala <= 0: return fondo
    try:
        h_f, w_f = fondo.shape[:2]
        # Optimizamos: Usar INTER_LINEAR si la escala es > 1, INTER_AREA si es < 1
        interp = cv2.INTER_AREA if escala < 1.0 else cv2.INTER_LINEAR
        img_res = cv2.resize(img, None, fx=escala, fy=escala, interpolation=interp)
        h, w, c = img_res.shape
        
        x, y = int(w_f * x_porcentaje), int(h_f * y_porcentaje)
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_f, x + w), min(h_f, y + h)
        if x1 >= x2 or y1 >= y2: return fondo
        
        img_rec = img_res[y1-y:y2-y, x1-x:x2-x]

        # VECTORIZACIÓN NUMPY (Sustituye el loop for lento) con chequeo de canal alfa
        if img_rec.shape[2] == 4:
            alpha = (img_rec[:, :, 3] / 255.0)[:, :, np.newaxis]
            blended = (alpha * img_rec[:, :, :3] + (1.0 - alpha) * fondo[y1:y2, x1:x2]).astype(np.uint8)
            fondo[y1:y2, x1:x2] = blended
        else:
            # Si no hay canal alfa, copiamos la imagen directamente
            fondo[y1:y2, x1:x2] = img_rec[:, :, :3]

        return fondo
    except Exception as e:
        return fondo

def dibujar_texto_utf8(frame, texto, posicion, tamano, color_bgr):
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    try:
        font = ImageFont.truetype("arial.ttf", tamano)
    except:
        font = ImageFont.load_default()
    color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
    draw.text(posicion, texto, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def load_ui_asset(nombre, base_dir, sitio_id=None):
    rutas = []
    if sitio_id:
        rutas.append(os.path.join(base_dir, 'assets', 'sitios', sitio_id, nombre))
    rutas.extend([os.path.join(base_dir, 'assets', 'ui', nombre), os.path.join(base_dir, 'ui', nombre), os.path.join(base_dir, nombre)])
    for r in rutas:
        if os.path.exists(r): return cv2.imread(r, cv2.IMREAD_UNCHANGED)
    return None

def dibujar_sombra(frame, cx, cy, rx, ry, alpha=0.35, color=(20, 20, 20)):
    if rx <= 0 or ry <= 0: return
    overlay = frame.copy()
    cv2.ellipse(overlay, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

def draw_rounded_rect(overlay, top_left, bottom_right, color, radius, thickness, alpha=1.0):
    x1, y1 = top_left
    x2, y2 = bottom_right
    
    # Creamos una copia para el dibujado si necesitamos mezcla alfa
    draw_target = overlay.copy() if alpha < 1.0 else overlay

    # Las elipses sí aceptan -1 para rellenar los sectores de las esquinas
    cv2.ellipse(draw_target, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness)
    cv2.ellipse(draw_target, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness)
    cv2.ellipse(draw_target, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness)
    cv2.ellipse(draw_target, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness)
    
    # Las líneas fallan con -1, solo se dibujan si el grosor es positivo
    if thickness > 0:
        cv2.line(draw_target, (x1 + radius, y1), (x2 - radius, y1), color, thickness)
        cv2.line(draw_target, (x2, y1 + radius), (x2, y2 - radius), color, thickness)
        cv2.line(draw_target, (x1 + radius, y2), (x2 - radius, y2), color, thickness)
        cv2.line(draw_target, (x1, y1 + radius), (x1, y2 - radius), color, thickness)

    if thickness == -1:
        cv2.rectangle(draw_target, (x1 + radius, y1), (x2 - radius, y2), color, -1)
        cv2.rectangle(draw_target, (x1, y1 + radius), (x2, y2 - radius), color, -1)

    # Si hay transparencia, mezclamos con la imagen original
    if alpha < 1.0:
        cv2.addWeighted(draw_target, alpha, overlay, 1.0 - alpha, 0, overlay)

def apply_glassmorphism(frame, x1, y1, x2, y2, blur_strength=15, alpha=0.3, border_color=(255, 255, 255), border_thickness=2, border_radius=15):
    sub = frame[y1:y2, x1:x2].copy()
    sub = cv2.GaussianBlur(sub, (blur_strength*2+1, blur_strength*2+1), 0)
    overlay = sub.copy()
    # Dibujamos el fondo blanco también redondeado para que coincida con el borde
    draw_rounded_rect(overlay, (0, 0), (x2 - x1, y2 - y1), (255, 255, 255), border_radius, -1)
    res = cv2.addWeighted(overlay, alpha, sub, 1.0 - alpha, 0)
    draw_rounded_rect(res, (0,0), (x2-x1, y2-y1), border_color, border_radius, border_thickness)
    frame[y1:y2, x1:x2] = res
    return frame