# api_connectors.py
import os
import json
import requests
import google.generativeai as genai
import openai
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
import logging
from dotenv import load_dotenv
import time
import itertools # Necesario para la rotación

class HybridAIConnector:
    def __init__(self):
        """
        Inicializa el conector híbrido de IA con configuración mejorada y rotación.
        """
        load_dotenv()
        self._setup_logger()
        self.timeout = 30
        self.max_retries = 3 # Reducir reintentos para rotar más rápido si falla
        self.retry_delay = 2
        # self.cache_dir = Path("api_cache") # Cache deshabilitado por simplicidad en este ejemplo
        # self.cache_dir.mkdir(exist_ok=True)

        self.providers = {
            "gemini": {
                "configured": False, "model": None,
                "models_available": ['models/gemini-1.5-flash-latest', 'models/gemini-1.5-pro-latest', 'models/gemini-pro'], # Flash primero (más rápido/barato)
                "generation_config": {"temperature": 0.75, "max_output_tokens": 4096} # Ajustar temp/tokens
            },
            "deepseek": {
                "configured": False, "endpoint": "https://api.deepseek.com/v1/chat/completions",
                "headers": {"Content-Type": "application/json"},
                "payload_template": {"model": "deepseek-chat", "temperature": 0.75, "max_tokens": 4096}
            },
            "openai": {
                "configured": False, "client": None,
                # --- ¡CAMBIO IMPORTANTE AQUÍ! ---
                "model": "gpt-3.5-turbo", # Usar GPT-3.5 Turbo por defecto (más barato)
                # ---------------------------------
                "params": {"temperature": 0.75, "max_tokens": 4000} # Ajustar temp/tokens
            }
        }

        self.active_providers_list: List[str] = []
        self.provider_cycler = None # Iterador para rotación
        self.configure_providers()
        self._validate_initial_config()
        self._setup_provider_rotation()

    def _setup_logger(self):
        self.logger = logging.getLogger("APIConnector")
        if not self.logger.handlers: # Evitar añadir handlers múltiples veces
            self.logger.setLevel(logging.INFO) # INFO por defecto, DEBUG si necesitas más detalle
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _validate_initial_config(self):
        if not self.active_providers_list:
            self.logger.error("CRÍTICO: No hay proveedores de API configurados. Revisa tu archivo .env con las claves API.")
            # No lanzamos error aquí para permitir modo offline en la GUI, pero sí logueamos
            # raise RuntimeError("Se requieren credenciales API válidas para al menos un proveedor.")

    def configure_providers(self):
        self.logger.info("Configurando proveedores de IA...")
        # Configura cada uno (sin cambios en estas funciones internas)
        self._configure_gemini()
        self._configure_deepseek()
        self._configure_openai()
        
        # Actualiza la lista de activos
        self.active_providers_list = [p for p, cfg in self.providers.items() if cfg['configured']]
        self.logger.info(f"Proveedores activos detectados: {', '.join(self.active_providers_list) if self.active_providers_list else 'Ninguno'}")

    def _configure_gemini(self):
        # (Sin cambios aquí, igual que tu versión anterior)
        if api_key := os.getenv("GEMINI_API_KEY"):
            try:
                genai.configure(api_key=api_key)
                # Intentar configurar con el primer modelo válido encontrado
                model_instance = None
                for model_name in self.providers["gemini"]["models_available"]:
                    try:
                        test_model = genai.GenerativeModel(model_name)
                        # Prueba de conexión simple (puede fallar por cuota, pero valida configuración)
                        test_model.generate_content("Test", generation_config=genai.types.GenerationConfig(max_output_tokens=5))
                        model_instance = test_model # Guardar la instancia del modelo que funcionó
                        self.providers["gemini"]["model_name_configured"] = model_name # Guardar nombre
                        self.logger.info(f"Modelo Gemini activo: {model_name}")
                        break # Usar el primer modelo exitoso
                    except Exception as model_e:
                        self.logger.debug(f"Modelo Gemini {model_name} no disponible o falló test: {model_e}")
                
                if model_instance:
                    self.providers["gemini"]["model"] = model_instance # Guardar la instancia
                    self.providers["gemini"]["configured"] = True
                    self.logger.info("Proveedor Gemini configurado exitosamente.")
                else:
                    self.logger.warning("No se pudo configurar ningún modelo Gemini válido.")

            except Exception as e:
                self.logger.error(f"Error configurando Gemini: {str(e)}")


    def _configure_deepseek(self):
        # (Sin cambios aquí, igual que tu versión anterior)
         if api_key := os.getenv("DEEPSEEK_API_KEY"):
            try:
                self.providers["deepseek"]["headers"]["Authorization"] = f"Bearer {api_key}"
                test_payload = { "messages": [{"role": "user", "content": "Test"}], "model": "deepseek-chat", "max_tokens": 1 }
                response = requests.post(
                    self.providers["deepseek"]["endpoint"], headers=self.providers["deepseek"]["headers"],
                    json=test_payload, timeout=10 )
                response.raise_for_status()
                self.providers["deepseek"]["configured"] = True
                self.logger.info("Proveedor DeepSeek configurado exitosamente.")
            except Exception as e:
                self.logger.error(f"Error configurando DeepSeek: {str(e)}")


    def _configure_openai(self):
        # (Sin cambios aquí, igual que tu versión anterior)
        if api_key := os.getenv("OPENAI_API_KEY"):
            try:
                self.providers["openai"]["client"] = openai.OpenAI(api_key=api_key)
                self.providers["openai"]["client"].models.list() # Test básico
                self.providers["openai"]["configured"] = True
                self.logger.info("Proveedor OpenAI configurado exitosamente.")
            except Exception as e:
                self.logger.error(f"Error configurando OpenAI: {str(e)}")

    def _setup_provider_rotation(self):
        """Configura el iterador para la rotación de proveedores activos."""
        if self.active_providers_list:
            # Crear un ciclo infinito sobre la lista de proveedores activos
            self.provider_cycler = itertools.cycle(self.active_providers_list)
            self.logger.info(f"Rotación de API habilitada para: {', '.join(self.active_providers_list)}")
        else:
            self.provider_cycler = None
            self.logger.warning("Rotación de API deshabilitada (no hay proveedores activos).")

    def _get_next_provider(self) -> Optional[str]:
        """Obtiene el siguiente proveedor de la rotación."""
        if self.provider_cycler:
            return next(self.provider_cycler)
        return None

    def query(self, prompt: str, specific_provider: Optional[str] = None) -> Tuple[str, str]:
        """
        Ejecuta una consulta usando el siguiente proveedor en rotación (o uno específico).
        Manejo robusto de errores y reintentos para el proveedor seleccionado.

        Args:
            prompt: Texto de entrada para la consulta.
            specific_provider: Si se proporciona, intenta usar este proveedor en lugar de rotar.

        Returns:
            Tupla con (respuesta, estado: 'success', 'error', 'timeout')
        """
        if not self.active_providers_list:
            self.logger.error("Intento de consulta sin proveedores activos.")
            return self._fallback_response(prompt, "No hay proveedores configurados"), "error"

        provider_to_use = None
        status = "error" # Estado por defecto

        if specific_provider:
            if specific_provider in self.providers and self.providers[specific_provider]["configured"]:
                provider_to_use = specific_provider
            else:
                self.logger.warning(f"Proveedor específico '{specific_provider}' no está configurado o no existe. Usando rotación.")
                provider_to_use = self._get_next_provider()
        else:
            # --- Lógica de Rotación ---
            provider_to_use = self._get_next_provider()
            # ------------------------

        if not provider_to_use: # Si la rotación falla (no debería pasar si hay activos)
             self.logger.error("No se pudo seleccionar un proveedor para la consulta.")
             return self._fallback_response(prompt, "Fallo interno al seleccionar proveedor"), "error"

        self.logger.info(f"Intentando consulta con: {provider_to_use}")

        # Intenta la consulta con el proveedor seleccionado, con reintentos
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"Intento {attempt + 1}/{self.max_retries} con {provider_to_use}")
                response_text = ""

                if provider_to_use == "gemini":
                    response_text = self._query_gemini(prompt)
                elif provider_to_use == "deepseek":
                    response_text = self._query_deepseek(prompt)
                elif provider_to_use == "openai":
                    response_text = self._query_openai(prompt)
                else:
                    # Esto no debería ocurrir si la lista de activos es correcta
                    raise ValueError(f"Proveedor desconocido encontrado en rotación: {provider_to_use}")

                # Éxito en este intento
                return response_text, "success"

            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout en intento {attempt + 1} con {provider_to_use}")
                status = "timeout" # Marcar como timeout si todos los reintentos fallan
                # No romper el bucle, reintentar
            except requests.exceptions.RequestException as req_err:
                 self.logger.warning(f"Error de red en intento {attempt + 1} con {provider_to_use}: {req_err}")
                 status = "error_network"
                 # No romper el bucle, reintentar
            except Exception as e:
                self.logger.error(f"Error inesperado en intento {attempt + 1} con {provider_to_use}: {str(e)}", exc_info=False) # exc_info=True para traceback completo
                status = "error_provider" # Marcar como error del proveedor
                # Romper el bucle si es un error del proveedor (probablemente no se arregle reintentando)
                # OJO: Podrías decidir reintentar también aquí, depende de la causa del error.
                # Por ahora, rompemos para evitar gastar reintentos en errores persistentes.
                break 

            # Si no fue éxito y quedan reintentos, esperar antes del siguiente
            if attempt < self.max_retries - 1:
                self._handle_retry_delay(attempt)
            
        # Si todos los reintentos fallaron para este proveedor
        self.logger.error(f"Consulta fallida para '{provider_to_use}' después de {self.max_retries} intentos. Estado final: {status}")
        # Podrías intentar con el SIGUIENTE proveedor aquí como fallback avanzado,
        # pero por ahora, devolvemos el fallo.
        return self._fallback_response(prompt, f"Fallaron todos los intentos con {provider_to_use} ({status})"), status


    def _handle_retry_delay(self, attempt: int):
        # (Sin cambios aquí)
        delay = self.retry_delay * (2 ** attempt) + random.uniform(0, 0.5) # Añadir jitter
        self.logger.info(f"Esperando {delay:.2f} segundos antes de reintentar...")
        time.sleep(delay)

    def _query_gemini(self, prompt: str) -> str:
        # (Sin cambios aquí, pero asegúrate que usa self.providers["gemini"]["model"] que es la instancia)
        if not self.providers["gemini"]["model"]:
             raise RuntimeError("Modelo Gemini no está instanciado correctamente.")
        try:
            response = self.providers["gemini"]["model"].generate_content(
                prompt,
                generation_config=self.providers["gemini"]["generation_config"] # Usa el config guardado
                # Opcional: request_options={"timeout": self.timeout} si la librería lo soporta bien
            )
            # Añadir validación de respuesta (bloqueos, etc.)
            if not response.parts:
                 # Podría ser un bloqueo de seguridad u otro problema
                 safety_feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else 'No feedback'
                 self.logger.warning(f"Respuesta Gemini vacía. Posible bloqueo. Feedback: {safety_feedback}")
                 # Devolver un mensaje de error o string vacío controlado
                 return "[Respuesta bloqueada por seguridad o vacía]" 
            return response.text
        except Exception as e:
            self.logger.error(f"Error específico en _query_gemini: {str(e)}", exc_info=False)
            raise # Re-lanza para que el bucle de reintento lo capture

    def _query_deepseek(self, prompt: str) -> str:
        # (Sin cambios aquí)
        provider = self.providers["deepseek"]
        payload = {**provider["payload_template"], "messages": [{"role": "user", "content": prompt}]}
        response = requests.post( provider["endpoint"], headers=provider["headers"], json=payload, timeout=self.timeout )
        response.raise_for_status() # Lanza excepción para errores HTTP
        data = response.json()
        # Añadir validación de contenido
        if not data.get("choices") or not data["choices"][0].get("message") or not data["choices"][0]["message"].get("content"):
             self.logger.warning(f"Respuesta DeepSeek inválida o vacía: {data}")
             return "[Respuesta inválida o vacía]"
        return data["choices"][0]["message"]["content"]


    def _query_openai(self, prompt: str) -> str:
        # (Sin cambios aquí, pero usa el modelo configurado: gpt-3.5-turbo)
        provider = self.providers["openai"]
        if not provider["client"]:
             raise RuntimeError("Cliente OpenAI no inicializado.")
        try:
            response = provider["client"].chat.completions.create(
                model=provider["model"], # Usa el modelo configurado
                messages=[
                    # Opcional: Añadir un system prompt si quieres guiar más al modelo
                    # {"role": "system", "content": "Eres un asistente para un RPG de texto."},
                    {"role": "user", "content": prompt}
                ],
                temperature=provider["params"]["temperature"],
                max_tokens=provider["params"]["max_tokens"]
                # timeout=self.timeout # La librería openai v1.x maneja timeouts de forma diferente, revisar docs
            )
             # Añadir validación
            if not response.choices or not response.choices[0].message or not response.choices[0].message.content:
                 self.logger.warning(f"Respuesta OpenAI inválida o vacía: {response}")
                 # Chequear 'finish_reason' si es por 'content_filter'
                 finish_reason = response.choices[0].finish_reason if response.choices else 'unknown'
                 if finish_reason == 'content_filter':
                      return "[Respuesta bloqueada por filtro de contenido]"
                 return "[Respuesta inválida o vacía]"
            return response.choices[0].message.content
        except openai.APIConnectionError as e:
             self.logger.error(f"Error de Conexión OpenAI: {e}")
             raise requests.exceptions.RequestException(f"OpenAI Connection Error: {e}") # Re-lanzar como error de red
        except openai.RateLimitError as e:
             self.logger.error(f"Error de Límite de Tasa OpenAI: {e}")
             # Podrías manejar esto esperando un poco antes de reintentar, pero por ahora, lo dejamos fallar
             raise # Re-lanza para que el bucle lo capture como error del proveedor
        except openai.APIStatusError as e:
             self.logger.error(f"Error de Estado API OpenAI (HTTP {e.status_code}): {e.response}")
             raise # Re-lanza
        except Exception as e:
             self.logger.error(f"Error inesperado en _query_openai: {str(e)}", exc_info=False)
             raise # Re-lanza


    def _fallback_response(self, prompt: str, error: str) -> str:
        # (Sin cambios aquí)
        # Podrías añadir aquí una generación simple basada en random.choice si quieres
        # return f"[Error API: {error}. No se pudo generar contenido para: {prompt[:50]}...]"
         return json.dumps({
            "error": str(error), "message": "No se pudo completar la solicitud API",
            "original_prompt": prompt[:100]+"...",
            "suggested_actions": ["Verificar conexión", "Validar claves API (.env)", "Revisar logs de error"]
        }, ensure_ascii=False, indent=2)


    def get_active_providers(self) -> list:
        # Devuelve la lista que ya calculamos en configure_providers
        return self.active_providers_list

# Fin de api_connectors.py modificado
