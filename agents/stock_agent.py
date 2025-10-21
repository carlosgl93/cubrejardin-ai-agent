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
- action: STOCK_ADD (agregar), STOCK_REMOVE (quitar), STOCK_QUERY (consultar), STOCK_SALE (venta), STOCK_SET (establecer), STOCK_HISTORY (historial), STOCK_ALERTS (alertas), PRODUCT_LIST (listar productos)
- product_id: número del producto (excepto para STOCK_ALERTS y PRODUCT_LIST)
- quantity: cantidad (si aplica)
- page: número de página (solo para PRODUCT_LIST)
- search_term: término de búsqueda (solo para PRODUCT_LIST con búsqueda)
- confidence: 0.0-1.0 qué tan seguro estás

Patrones comunes para AGREGAR stock (STOCK_ADD):
- "entrada 123 50", "+123 50", "+ 3 50", "agregar 20 unidades del producto 456"
- "agregar 20 al producto 3", "añadir 100 del 789", "agregar 50 al producto 3"
- "sumar 30 al 456", "añadir 200 al producto 5"

Patrones comunes para VENTA/SALIDA (STOCK_SALE):
- "venta 123 5", "vendi 5 del producto 3", "vendí 10 del 456"
- "se vendieron 20 del producto 123", "venta de 5 unidades del 3"
- "salida 123 30", "-123 30", "- 3 50", "quitar 30 del producto 456"
- "restar 50 al producto 3", "quitar 20 del 789", "restar 100 del producto 5"

Patrones comunes para CONSULTAR stock (STOCK_QUERY):
- "stock 123", "? 3", "?3", "cuanto stock tiene el 123"
- "consulta 456", "stock del 3", "cuanto hay del producto 789"

Patrones comunes para ESTABLECER stock (STOCK_SET):
- "set 123 100", "establecer stock del 123 a 100"
- "fijar 456 en 200", "poner 789 a 50"
- "reiniciar producto 3 con 5000 unidades", "establecer producto 5 con 300"
- "fijar producto 456 en 1000", "poner producto 789 con 2500"

Patrones comunes para HISTORIAL (STOCK_HISTORY):
- "historial 123", "movimientos del 456", "history 789"
- "historial del producto 3", "movimientos 3"

Patrones comunes para ALERTAS (STOCK_ALERTS):
- "alertas", "alerts", "ver alertas", "alertas de stock"
- "que alertas hay", "mostrar alertas"

Patrones comunes para LISTAR PRODUCTOS (PRODUCT_LIST):
- "productos", "mis productos", "lista", "inventario"
- "productos pagina 2", "lista pagina 3"
- "buscar tomates", "buscar manzanas", "productos tomates"

IMPORTANTE: 
- "vendi", "vendí", "venta" siempre son STOCK_SALE (no STOCK_REMOVE)
- Los números de producto pueden estar pegados o con espacios: "+3 50" o "+ 3 50"
- Acepta variaciones sin acentos: "vendi" = "vendí"

