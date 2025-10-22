"""FAQ agent for handling customer questions."""

from __future__ import annotations

import json
from typing import Any, Dict

from services.openai_service import OpenAIService
from utils import logger


class FAQAgent:
    """Agent responsible for identifying and answering FAQ questions."""

    def __init__(self, openai_service: OpenAIService) -> None:
        self.openai_service = openai_service

    def identify_faq_intent(self, message: str) -> Dict[str, Any]:
        """Identify if the message is asking an FAQ question and extract intent."""
        
        system_prompt = """Eres un asistente que analiza mensajes de WhatsApp para identificar preguntas frecuentes sobre CubreJardin.

Las categorías de preguntas frecuentes son:

1. LOCATION - preguntas sobre ubicación, tienda física, dónde están
2. REGIONS - preguntas sobre envíos a regiones fuera de Santiago
3. INSTALLATION - preguntas sobre servicio de instalación
4. MINIMUM_ORDER - preguntas sobre pedido mínimo o despacho mínimo
5. LANDSCAPING - preguntas sobre paisajismo o diseño de jardines
6. OTHER_PRODUCTS - preguntas sobre otros productos, plantas, cubresuelos
7. WEB_PURCHASE - preguntas sobre comprar en la página web
8. PAYMENT - preguntas sobre métodos de pago
9. ORDER_PROCESS - preguntas sobre cómo hacer un pedido
10. TIQUI_INFO - preguntas generales sobre el tiqui tiqui
11. TIQUI_RABBITS - preguntas sobre si los conejos comen el tiqui tiqui
12. TIQUI_SHADE - preguntas sobre poner tiqui tiqui a la sombra
13. TIQUI_ON_GRASS - preguntas sobre poner tiqui tiqui sobre el pasto
14. TIQUI_MIX_GRASS - preguntas sobre mezclar tiqui tiqui con pasto
15. TIQUI_PRICE - preguntas sobre el precio del tiqui tiqui
16. TIQUI_COVERAGE - preguntas sobre cuánto tiqui tiqui se necesita para X metros cuadrados
17. GENERAL - consulta general que no cae en las categorías anteriores
18. NOT_FAQ - no es una pregunta FAQ

Analiza el mensaje y determina:
- category: la categoría más apropiada
- confidence: qué tan seguro estás (0.0-1.0)
- extracted_info: cualquier información relevante extraída (metros cuadrados, comuna, etc.)

Responde SOLO con JSON:
{
  "category": "CATEGORY_NAME",
  "confidence": 0.95,
  "extracted_info": {
    "square_meters": 20,
    "comuna": "Las Condes"
  }
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]

        try:
            response = self.openai_service.chat_completion(
                messages=messages,
                response_format={"type": "json_object"}
            )
            
            content = response["choices"][0]["message"]["content"]
            logger.info("faq_raw_response", extra={"content": content})
            
            data: Dict[str, Any] = json.loads(content)
            
            logger.info(
                "faq_intent_identified",
                extra={
                    "category": data.get("category"),
                    "confidence": data.get("confidence"),
                    "extracted_info": data.get("extracted_info")
                }
            )
            
            return data
            
        except Exception as e:
            logger.error("faq_intent_identification_failed", extra={"error": str(e), "traceback": str(e)})
            return {
                "category": "NOT_FAQ",
                "confidence": 0.0,
                "extracted_info": {}
            }

    def generate_faq_response(
        self, 
        message: str, 
        intent: Dict[str, Any],
        rag_context: str = ""
    ) -> str:
        """Generate a response based on FAQ intent and RAG context."""
        
        system_prompt = """Eres un asistente de atención al cliente de CubreJardin.

Tu trabajo es responder preguntas usando la información de la base de conocimientos proporcionada.

REGLAS IMPORTANTES:
1. Mantén EXACTAMENTE el tono, ortografía y estilo de las respuestas en la base de conocimientos
2. NO corrijas errores ortográficos que estén en las respuestas originales (ejemplo: "distintsas", "tambine", "tines")
3. Mantén el uso de mayúsculas y minúsculas exactamente como están
4. NO USES EMOJIS - Las respuestas originales NO tienen emojis, no los agregues
5. Si la pregunta requiere información específica del usuario (metros cuadrados, comuna), haz la pregunta correspondiente
6. Si haces cálculos para metros cuadrados, usa el formato y estilo de las respuestas originales
7. Sé natural, amigable y conversacional como en los ejemplos
8. Copia el texto EXACTAMENTE como aparece en la base de conocimientos, sin agregar ni quitar nada

Si la información no está en la base de conocimientos, indica amablemente que no tienes esa información y ofrece ayuda general."""

        user_content = f"""Pregunta del cliente: {message}

Información de la base de conocimientos:
{rag_context}

Información extraída: {json.dumps(intent.get('extracted_info', {}), ensure_ascii=False)}

Responde la pregunta del cliente usando la información proporcionada, manteniendo el tono y estilo exacto de las respuestas."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            response = self.openai_service.chat_completion(
                messages=messages
            )
            
            answer = response["choices"][0]["message"]["content"]
            
            logger.info(
                "faq_response_generated",
                extra={
                    "category": intent.get("category"),
                    "response_length": len(answer)
                }
            )
            
            return answer
            
        except Exception as e:
            logger.error("faq_response_generation_failed", extra={"error": str(e)})
            return "Disculpa, tuve un problema procesando tu pregunta. ¿Podrías reformularla?"


__all__ = ["FAQAgent"]
