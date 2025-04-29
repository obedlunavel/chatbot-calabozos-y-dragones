# Micro Calabozos y Chatbots - Un RPG de Texto con IA como DM

Este proyecto es un juego de rol (RPG) de texto simple, inspirado en Dungeons & Dragons, donde una Inteligencia Artificial (IA) actúa como tu Dungeon Master (DM). La interfaz gráfica está construida con Python y Tkinter (usando widgets ttk para un mejor aspecto), y la narrativa es generada dinámicamente mediante llamadas a APIs de Modelos de Lenguaje Grandes (LLMs) como GPT-3.5 Turbo (OpenAI), Gemini (Google) y/o DeepSeek.

El juego incluye mecánicas básicas de RPG como puntos de vida, estadísticas simples, experiencia, subida de nivel, un inventario básico y persistencia para guardar y cargar tu progreso.

![Ejemplo de Screenshot](screenshot.png) 
*(Opcional pero MUY recomendado: Reemplaza esto con una captura de pantalla real o un GIF del juego en acción. Guarda la imagen como `screenshot.png` en la misma carpeta).*

## Características Principales

* **Interfaz Gráfica de Chat:** GUI creada con Python, Tkinter y `ttk` para una interacción basada en texto.
* **IA como Dungeon Master:** Utiliza APIs de LLM externas para generar descripciones de escenas, narrar resultados de acciones y presentar opciones al jugador.
* **Conector Híbrido de API (`HybridAIConnector`):**
    * Se conecta a OpenAI, Google Gemini y/o DeepSeek (requiere al menos una clave API configurada).
    * Detecta automáticamente qué APIs están configuradas a través de variables de entorno.
    * Implementa **rotación Round-Robin** entre las APIs activas para distribuir el uso y mitigar costos/límites.
    * Manejo básico de reintentos en caso de fallo temporal de la API.
* **Sistema de Personaje Básico:**
    * Puntos de Vida (HP) que se modifican según la narrativa.
    * Estadísticas simples (Fuerza - STR, Destreza - DEX).
    * Sistema de Experiencia (XP) y Niveles.
    * Subida de nivel con mejoras automáticas de HP y stats.
* **Parseo de Respuesta de IA:** Utiliza expresiones regulares para extraer información estructurada de la respuesta del DM mediante tags específicos:
    * `[DAÑO: X]` - Reduce el HP del jugador.
    * `[CURA: Y]` - Incrementa el HP del jugador.
    * `[XP: Z]` - Otorga puntos de experiencia.
    * `[ITEM: Nombre Objeto]` - Añade el objeto al inventario.
* **Inventario:** Sistema simple para llevar objetos. Comando `/inv` para ver y `/usar` (limitado a pociones por ahora).
* **Persistencia:** Guarda automáticamente el estado del juego (stats, inventario, contexto reciente, estado de fin de juego) en `rpg_save.json` al salir y lo carga al iniciar. Comandos `/guardar` y `/cargar` disponibles.
* **Manejo Asíncrono:** Usa `threading` y `queue` para realizar llamadas a las APIs en segundo plano, manteniendo la interfaz gráfica responsiva.
* **Comandos del Jugador:** Aparte de la entrada narrativa, acepta comandos como `/inv`, `/usar`, `/stats`, `/hp`, `/save`, `/load`, `/help`.

## Tecnologías Utilizadas

* **Lenguaje:** Python 3 (se recomienda 3.8 o superior)
* **GUI:** Tkinter, `tkinter.ttk`
* **APIs Externas:** OpenAI (GPT-3.5 Turbo), Google Gemini, DeepSeek (configurable vía `api_connectors.py` y `.env`)
* **Librerías Principales:**
    * `requests` (para DeepSeek)
    * `google-generativeai` (para Gemini)
    * `openai` (para OpenAI)
    * `python-dotenv` (para cargar claves API desde `.env`)
    * Módulos estándar: `json`, `re`, `threading`, `queue`, `os`, `time`, `random`

## Configuración e Instalación

Sigue estos pasos para configurar y ejecutar el proyecto en tu máquina local:

1.  **Clonar el Repositorio (si aplica):**
    ```bash
    git clone [URL_DEL_REPOSITORIO]
    cd [NOMBRE_CARPETA_PROYECTO]
    ```
    O simplemente descarga los archivos (`.py`, `.env.example`) en una carpeta.

2.  **Crear un Entorno Virtual (Recomendado):**
    ```bash
    python -m venv venv 
    # Activar el entorno:
    # Windows:
    venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate 
    ```

3.  **Instalar Dependencias:**
    Crea un archivo `requirements.txt` con el siguiente contenido:
    ```txt
    requests
    google-generativeai
    openai
    python-dotenv
    ```
    Luego, instala las librerías:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar Claves API (¡IMPORTANTE!):**
    * Busca el archivo `env.example` en el proyecto.
    * **Copia** este archivo y renómbralo a `.env` (asegúrate de que empiece con un punto).
    * **Edita** el archivo `.env` con un editor de texto.
    * **Añade tus propias claves API** para al menos uno de los servicios (OpenAI, Gemini, DeepSeek). Si no añades ninguna clave, el juego funcionará en modo offline con respuestas de fallback muy básicas.
        ```dotenv
        # Ejemplo de contenido para .env
        OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        GEMINI_API_KEY=AIxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx 
        ```
    * **¡NUNCA compartas tu archivo `.env` ni tus claves API!** Asegúrate de que `.env` esté listado en tu archivo `.gitignore` si usas Git.

## Cómo Ejecutar

Una vez completada la configuración, ejecuta el script principal desde tu terminal (asegúrate de que tu entorno virtual esté activado):

```bash
python micro_rpg_chatbot_v2_portfolio.py
