"""Stock management agent for Mercado Fiel integration."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from services.openai_service import OpenAIService
from models.schemas import StockOperation
from utils import logger


class StockAgent:
    """Agent responsible for parsing and executing stock operations."""

    def __init__(self, openai_service: OpenAIService) -> None:
        self.openai_service = openai_service

    def parse_stock_command(self, message: str) -> StockOperation:
        """Parse natural language stock command using OpenAI."""
        
        system_prompt = """Eres un asistente que analiza mensajes de WhatsApp para detectar operaciones de stock.

Debes extraer:
- action: STOCK_ADD (agregar), STOCK_REMOVE (quitar), STOCK_QUERY (consultar), STOCK_SALE (venta), STOCK_SET (establecer)
- product_id: número del producto
- quantity: cantidad (si aplica)
- confidence: 0.0-1.0 qué tan seguro estás

Patrones comunes:
- "entrada 123 50" → STOCK_ADD, product_id=123, quantity=50
- "salida 123 30" → STOCK_REMOVE, product_id=123, quantity=30
- "venta 123 5" → STOCK_SALE, product_id=123, quantity=5
- "stock 123" → STOCK_QUERY, product_id=123
- "set 123 100" → STOCK_SET, product_id=123, quantity=100
- "+123 50" → STOCK_ADD, product_id=123, quantity=50
- "-123 30" → STOCK_REMOVE, product_id=123, quantity=30
- "cuanto stock tiene el 123" → STOCK_QUERY, product_id=123
- "agregar 20 unidades del producto 456" → STOCK_ADD, product_id=456, quantity=20

Responde SOLO con JSON:
{
  "action": "STOCK_ADD|STOCK_REMOVE|STOCK_QUERY|STOCK_SALE|STOCK_SET|UNKNOWN",
  "product_id": 123,
  "quantity": 50,
  "confidence": 0.95
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]

        try:
            response = self.openai_service.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                purpose="stock_command_parsing"
            )
            
            content = response["choices"][0]["message"]["content"]
            data: Dict[str, Any] = json.loads(content)
            
            logger.info(
                "stock_command_parsed",
                extra={
                    "action": data.get("action"),
                    "product_id": data.get("product_id"),
                    "quantity": data.get("quantity"),
                    "confidence": data.get("confidence", 0.0)
                }
            )
            
            return StockOperation(**data)
            
        except Exception as e:
            logger.error("stock_parsing_error", extra={"error": str(e), "text": message})
            return StockOperation(
                action="UNKNOWN",
                product_id=None,
                quantity=None,
                confidence=0.0
            )

    def quick_parse(self, message: str) -> Optional[Dict[str, Any]]:
        """Quick regex-based parsing for common patterns (fallback)."""
        
        text = message.lower().strip()
        
        patterns = {
            "stock_add": r"^(?:stock\s+add|entrada|\+)\s+(\d+)\s+(\d+)",
            "stock_remove": r"^(?:stock\s+remove|salida|-)\s+(\d+)\s+(\d+)",
            "stock_sale": r"^(?:venta|sale)\s+(\d+)\s+(\d+)",
            "stock_query": r"^(?:stock|consulta|\?)\s+(\d+)",
            "stock_set": r"^set\s+(\d+)\s+(\d+)",
        }
        
        for action_key, pattern in patterns.items():
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                action_map = {
                    "stock_add": "STOCK_ADD",
                    "stock_remove": "STOCK_REMOVE",
                    "stock_sale": "STOCK_SALE",
                    "stock_query": "STOCK_QUERY",
                    "stock_set": "STOCK_SET",
                }
                
                product_id = int(match.group(1))
                quantity = int(match.group(2)) if len(match.groups()) > 1 else None
                
                return {
                    "action": action_map[action_key],
                    "product_id": product_id,
                    "quantity": quantity,
                    "confidence": 1.0
                }
        
        return None