Responde SOLO con JSON:
{
  "action": "STOCK_ADD|STOCK_REMOVE|STOCK_QUERY|STOCK_SALE|STOCK_SET|STOCK_HISTORY|STOCK_ALERTS|PRODUCT_LIST|UNKNOWN",
  "product_id": 123,
  "quantity": 50,
  "page": 1,
  "search_term": "tomates",
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
        
        # More flexible patterns allowing optional spaces
        patterns = {
            "stock_add": r"^(?:entrada|agregar|\+|añadir|sumar)\s*(\d+)\s+(\d+)",
            "stock_add_natural": r"^(?:agregar|añadir|sumar)\s+(\d+)\s+(?:al|del)\s+(?:producto\s+)?(\d+)",
            "stock_remove": r"^(?:salida|quitar|-)\s*(\d+)\s+(\d+)",
            "stock_remove_natural": r"^(?:quitar|restar)\s+(\d+)\s+(?:al|del)\s+(?:producto\s+)?(\d+)",
            "stock_sale": r"^(?:venta|vendi[oí]?)\s+(?:del\s+producto\s+)?(\d+)\s+(\d+)|^(?:venta|vendi[oí]?)\s+(\d+)\s+del\s+(?:producto\s+)?(\d+)",
            "stock_query": r"^(?:stock|consulta|\?)\s*(\d+)",
            "stock_set": r"^set\s+(\d+)\s+(\d+)",
            "stock_set_natural": r"^(?:reiniciar|establecer|fijar|poner)\s+(?:producto\s+)?(\d+)\s+(?:con|en|a)\s+(\d+)(?:\s+unidades)?",
            "stock_history": r"^(?:historial|history|movimientos)\s+(\d+)",
            "stock_alerts": r"^(?:alertas|alerts)$",
            "product_list": r"^(?:productos|lista|inventario|mis\s+productos)(?:\s+(?:pagina|página|page)\s+(\d+))?$",
            "product_search": r"^(?:buscar|productos|lista)\s+(.+?)(?:\s+(?:pagina|página|page)\s+(\d+))?$",
        }
        
        for action_key, pattern in patterns.items():
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                action_map = {
                    "stock_add": "STOCK_ADD",
                    "stock_add_natural": "STOCK_ADD",
                    "stock_remove": "STOCK_REMOVE",
                    "stock_remove_natural": "STOCK_REMOVE",
                    "stock_sale": "STOCK_SALE",
                    "stock_query": "STOCK_QUERY",
                    "stock_set": "STOCK_SET",
                    "stock_set_natural": "STOCK_SET",
                    "stock_history": "STOCK_HISTORY",
                    "stock_alerts": "STOCK_ALERTS",
                    "product_list": "PRODUCT_LIST",
                    "product_search": "PRODUCT_LIST",
                }
                
                # Extract groups, filtering out None values from alternation patterns
                groups = [g for g in match.groups() if g is not None]
                
                # Handle special cases
                if action_key == "stock_alerts":
                    # Alertas doesn't need product_id or quantity
                    return {
                        "action": action_map[action_key],
                        "product_id": None,
                        "quantity": None,
                        "confidence": 1.0
                    }
                
                if action_key == "product_list":
                    # Product list with optional page number
                    page = int(groups[0]) if groups else 1
                    return {
                        "action": action_map[action_key],
                        "product_id": None,
                        "quantity": None,
                        "page": page,
                        "search_term": None,
                        "confidence": 1.0
                    }
                
                if action_key == "product_search":
                    # Product search with optional page number
                    search_term = groups[0] if groups else None
                    page = int(groups[1]) if len(groups) > 1 else 1
                    return {
                        "action": action_map[action_key],
                        "product_id": None,
                        "quantity": None,
                        "page": page,
                        "search_term": search_term,
                        "confidence": 1.0
                    }
                
                if action_key == "stock_history":
                    # Historial only needs product_id
                    return {
                        "action": action_map[action_key],
                        "product_id": int(groups[0]),
                        "quantity": None,
                        "confidence": 1.0
                    }
                
                if action_key in ["stock_add_natural", "stock_remove_natural"]:
                    # Natural language patterns: "agregar 50 al producto 3" → quantity=50, product_id=3
                    # groups[0] = quantity, groups[1] = product_id
                    return {
                        "action": action_map[action_key],
                        "product_id": int(groups[1]),
                        "quantity": int(groups[0]),
                        "confidence": 1.0
                    }
                
                if action_key == "stock_set_natural":
                    # Natural language patterns: "reiniciar producto 3 con 5000" → product_id=3, quantity=5000
                    # groups[0] = product_id, groups[1] = quantity
                    return {
                        "action": action_map[action_key],
                        "product_id": int(groups[0]),
                        "quantity": int(groups[1]),
                        "confidence": 1.0
                    }
                
                if action_key == "stock_sale" and len(groups) >= 2:
                    # Handle "vendi 5 del producto 3" format
                    # Could be (quantity, product_id) or (product_id, quantity)
                    # Check which makes more sense based on typical values
                    num1, num2 = int(groups[0]), int(groups[1])
                    # Assume larger number is product_id, smaller is quantity
                    if "del producto" in text or "del" in text:
                        # "vendi 5 del producto 3" → quantity=5, product_id=3
                        quantity = num1
                        product_id = num2
                    else:
                        # "venta 3 5" → product_id=3, quantity=5
                        product_id = num1
                        quantity = num2
                else:
                    product_id = int(groups[0])
                    quantity = int(groups[1]) if len(groups) > 1 else None
                
                return {
                    "action": action_map[action_key],
                    "product_id": product_id,
                    "quantity": quantity,
                    "confidence": 1.0
                }
        
        return None
