import cv2
import numpy as np
import os
from PIL import Image, ImageSequence

# --- CLASE PARA MANEJAR ANIMACIONES GIF ---
class GifHandler:
    """Extrae y gestiona los frames de archivos GIF para OpenCV."""
    def __init__(self, filepath):
        self.frames = []
        self.current_frame = 0
        self.load_gif(filepath)

    def load_gif(self, filepath):
        if not os.path.exists(filepath):
            return
        try:
            pil_img = Image.open(filepath)
            for frame in ImageSequence.Iterator(pil_img):
                frame_rgba = frame.convert('RGBA')
                opencv_frame = cv2.cvtColor(np.array(frame_rgba), cv2.COLOR_RGBA_BGRA)
                self.frames.append(opencv_frame)
            if len(self.frames) > 0:
                print(f"  [OK] GIF cargado: {os.path.basename(filepath)} ({len(self.frames)} frames)")
        except Exception as e:
            print(f"  [ERROR] Al cargar GIF {filepath}: {e}")

    def get_frame(self):
        if not self.frames: return None
        frame = self.frames[self.current_frame]
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        return frame

# --- FUNCIÓN DE RENDERIZADO CON CANAL ALFA ---
def render_alfa(fondo, img, x_porcentaje, y_porcentaje, escala):
    if img is None: return fondo
    try:
        h_f, w_f = fondo.shape[:2]
        img_res = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
        h, w, c = img_res.shape
        
        x = int(w_f * x_porcentaje)
        y = int(h_f * y_porcentaje)
        
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_f, x + w), min(h_f, y + h)
        
        if x1 >= x2 or y1 >= y2: return fondo
        
        img_rec = img_res[y1-y:y2-y, x1-x:x2-x]
        region_fondo = fondo[y1:y2, x1:x2]
        
        if c == 4:
            alpha = img_rec[:, :, 3] / 255.0
            for canal in range(3):
                region_fondo[:, :, canal] = (alpha * img_rec[:, :, canal] + 
                                            (1.0 - alpha) * region_fondo[:, :, canal])
        else:
            fondo[y1:y2, x1:x2] = img_rec[:, :, :3]
            
        return fondo
    except:
        return fondo

