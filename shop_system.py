from utils import load_ui_asset

class ShopSystem:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.monedas = 0
        self.tienda_abierta = False
        self.atuendo_actual = "original"
        self.outfits_comprados = ["original"]
        self.outfits_disponibles = [
            {"id": "original", "nombre": "Original", "precio": 0},
            {"id": "elegante", "nombre": "De Gala", "precio": 100},
            {"id": "explorador", "nombre": "Monteriano", "precio": 150},
            {"id": "pupi", "nombre": "Pupi", "precio": 200}
        ]

        # Cargar icono de tienda
        self.btn_tienda = load_ui_asset('shop.png', self.base_dir)
        self.btn_moneda = load_ui_asset('coin.png', self.base_dir)

    def add_coins(self, amount):
        self.monedas += amount
        print(f"  [SHOP] Monedas añadidas: {amount}. Total: {self.monedas}")

    def buy_outfit(self, outfit_id):
        pass # Lógica de compra se manejará en App.mouse_callback