from utils import load_ui_asset

class ShopSystem:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.monedas = 0
        self.tienda_abierta = False
        self.marco_actual = "ninguno"
        self.marcos_comprados = ["ninguno"]
        self.outfits_disponibles = [
            {"id": "ninguno", "nombre": "Sin Marco", "precio": 0},
            {"id": "iguana", "nombre": "Marco Iguana", "precio": 100},
            {"id": "ardilla", "nombre": "Marco Ardilla", "precio": 150},
            {"id": "perezoso", "nombre": "Marco Perezoso", "precio": 200}
        ]

        # Cargar icono de tienda
        self.btn_tienda = load_ui_asset('shop.png', self.base_dir)
        self.btn_moneda = load_ui_asset('coin.png', self.base_dir)

    def add_coins(self, amount):
        self.monedas += amount
        print(f"  [SHOP] Monedas añadidas: {amount}. Total: {self.monedas}")

    def buy_outfit(self, outfit_id):
        pass # Lógica de compra se manejará en App.mouse_callback