# --- CLASE PRINCIPAL DEL VISOR AR ---
class VisorTurismoAR:
    def __init__(self):
        # Determinamos la ruta absoluta de la carpeta donde está este script
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"\n[SISTEMA] Iniciando desde: {self.base_dir}")
        
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.detector = cv2.QRCodeDetector()
        
        self.guia_activo = False
        self.paso = 1
        self.max_pasos = 6
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None}
        
        # Intentar cargar UI desde múltiples ubicaciones posibles
        print("\n--- BUSCANDO BOTONES DE INTERFAZ ---")
        self.btn_sig = self._buscar_archivo_ui('btn_siguiente.png')
        self.btn_salt = self._buscar_archivo_ui('btn_saltar.png')

    def _buscar_archivo_ui(self, nombre):
        rutas_a_probar = [
            os.path.join(self.base_dir, 'assets', 'ui', nombre),
            os.path.join(self.base_dir, 'ui', nombre),
            os.path.join(self.base_dir, nombre)
        ]
        for ruta in rutas_a_probar:
            if os.path.exists(ruta):
                img = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    print(f"  [EXITO] Cargado: {ruta}")
                    return img
        print(f"  [AVISO] No se encontro: {nombre}")
        return None

    def cargar_activos_sitio(self, texto_qr):
        sitio_id = texto_qr.strip().lower()
        # Ruta absoluta hacia la carpeta del sitio
        path_sitio = os.path.join(self.base_dir, 'assets', 'sitios', sitio_id)
        
        print(f"\n--- CARGANDO ACTIVOS PARA: {sitio_id} ---")
        print(f"Buscando en: {path_sitio}")
        
        if not os.path.exists(path_sitio):
            print(f"  [ERROR] La carpeta '{sitio_id}' no existe en la ruta especificada.")
            return False
        
        self.activos = {'avatars': {}, 'burbujas': {}, 'foto_h': None}
        archivos = os.listdir(path_sitio)
        
        for i in range(1, self.max_pasos + 1):
            for f in archivos:
                f_low = f.lower()
                if f_low == f"avatar_{i}.gif":
                    self.activos['avatars'][i] = GifHandler(os.path.join(path_sitio, f))
                if f_low == f"burbuja_{i}.gif":
                    self.activos['burbujas'][i] = GifHandler(os.path.join(path_sitio, f))
        
        if 'historica.png' in [f.lower() for f in archivos]:
            self.activos['foto_h'] = cv2.imread(os.path.join(path_sitio, 'historica.png'), cv2.IMREAD_UNCHANGED)

        total = len(self.activos['avatars']) + len(self.activos['burbujas'])
        print(f"--- Carga completada ({total} elementos) ---")
        return True

    def mouse_callback(self, event, x, y, flags, param):
        h_f, w_f = param
        if event == cv2.EVENT_LBUTTONDOWN and self.guia_activo:
            # Botón Siguiente
            if x > w_f * 0.7 and y > h_f * 0.75:
                self.paso = (self.paso % self.max_pasos) + 1
                print(f"Siguiente -> Paso {self.paso}")
            # Botón Saltar
            elif x < w_f * 0.3 and y > h_f * 0.75:
                print("Guia finalizada.")
                self.guia_activo = False

    def run(self):
        cv2.namedWindow("VISOR_TURISMO_AR")
        
        while True:
            ret, frame = self.cap.read()
            if not ret: break
            
            frame = cv2.flip(frame, 1)
            h_f, w_f, _ = frame.shape
            cv2.setMouseCallback("VISOR_TURISMO_AR", self.mouse_callback, param=(h_f, w_f))

            if not self.guia_activo:
                # MODO ESCANEO
                cv2.rectangle(frame, (int(w_f*0.25), int(h_f*0.25)), (int(w_f*0.75), int(h_f*0.75)), (0, 255, 0), 2)
                cv2.putText(frame, "ESCANEE QR SITIO_1", (int(w_f*0.3), int(h_f*0.2)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                data, _, _ = self.detector.detectAndDecode(frame)
                if data:
                    if self.cargar_activos_sitio(data):
                        self.guia_activo, self.paso = True, 1
            else:
                # MODO AR
                # 1. Avatar
                av = self.activos['avatars'].get(self.paso)
                if av: frame = render_alfa(frame, av.get_frame(), 0.05, 0.35, 0.55)
                
                # 2. Burbuja
                bu = self.activos['burbujas'].get(self.paso)
                if bu: frame = render_alfa(frame, bu.get_frame(), 0.35, 0.05, 0.5)
                
                # 3. Foto Histórica
                if self.paso == self.max_pasos and self.activos['foto_h'] is not None:
                    frame = render_alfa(frame, self.activos['foto_h'], 0.65, 0.3, 0.3)

                # 4. Botones
                if self.btn_sig is not None:
                    frame = render_alfa(frame, self.btn_sig, 0.75, 0.8, 0.18)
                else:
                    cv2.rectangle(frame, (int(w_f*0.75), int(h_f*0.8)), (int(w_f*0.95), int(h_f*0.95)), (0,0,255), 2)
                    cv2.putText(frame, "SIGUIENTE", (int(w_f*0.77), int(h_f*0.88)), 0, 0.5, (0,0,255), 1)

                if self.btn_salt is not None:
                    frame = render_alfa(frame, self.btn_salt, 0.05, 0.8, 0.18)
                else:
                    cv2.rectangle(frame, (int(w_f*0.05), int(h_f*0.8)), (int(w_f*0.25), int(h_f*0.95)), (0,0,255), 2)
                    cv2.putText(frame, "SALTAR", (int(w_f*0.08), int(h_f*0.88)), 0, 0.5, (0,0,255), 1)

                cv2.putText(frame, f"PASO {self.paso} / {self.max_pasos}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.imshow("VISOR_TURISMO_AR", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = VisorTurismoAR()
    app.run()