# -*- coding: utf-8 -*-
"""
Micro Calabozos y Chatbots v2.1 (Portfolio Version)

Un simple juego de rol de texto estilo chatbot implementado con Python y Tkinter.
Utiliza una IA (a través de HybridAIConnector) para actuar como Dungeon Master (DM),
generando narrativas y respondiendo a las acciones del jugador.

Características:
- Interfaz gráfica de usuario (GUI) con Tkinter y ttk para un look mejorado.
- Conexión a APIs de LLM (OpenAI GPT-3.5 Turbo, Gemini, DeepSeek) mediante HybridAIConnector.
- Rotación automática entre APIs configuradas para distribuir carga/costo.
- Sistema básico de personaje con HP, Stats (STR, DEX), Nivel y XP.
- Modificación de estado (HP, XP, Items) basada en tags parseados de la respuesta del DM.
- Sistema de subida de nivel simple.
- Inventario básico con comandos /inv y /usar (para pociones).
- Persistencia del juego (guardado/cargado automático y manual) usando JSON.
- Manejo de llamadas API asíncronas usando threading y queue para mantener la GUI responsiva.
- Comandos de jugador simples (incluyendo /ayuda).

Dependencias (instalar con pip):
- requests
- google-generativeai
- openai
- python-dotenv

Setup:
1. Guarda este archivo como 'micro_rpg_chatbot_v2_portfolio.py'.
2. Asegúrate de tener 'api_connectors.py' (la versión con rotación) en la misma carpeta.
3. Crea un archivo '.env' en la misma carpeta y añade tus claves API:
   OPENAI_API_KEY=tu_clave_openai
   GEMINI_API_KEY=tu_clave_gemini
   DEEPSEEK_API_KEY=tu_clave_deepseek
   (Necesitas al menos una clave para que la IA funcione).
4. Ejecuta el script: python micro_rpg_chatbot_v2_portfolio.py
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, PhotoImage, simpledialog
import tkinter.ttk as ttk # Usar themed widgets
import random
import time
import os
import json
import re
import threading
import queue

# Importar el conector de API personalizado
try:
    from api_connectors import HybridAIConnector
except ImportError:
    # Mostrar error si el archivo del conector no se encuentra
    root = tk.Tk()
    root.withdraw() # Ocultar la ventana raíz principal de Tkinter
    messagebox.showerror("Error de Importación",
                         "No se encontró el archivo 'api_connectors.py'.\n"
                         "Asegúrate de que esté en la misma carpeta que este script.")
    exit()
except Exception as e:
     root = tk.Tk()
     root.withdraw()
     messagebox.showerror("Error de Importación", f"Error al importar api_connectors: {e}")
     exit()

# --- Constantes y Configuración ---
SAVE_FILE = "rpg_save.json" # Nombre del archivo de guardado

# --- Estado del Juego (Valores por defecto para juego nuevo) ---
DEFAULT_PLAYER_STATS = {
    "HP": 15, "MaxHP": 15, "STR": 10, "DEX": 10,
    "Level": 1, "XP": 0, "XP_Next_Level": 100,
    "Notas": "Un aventurero novato."
}
player_stats = DEFAULT_PLAYER_STATS.copy() # Estado actual del jugador
player_inventory = [] # Inventario actual
game_context = ["Inicio de la Aventura"] # Historial reciente para la IA
game_over = False # Flag para saber si el juego terminó

# --- Variables Globales ---
connector = None # Instancia del conector API
connector_status = "OFFLINE (Inicializando...)" # Estado visible de la API
window = None # Ventana principal de Tkinter
log_area = None # Widget ScrolledText para mostrar el juego
# Labels para mostrar estado
hp_label = None
stats_label = None
xp_label = None
connector_label = None
# Widgets de entrada
input_entry = None
send_button = None
# Cola para comunicación entre hilos y GUI
gui_queue = queue.Queue()

# --- DEFINICIÓN DE FUNCIONES ---

def run_in_thread(target_func, *args, **kwargs):
    """
    Ejecuta una función objetivo en un hilo separado (daemon).

    Args:
        target_func: La función a ejecutar en el hilo.
        *args: Argumentos posicionales para target_func.
        **kwargs: Argumentos clave para target_func.
    """
    thread = threading.Thread(target=target_func, args=args, kwargs=kwargs)
    thread.daemon = True # Permite que el programa termine aunque el hilo siga activo
    thread.start()

def add_log(message, tag=None):
    """
    Añade un mensaje al área de log principal (ScrolledText) de forma segura.
    Debe ser llamado desde el hilo principal o poniendo el mensaje en la gui_queue.

    Args:
        message (str): El texto a añadir.
        tag (str, optional): Un tag para aplicar formato especial (ej: 'player', 'dm').
                               Defaults to None.
    """
    try:
        # Asegurarse que la ventana y el widget existen antes de interactuar
        if window and window.winfo_exists() and log_area:
            log_area.config(state=tk.NORMAL) # Habilitar escritura

            # Aplicar formato basado en tags
            if tag == "player": log_area.insert(tk.END, "Tú: ", ("player_tag", "bold")); log_area.insert(tk.END, message + "\n")
            elif tag == "dm": log_area.insert(tk.END, "DM: ", ("dm_tag", "bold")); log_area.insert(tk.END, message + "\n\n", ("dm_text"))
            elif tag == "roll": log_area.insert(tk.END, message + "\n", ("roll_tag", "italic"))
            elif tag == "system": log_area.insert(tk.END, message + "\n", ("system_tag", "italic", "grey"))
            elif tag == "levelup": log_area.insert(tk.END, message + "\n", ("levelup_tag", "bold", "gold"))
            else: log_area.insert(tk.END, message + "\n") # Sin tag especial

            log_area.see(tk.END) # Hacer scroll automático hacia el final
            log_area.config(state=tk.DISABLED) # Deshabilitar escritura
    except tk.TclError:
        pass # Ignorar error si la ventana se cierra durante la actualización
    except AttributeError:
        # Fallback si la GUI no está completamente lista (improbable con queue)
        print(f"Log ({tag or 'System'}): {message}")

def update_status_display():
    """Actualiza las etiquetas de estado (HP, Stats, XP, API) en la GUI."""
    try:
        if window and window.winfo_exists():
            # Actualizar cada Label con la información actual de player_stats
            hp_label.config(text=f"HP: {player_stats.get('HP', '?')}/{player_stats.get('MaxHP', '?')}")
            other_stats = f"STR: {player_stats.get('STR', '?')} | DEX: {player_stats.get('DEX', '?')}"
            stats_label.config(text=other_stats)
            xp_label.config(text=f"Lvl: {player_stats.get('Level', '?')} | XP: {player_stats.get('XP', '?')}/{player_stats.get('XP_Next_Level', '?')}")
            connector_label.config(text=f"API: {connector_status}")
    except tk.TclError: pass
    except AttributeError: pass # Ignorar si los widgets no existen aún

def set_input_state(state):
    """Habilita o deshabilita el campo de entrada y el botón de enviar."""
    try:
        if window and window.winfo_exists():
            if input_entry: input_entry.config(state=state)
            if send_button: send_button.config(state=state)
    except tk.TclError: pass
    except AttributeError: pass

def initialize_connector():
    """
    Inicializa el conector de APIs de forma síncrona.
    Intenta cargar una partida guardada antes de inicializar.
    Pone tareas en la cola para actualizar la GUI y empezar el juego.
    """
    global connector, connector_status

    # Intentar cargar partida guardada primero
    gui_queue.put(("log", "Intentando cargar partida guardada..."))
    load_game() # Esta función pondrá logs en la cola sobre el resultado

    # Inicializar el conector
    gui_queue.put(("log", "Inicializando conector IA (puede tardar)..."))
    connector_status = "OFFLINE (Inicializando...)" # Estado inicial

    try:
        connector = HybridAIConnector() # Usar la clase del archivo importado
        active_providers = connector.get_active_providers()
        if not active_providers:
            # No hay APIs configuradas
            connector = None
            connector_status = "OFFLINE (No hay proveedores activos. Revisa .env)"
        else:
            # APIs configuradas, se usará rotación
            connector_status = f"ONLINE (Rotando: {', '.join(active_providers)})"

    except Exception as e:
        # Error durante la inicialización del conector
        connector = None
        connector_status = f"OFFLINE (Error: {e})"
        gui_queue.put(("log", f"ERROR grave inicializando conector: {e}"))

    # Informar estado final y pedir actualización de GUI
    gui_queue.put(("log", f"Estado final del conector: {connector_status}"))
    gui_queue.put(("update_status", None)) # Tarea para actualizar labels

    # Si no se cargó una partida terminada y el contexto está vacío (nuevo juego), empezar
    if not game_over and len(game_context) <= 1:
         gui_queue.put(("start_game", None)) # Tarea para generar escena inicial
    elif not game_over: # Si se cargó partida y no está terminada
         gui_queue.put(("log", "Partida cargada reanudada."))
         gui_queue.put(("set_input_state", tk.NORMAL)) # Habilitar input
    else: # Si se cargó partida terminada
        gui_queue.put(("set_input_state", tk.DISABLED))


def ask_dm_ai(prompt: str, callback):
    """
    Envía una petición a la IA (actuando como DM) en un hilo secundario.
    Construye un prompt detallado con contexto, stats e instrucciones.
    Pone la tupla (callback, resultado) en la gui_queue al terminar.

    Args:
        prompt (str): La TAREA ACTUAL o acción del jugador a procesar por la IA.
        callback (callable): La función a llamar (en el hilo principal) cuando se recibe la respuesta.
    """
    # Feedback visual inmediato en la GUI
    add_log("... DM está pensando ...", "italic")

    def generation_task():
        """Tarea ejecutada en el hilo secundario para llamar a la API."""
        result = None
        status = "offline"
        if connector:
            # Construir contexto y prompt completo
            context_str = "\n".join(game_context[-6:]) # Usar historial reciente
            inventory_str = ", ".join(player_inventory) if player_inventory else "Vacío"
            if len(inventory_str) > 150: inventory_str = inventory_str[:150] + "..."

            # Prompt detallado con instrucciones claras para la IA/DM
            full_prompt = (
                f"Eres el Dungeon Master (DM) de un juego de rol de texto estilo D&D simplificado.\n"
                f"Contexto Reciente:\n{context_str}\n\n"
                f"Estadísticas del Jugador: Lvl={player_stats.get('Level',1)}, HP={player_stats.get('HP',1)}/{player_stats.get('MaxHP',1)}, STR={player_stats.get('STR',10)}, DEX={player_stats.get('DEX',10)}, XP={player_stats.get('XP',0)}/{player_stats.get('XP_Next_Level',100)}\n"
                f"Inventario: {inventory_str}\n"
                f"Notas del Jugador: {player_stats.get('Notas', 'N/A')}\n\n"
                f"TAREA ACTUAL: {prompt}\n\n"
                f"Instrucciones para el DM:\n"
                f"1. Narra el resultado de la acción del jugador de forma interesante y coherente.\n"
                f"2. Describe la situación actual.\n"
                f"3. **IMPORTANTE:** Si el jugador recibe daño o se cura, indícalo CLARAMENTE usando los tags [DAÑO: X] o [CURA: Y] (ej: 'El goblin te golpea! [DAÑO: 4]').\n"
                f"4. **IMPORTANTE:** Si el jugador supera un desafío o logra algo significativo, otórgale experiencia usando el tag [XP: Z] (ej: 'Logras descifrar el enigma. [XP: 50]'). Otorga XP con moderación.\n"
                f"5. **IMPORTANTE:** Si el jugador encuentra un objeto, indícalo con el tag [ITEM: Nombre del Objeto] (ej: 'Encuentras una [ITEM: Daga brillante] en el cofre.')\n"
                f"6. Termina tu respuesta preguntando '¿Qué haces?' o con 2-3 opciones numeradas [1] Opción A [2] Opción B.\n"
                f"7. Mantén las respuestas relativamente cortas (2-6 frases).\n"
                f"8. Si HP llega a 0 o menos, narra la derrota épica.\n"
                f"9. Sé creativo y mantén el espíritu de D&D."
            )

            # Llamar al conector (que maneja rotación y reintentos)
            response_text, status = connector.query(full_prompt)

            # Procesar respuesta o error
            if status == "success" and response_text:
                 result = response_text.strip()
            else:
                # Si hubo error, loguearlo y preparar mensaje de fallback
                log_msg = f"... (API DM falló: {status}). Usando fallback narrativo simple."
                gui_queue.put(("log", log_msg))
                try:
                    # Intentar parsear si el conector devuelve JSON en error
                    error_info = json.loads(response_text)
                    result = f"[Fallback por error API: {error_info.get('error', status)}. El DM está confundido. Intenta algo simple.]"
                except (json.JSONDecodeError, TypeError):
                    result = f"[Fallback por error API: {status}. El DM está confundido. Intenta algo simple.]"

        # Si no hay conector o falló todo, usar fallback básico
        if result is None:
            result = "El DM se queda en silencio... parece que la conexión se perdió. ¿Qué intentas hacer de todos modos?"
            gui_queue.put(("log", "... (Usando fallback offline directo)."))

        # Poner el resultado y el callback en la cola para el hilo principal
        gui_queue.put((callback, result))

    # Deshabilitar input y empezar tarea en hilo
    set_input_state(tk.DISABLED)
    run_in_thread(generation_task)

def roll_dice(sides: int) -> int:
    """Simula tirar un dado de N caras."""
    return random.randint(1, sides)

def process_player_input(event=None):
    """
    Procesa la entrada del usuario desde el campo de texto.
    Maneja comandos especiales (ej: /inv) o envía la acción a la IA/DM.
    Se puede activar presionando Enter en el campo de entrada o con el botón Enviar.
    """
    if game_over: return # No procesar si el juego terminó

    player_input = input_entry.get().strip()
    if not player_input: return # Ignorar entrada vacía

    add_log(player_input, "player") # Mostrar input del jugador
    input_entry.delete(0, tk.END) # Limpiar campo

    # Procesar comandos especiales que no van a la IA
    command = player_input.lower()
    if command == "/inv" or command == "/inventario": show_inventory(); return
    elif command.startswith("/usar "): use_item(player_input[len("/usar "):].strip()); return
    elif command == "/guardar" or command == "/save": save_game(); add_log("Partida guardada.", "system"); return
    elif command == "/cargar" or command == "/load": load_game(); return
    elif command == "/stats" or command == "/hp": show_stats(); return
    elif command == "/ayuda" or command == "/help": show_help(); return

    # Si no es un comando, es una acción para el DM
    game_context.append(f"Jugador: {player_input}")
    dm_request_prompt = f"El jugador acaba de decir: '{player_input}'. Procesa esta acción."
    # Pedir a la IA que procese la acción y responda
    ask_dm_ai(dm_request_prompt, handle_dm_response)

def handle_dm_response(dm_text):
    """
    Callback ejecutado (desde el hilo principal vía cola) cuando se recibe la respuesta del DM.
    Parsea la respuesta en busca de tags [DAÑO:X], [CURA:Y], [XP:Z], [ITEM:Nombre],
    actualiza el estado del juego, muestra la narrativa limpia y reactiva la entrada.
    """
    global game_over, player_stats, player_inventory

    display_text = dm_text
    extracted_data = {"damage": 0, "heal": 0, "xp": 0, "items": []}
    # Regex para encontrar tags como [TAG: Valor] (case-insensitive para TAG)
    tag_pattern = r"\[(DAÑO|CURA|XP|ITEM):\s*([^\]]+)\]"

    def extract_and_remove_tags(text):
        """Función interna para buscar tags, extraer datos y limpiar texto."""
        nonlocal display_text # Permitir modificar la variable externa
        matches = list(re.finditer(tag_pattern, text, re.IGNORECASE)) # Ignorar mayus/minus en TAG

        for match in reversed(matches): # Procesar de atrás hacia adelante
            tag = match.group(1).upper() # Convertir tag a mayúsculas para consistencia
            value_str = match.group(2).strip()

            try:
                if tag == "DAÑO": extracted_data["damage"] += int(value_str)
                elif tag == "CURA": extracted_data["heal"] += int(value_str)
                elif tag == "XP": extracted_data["xp"] += int(value_str)
                elif tag == "ITEM": extracted_data["items"].append(value_str)
            except ValueError:
                # Loguear error si el valor no es convertible (ej. [DAÑO: Mucho])
                add_log(f"Advertencia: Valor no numérico en tag {tag}: '{value_str}'", "system")

            # Eliminar el tag completo del texto a mostrar
            display_text = display_text[:match.start()] + display_text[match.end():]

        return display_text.strip() # Devolver texto sin tags

    # Limpiar el texto y añadirlo al log
    cleaned_text = extract_and_remove_tags(dm_text)
    add_log(cleaned_text, "dm")
    # Guardar el texto limpio en el contexto para futuras llamadas a la IA
    game_context.append(f"DM: {cleaned_text}")

    # Aplicar los cambios de estado extraídos
    hp_changed = False
    if extracted_data["damage"] > 0:
        player_stats["HP"] = player_stats.get("HP", 1) - extracted_data["damage"]
        add_log(f"(Recibiste {extracted_data['damage']} daño)", "system")
        hp_changed = True
    if extracted_data["heal"] > 0:
        max_hp = player_stats.get("MaxHP", 1)
        player_stats["HP"] = min(player_stats.get("HP", 0) + extracted_data["heal"], max_hp)
        add_log(f"(Te curaste {extracted_data['heal']} HP)", "system")
        hp_changed = True
    if extracted_data["items"]:
        for item in extracted_data["items"]:
            # Evitar añadir items vacíos si el parseo falla
            if item:
                player_inventory.append(item)
                add_log(f"(Obtuviste: {item})", "system")
    if extracted_data["xp"] > 0:
        player_stats["XP"] = player_stats.get("XP", 0) + extracted_data["xp"]
        add_log(f"(Ganaste {extracted_data['xp']} XP)", "system")
        check_level_up() # Comprobar si se sube de nivel (esto actualiza display si ocurre)

    # Actualizar display si HP cambió y no hubo level up (que ya actualiza)
    if hp_changed and not extracted_data["xp"] > 0: # Evitar doble update si se ganó XP
         update_status_display()
    elif not hp_changed and not extracted_data["xp"] > 0 and not extracted_data["items"]:
         # Si no pasó nada que modifique el estado visible,
         # no es estrictamente necesario actualizar, pero no hace daño.
         pass

    # Comprobar fin de juego
    check_game_over()

    # Reactivar input si el juego continúa
    if not game_over:
        set_input_state(tk.NORMAL)
        # Poner foco de nuevo en el campo de entrada
        if input_entry: input_entry.focus_set()


def check_level_up():
    """
    Comprueba si el jugador tiene suficiente XP para subir de nivel.
    Si es así, incrementa nivel, stats, HP, y calcula nuevo umbral de XP.
    Muestra un mensaje de felicitación.
    """
    global player_stats
    current_xp = player_stats.get("XP", 0)
    xp_next = player_stats.get("XP_Next_Level", 100)
    current_level = player_stats.get("Level", 1)

    if current_xp >= xp_next:
        # Subida de nivel
        player_stats["Level"] = current_level + 1
        xp_overflow = current_xp - xp_next # XP sobrante
        # Aumento de stats (ejemplo simple)
        hp_gain = random.randint(3, 6)
        old_max_hp = player_stats.get("MaxHP", 15)
        player_stats["MaxHP"] = old_max_hp + hp_gain
        player_stats["HP"] = player_stats["MaxHP"] # Curación completa al subir
        # Aumentar STR o DEX aleatoriamente
        stat_to_increase = random.choice(["STR", "DEX"])
        old_stat_value = player_stats.get(stat_to_increase, 10)
        player_stats[stat_to_increase] = old_stat_value + 1
        # Nuevo umbral de XP (ejemplo: casi duplicar)
        player_stats["XP_Next_Level"] = int(xp_next * 1.7 + 50)
        player_stats["XP"] = xp_overflow # Conservar XP sobrante

        # Notificar al jugador
        add_log(f"¡Felicidades! ¡Has subido al Nivel {player_stats['Level']}!", "levelup")
        add_log(f"(HP Max: {old_max_hp} -> {player_stats['MaxHP']}. {stat_to_increase}: {old_stat_value} -> {player_stats[stat_to_increase]})", "levelup")

        # Actualizar inmediatamente la GUI para reflejar el nivel y stats
        update_status_display()

def show_inventory():
    """Muestra el inventario actual del jugador en el log."""
    if not player_inventory:
        add_log("Inventario vacío.", "system")
    else:
        # Formatear lista para mejor lectura
        inv_str = "\n".join([f"- {item}" for item in sorted(player_inventory)]) # Ordenado alfabéticamente
        add_log("--- Inventario ---\n" + inv_str + "\n----------------", "system")

def use_item(item_name_input):
    """
    Intenta usar un item del inventario.
    Lógica simple implementada solo para items que contengan 'poción'.
    """
    global player_stats, player_inventory

    found_item = None
    item_index = -1
    # Buscar el item (case-insensitive)
    for i, item in enumerate(player_inventory):
        if item_name_input.lower() in item.lower(): # Busca si el input está contenido en el nombre del item
            found_item = item
            item_index = i
            break # Usar el primer item que coincida

    if not found_item:
        add_log(f"No tienes nada parecido a '{item_name_input}' en tu inventario.", "system")
        return

    # Lógica específica para pociones
    # Podría extenderse con un diccionario de efectos de items si se quisiera
    if "poción" in found_item.lower() or "potion" in found_item.lower():
        heal_amount = random.randint(4, 8) # Cura variable
        max_hp = player_stats.get("MaxHP", 1)
        current_hp = player_stats.get("HP", 0)
        effective_heal = min(heal_amount, max_hp - current_hp) # No curar más allá del máximo

        if effective_heal > 0:
            player_stats["HP"] = current_hp + effective_heal
            player_inventory.pop(item_index) # Consumir item (eliminar por índice)
            add_log(f"Usaste {found_item} y recuperaste {effective_heal} HP.", "system")
            update_status_display() # Actualizar HP en GUI
        else:
            add_log(f"Ya tienes la salud al máximo, no necesitas usar {found_item}.", "system")

    else:
        # Para otros items, no hacer nada o enviar al DM
        add_log(f"No sabes cómo usar '{found_item}' ahora mismo.", "system")
        # Opcional: Podrías enviar esto al DM para que narre el intento
        # game_context.append(f"Jugador: Intenta usar {found_item}")
        # ask_dm_ai(f"El jugador intenta usar '{found_item}'. Describe qué pasa.", handle_dm_response)


def show_stats():
     """Muestra las estadísticas detalladas del personaje."""
     # Usar .get con valores por defecto por si alguna clave falta
     stats_str = f"--- Estadísticas ---\n" \
                 f" Nivel: {player_stats.get('Level', '?')}\n" \
                 f" HP: {player_stats.get('HP', '?')} / {player_stats.get('MaxHP', '?')}\n" \
                 f" XP: {player_stats.get('XP', '?')} / {player_stats.get('XP_Next_Level', '?')}\n" \
                 f" Fuerza (STR): {player_stats.get('STR', '?')}\n" \
                 f" Destreza (DEX): {player_stats.get('DEX', '?')}\n" \
                 f" Notas: {player_stats.get('Notas', 'N/A')}\n" \
                 f"--------------------"
     add_log(stats_str, "system")

def show_help():
     """Muestra los comandos disponibles."""
     help_str = "--- Comandos Disponibles ---\n" \
                "/inv | /inventario   - Muestra tu inventario.\n" \
                "/usar [nombre_item] - Intenta usar un objeto (ej: /usar Poción).\n" \
                "/stats | /hp         - Muestra tus estadísticas.\n" \
                "/guardar | /save     - Guarda la partida.\n" \
                "/cargar | /load     - Carga la última partida guardada.\n" \
                "/ayuda | /help       - Muestra esta ayuda.\n" \
                "---------------------------"
     add_log(help_str, "system")

def start_game():
    """Inicia el juego pidiendo la escena inicial al DM."""
    if not game_over: set_input_state(tk.DISABLED)
    add_log("Generando la escena inicial...", "italic")
    initial_prompt = (
        "Comienza una nueva aventura de rol estilo D&D simplificado. "
        "Describe una escena inicial interesante y peligrosa para un aventurero novato "
        "(quizás una cueva oscura, un bosque embrujado, unas ruinas antiguas). "
        "Termina preguntando al jugador '¿Qué haces?' o con 2-3 opciones numeradas."
    )
    ask_dm_ai(initial_prompt, handle_dm_response) # El callback reactivará input

def check_game_over():
    """Comprueba si HP <= 0 y actualiza el estado del juego."""
    global game_over
    if player_stats.get("HP", 1) <= 0 and not game_over:
        game_over = True
        add_log("\n" + "="*30 + "\n      GAME OVER\n" + "="*30, "bold")
        set_input_state(tk.DISABLED) # Deshabilitar input
        add_log("Tu viaje ha terminado. Has sido consumido por el Vacío...", "bold")
        add_log("\nEstadísticas Finales de la Sesión:")
        for key, value in player_stats.items():
             formatted_key = key.replace('_', ' ').capitalize()
             add_log(f"- {formatted_key}: {value}")
        if player_inventory:
            add_log("Inventario final: " + ", ".join(player_inventory))
        # Considerar guardar automáticamente aquí o al cerrar

# --- Persistencia (Guardar/Cargar) ---
def save_game():
    """Guarda el estado actual del juego en un archivo JSON."""
    try:
        # Guardar solo el contexto reciente
        limited_context = game_context[-25:] # Guardar últimos 25 intercambios

        save_data = {
            "player_stats": player_stats,
            "player_inventory": player_inventory,
            "game_context": limited_context,
            "game_over": game_over
        }
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=4, ensure_ascii=False)
        # No loguear aquí si se llama desde on_closing o comando /save
        return True
    except Exception as e:
        # Usar la cola para loguear error de forma segura si ocurre en on_closing
        gui_queue.put(("log", f"Error al guardar partida: {e}"))
        return False

def load_game():
    """
    Carga el estado del juego desde SAVE_FILE si existe.
    Actualiza las variables globales y pone tareas en cola para actualizar GUI.
    """
    global player_stats, player_inventory, game_context, game_over
    try:
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                load_data = json.load(f)

            # Validar datos cargados (muy básico)
            if isinstance(load_data.get("player_stats"), dict) and \
               isinstance(load_data.get("player_inventory"), list) and \
               isinstance(load_data.get("game_context"), list):

                # Restaurar estado
                player_stats = load_data["player_stats"]
                player_inventory = load_data["player_inventory"]
                game_context = load_data["game_context"]
                game_over = load_data.get("game_over", False) # Cargar estado game_over

                # Poner tareas en cola para actualizar la GUI y log
                gui_queue.put(("log", "Partida anterior cargada."))
                gui_queue.put(("log", "--- Contexto Cargado ---"))
                # Usar un comando especial en cola para añadir logs múltiples
                log_tasks = []
                for entry in game_context:
                     if entry.startswith("Jugador:"): log_tasks.append(("add_log", (entry[len("Jugador:"):].strip(), "player")))
                     elif entry.startswith("DM:"): log_tasks.append(("add_log", (entry[len("DM:"):].strip(), "dm")))
                     else: log_tasks.append(("add_log", (entry, "system")))
                gui_queue.put(("process_log_batch", log_tasks)) # Comando para procesar lote de logs
                gui_queue.put(("log", "--- Fin Contexto Cargado ---"))
                gui_queue.put(("update_status", None)) # Actualizar labels de status

                if game_over:
                    gui_queue.put(("log", "Esta partida guardada ya había terminado."))
                    gui_queue.put(("set_input_state", tk.DISABLED)) # Deshabilitar input

            else:
                # Archivo corrupto
                gui_queue.put(("log", "Error: Archivo de guardado corrupto o inválido. Iniciando nueva partida."))
                player_stats = DEFAULT_PLAYER_STATS.copy(); player_inventory = []; game_context = ["Inicio de la Aventura"]; game_over = False; # Reset state
        else:
             # No hay archivo, empezar juego nuevo (no hacer nada aquí, initialize_connector lo maneja)
             gui_queue.put(("log", "No se encontró partida guardada. Iniciando nueva aventura."))

    except Exception as e:
        gui_queue.put(("log", f"Error crítico al cargar partida: {e}. Iniciando nueva partida."))
        player_stats = DEFAULT_PLAYER_STATS.copy(); player_inventory = []; game_context = ["Inicio de la Aventura"]; game_over = False; # Reset state


def on_closing():
    """Función llamada al intentar cerrar la ventana."""
    should_quit = False
    if not game_over: # Solo preguntar si el juego no ha terminado
        if messagebox.askyesno("Salir", "¿Guardar partida antes de salir?"):
            if save_game():
                 add_log("Partida guardada al salir.", "system")
                 should_quit = True
            else:
                 # Si falla el guardado, preguntar si aún quiere salir
                 if messagebox.askokcancel("Error al Guardar", "No se pudo guardar la partida. ¿Salir de todas formas?"):
                      should_quit = True
        else:
            # Si elige no guardar
            should_quit = True
    else:
        # Si el juego ya terminó, simplemente salir
        should_quit = True

    if should_quit:
        # Limpiar cola y detener el bucle after (intentar)
        # (Esto es difícil de garantizar perfectamente con hilos daemon)
        # Poner None puede servir como señal para process_gui_queue
        gui_queue.put(None) 
        window.destroy() # Cierra la ventana

# --- Procesador de Cola GUI (Corregido y Ampliado) ---
def process_gui_queue():
    """Procesa eventos puestos en la cola (llamado periódicamente por Tkinter)."""
    try:
        while not gui_queue.empty():
            message = gui_queue.get_nowait()

            # Señal de salida
            if message is None: 
                return # Detener el bucle after

            # Procesar diferentes tipos de mensajes/tareas
            if isinstance(message, tuple) and len(message) == 2:
                item1, item2 = message
                if callable(item1): # (callback, result)
                    callback = item1; result = item2
                    if window and window.winfo_exists(): callback(result)
                elif item1 == "log": add_log(item2) # ("log", "mensaje")
                elif item1 == "add_log": # ("add_log", (mensaje, tag))
                    log_msg, log_tag = item2
                    add_log(log_msg, log_tag)
                elif item1 == "update_status": update_status_display() # ("update_status", None)
                elif item1 == "start_game": start_game() # ("start_game", None)
                elif item1 == "set_input_state": set_input_state(item2) # ("set_input_state", state)
                elif item1 == "process_log_batch": # ("process_log_batch", [(type, (msg, tag)),...])
                     log_tasks = item2
                     for task_type, task_data in log_tasks:
                          if task_type == "add_log": add_log(task_data[0], task_data[1])
                else: add_log(f"Msg cola desc (tupla len 2): {message}")
            elif isinstance(message, str): add_log(message) # Mensaje de log simple
            else: add_log(f"Msg cola desc (otro tipo): {message}")

    except queue.Empty:
        pass # Normal si la cola está vacía
    except Exception as e:
        # Imprimir error a consola para depuración
        print(f"Error procesando cola GUI: {e}")

    # Volver a programar la revisión de la cola si la ventana existe
    if window and window.winfo_exists():
         window.after(100, process_gui_queue) # Revisar cada 100ms


# ==============================================================
# --- CONFIGURACIÓN DE LA GUI (Usando TTK) ---
# ==============================================================
window = tk.Tk()
window.title("Micro Calabozos y Chatbots v2.1 (Portfolio)")
window.geometry("750x650")
window.configure(bg="#ECECEC") # Fondo gris claro

# --- Estilos y Fuentes ---
font_normal = ("Segoe UI", 10)
font_bold = ("Segoe UI", 10, "bold")
font_italic = ("Segoe UI", 10, "italic")
font_title = ("Segoe UI", 12, "bold")

# --- Configurar Estilos TTK ---
style = ttk.Style()
available_themes = style.theme_names()
# Preferir temas más modernos si están disponibles
if 'clam' in available_themes: style.theme_use('clam')
elif 'vista' in available_themes: style.theme_use('vista')

style.configure('TButton', font=font_bold, padding=(10, 5))
style.configure('TLabel', font=font_normal, background="#ECECEC", padding=2)
style.configure('Bold.TLabel', font=font_bold, background="#ECECEC")
style.configure('Status.TLabel', font=font_normal, background="#F5F5F5", padding=5)
style.configure('TFrame', background="#ECECEC")
style.configure('Card.TFrame', background="#F5F5F5", relief=tk.SOLID, borderwidth=1)
style.configure('TLabelframe', background="#F5F5F5", padding=10)
style.configure('TLabelframe.Label', font=font_bold, background="#F5F5F5", foreground="#333333")
style.configure('TEntry', font=font_normal, padding=5)

# --- Layout Principal (Frames TTK) ---
top_frame = ttk.Frame(window, padding=5); top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(5,0))
middle_frame = ttk.Frame(window, padding=(0, 5, 0, 0)); middle_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
bottom_frame = ttk.Frame(window, padding=10); bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

# --- Widgets Superiores (Estado) ---
status_card = ttk.Frame(top_frame, style='Card.TFrame', padding=10)
status_card.pack(fill=tk.X, padx=10, pady=5)
status_labels_frame = ttk.Frame(status_card, style='Card.TFrame') # Usar mismo estilo que card para fondo
status_labels_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
hp_label = ttk.Label(status_labels_frame, text="HP: ?/?", style='Status.TLabel'); hp_label.pack(side=tk.LEFT, padx=(0,15))
stats_label = ttk.Label(status_labels_frame, text="STR: ? | DEX: ?", style='Status.TLabel'); stats_label.pack(side=tk.LEFT, padx=15)
xp_label = ttk.Label(status_labels_frame, text="Lvl: ? | XP: ?/?", style='Status.TLabel'); xp_label.pack(side=tk.LEFT, padx=15)
connector_label = ttk.Label(status_card, text=f"API: {connector_status}", anchor=tk.E, style='Status.TLabel')
connector_label.pack(side=tk.RIGHT)

# --- Widgets Medios (Log) ---
log_frame = ttk.Frame(middle_frame); log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=20, font=font_normal, state=tk.DISABLED, bd=1, relief=tk.SOLID, padx=5, pady=5)
log_area.pack(fill=tk.BOTH, expand=True)
# Configurar tags (colores y espaciado)
log_area.tag_config("player_tag", foreground="#00008B", font=font_bold)
log_area.tag_config("dm_tag", foreground="#006400", font=font_bold)
log_area.tag_config("dm_text", lmargin1=15, lmargin2=15, spacing3=8)
log_area.tag_config("roll_tag", foreground="#8A2BE2", font=font_italic)
log_area.tag_config("bold", font=font_bold)
log_area.tag_config("italic", font=font_italic)
log_area.tag_config("system_tag", foreground="#555555", font=font_italic) # Gris un poco más oscuro
try: log_area.tag_config("levelup_tag", foreground="orange", font=font_bold)
except tk.TclError: log_area.tag_config("levelup_tag", foreground="#FF8C00", font=font_bold) # Naranja oscuro

# --- Widgets Inferiores (Entrada) ---
input_entry = ttk.Entry(bottom_frame, font=font_normal)
input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5), pady=5)
input_entry.bind("<Return>", process_player_input)
send_button = ttk.Button(bottom_frame, text="Enviar", command=process_player_input, style='TButton')
send_button.pack(side=tk.RIGHT, padx=(0, 10), pady=5)


# ==============================================================
# --- INICIALIZACIÓN FINAL Y BUCLE PRINCIPAL ---
# ==============================================================

# Mensaje inicial seguro
add_log("--- Bienvenido a Micro Calabozos y Chatbots v2.1 ---")
add_log("Cargando estado y conectando a APIs...", "system")
add_log("Escribe '/ayuda' para ver los comandos disponibles.", "system")

# Inicializa conector y carga partida (síncrono)
initialize_connector()

# Actualiza display inicial
update_status_display()

# Inicia el chequeo periódico de la cola GUI
process_gui_queue()

# Configurar guardado al cerrar la ventana
window.protocol("WM_DELETE_WINDOW", on_closing)

# Enfocar el campo de entrada al inicio (solo si el juego no está terminado)
if not game_over and input_entry:
    input_entry.focus_set()
else: # Si se cargó juego terminado, deshabilitar input
    set_input_state(tk.DISABLED)

# Iniciar el bucle principal de Tkinter
window.mainloop()
