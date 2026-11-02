"""FAQ agent for handling customer questions."""

from __future__ import annotations

import json
from typing import Any, Dict

from services.openai_service import OpenAIService
from utils import logger


class FAQAgent:
    """Agent responsible for identifying and answering FAQ questions."""

    def __init__(
        self,
        openai_service: OpenAIService,
        business_name: str = "el negocio",
        categories: list[str] | None = None,
    ) -> None:
        self.openai_service = openai_service
        self.business_name = business_name
        self.categories = categories or [
            "1. LOCATION - preguntas sobre ubicación, tienda física, dónde están",
            "2. SHIPPING - preguntas sobre envíos, cobertura, despacho",
            "3. SERVICES - preguntas sobre servicios ofrecidos o catálogo",
            "4. PRICING - preguntas sobre precios, cotizaciones, costos",
            "5. PAYMENT - preguntas sobre métodos de pago",
            "6. ORDER_PROCESS - preguntas sobre cómo hacer un pedido o contratar",
            "7. HOURS - preguntas sobre horarios de atención",
            "8. CONTACT - preguntas sobre canales de contacto",
            "9. GENERAL - consulta general sobre el negocio",
            "10. NOT_FAQ - no es una pregunta FAQ",
        ]

    def identify_faq_intent(self, message: str) -> Dict[str, Any]:
        """Identify if the message is asking an FAQ question and extract intent."""
        
        categories_text = "\n".join(self.categories)
        system_prompt = f"""Eres un asistente que analiza mensajes de clientes para identificar preguntas frecuentes sobre {self.business_name}.

Las categorías de preguntas frecuentes son:

{categories_text}

Analiza el mensaje y determina:
- category: la categoría más apropiada
- confidence: qué tan seguro estás (0.0-1.0)
- extracted_info: cualquier información relevante extraída (cantidades, comuna, etc.)

Responde SOLO con JSON:
{{
  "category": "CATEGORY_NAME",
  "confidence": 0.95,
  "extracted_info": {{
    "square_meters": 20,
    "comuna": "Las Condes"
  }}
}}"""

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
        rag_context: str = "",
        tenant_system_prompt: str | None = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate a response based on FAQ intent and RAG context."""
        
        system_prompt = f"""Eres un asistente de atención al cliente de {self.business_name}.

Tu labor es responder las preguntas de los clientes de manera concisa, clara, cordial y profesional en español.

DIRECTRICES CONVERSACIONALES:
1. Responde de forma breve y directa a lo que el cliente pregunta (máximo 1 a 3 párrafos cortos).
2. Sintetiza la información relevante de la base de conocimientos; NO vuelques textos largos ni bloques enteros de documentos.
3. Utiliza redacción y ortografía correctas en español amigable y cercano.
4. Si la base de conocimientos contiene detalles extensos, prioriza lo más útil para la consulta actual.
5. Si corresponde, incluye una pregunta de seguimiento orientadora (por ejemplo: si necesita cotizar metros cuadrados, despacho a su comuna o más información).
6. Si la información no se encuentra en la base de conocimientos, dilo amablemente y ofrece ayuda general o transferir con un ejecutivo."""

        if tenant_system_prompt and tenant_system_prompt.strip():
            system_prompt = f"{tenant_system_prompt.strip()}\n\n{system_prompt}"

        user_content = f"""Pregunta del cliente: {message}

Información de la base de conocimientos:
{rag_context}

Información extraída: {json.dumps(intent.get('extracted_info', {}), ensure_ascii=False)}

Responde la pregunta del cliente de forma concisa y conversacional usando la información anterior."""

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})

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
