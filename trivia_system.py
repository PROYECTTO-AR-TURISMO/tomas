class TriviaSystem:
    def __init__(self):
        self.trivia_errores = [] # Para rastrear clics incorrectos en la trivia
        self.trivia_acierto = None # Para marcar la respuesta correcta elegida
        self.trivia_opciones = [1976, 1986, 1938, 1900] # Configuración de Trivia para el Paso 5 (Alineada con la imagen de fondo proporcionada)
        self.trivia_opciones_fase2 = ["Francisco de Miranda", "Gabriel García Márquez", "Policarpa Salavarrieta", "Justo Manuel Triviña"]
        self.trivia_fase = 1 # 1: Año, 2: Autor
        self.input_texto = "" # Para almacenar lo que el usuario escribe

    def check_answer_phase1(self, selected_year):
        return selected_year == 1938

    def check_answer_phase2(self, selected_name):
        return selected_name == "Justo Manuel Triviña"

    def record_error(self, incorrect_answer):
        if incorrect_answer not in self.trivia_errores:
            self.trivia_errores.append(incorrect_answer)

    def reset_trivia(self):
        self.trivia_fase = 1
        self.input_texto = ""
        self.trivia_errores = []
        self.trivia_acierto = None

    def get_current_options(self):
        return self.trivia_opciones if self.trivia_fase == 1 else self.trivia_opciones_fase2