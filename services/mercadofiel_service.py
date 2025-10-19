"""Mercado Fiel API client for stock operations."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from utils import logger


class MercadoFielService:
    """Client for interacting with Mercado Fiel stock API."""

    def __init__(self) -> None:
        self.base_url = os.getenv("MERCADO_FIEL_API_URL", "https://us-central1-mercadofiel.cloudfunctions.net/api")
        self.api_key = os.getenv("MERCADO_FIEL_API_KEY", "")
        self.timeout = 15.0  # Increased to 15 seconds per API spec
        
        if not self.api_key:
            logger.warning("mercadofiel_no_api_key", extra={"message": "MERCADO_FIEL_API_KEY not configured"})

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Client": "WhatsApp-Bot",
        }

    def _map_action_to_movement_type(self, action: str, is_sale: bool = False) -> str:
        """Map stock action to Mercado Fiel movement type."""
        mapping = {
            "STOCK_ADD": "ENTRADA_REABASTECIMIENTO",
            "STOCK_REMOVE": "SALIDA_AJUSTE",
            "STOCK_SALE": "SALIDA_VENTA",
            "STOCK_SET": None,  # Handled separately
        }
        
        if is_sale or action == "STOCK_SALE":
            return "SALIDA_VENTA"
        
        return mapping.get(action, "ENTRADA_REABASTECIMIENTO")

    async def add_stock(
        self,
        product_id: int,
        quantity: int,
        phone_number: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add stock using POST /stock/movements endpoint."""
        
        endpoint = f"{self.base_url}/stock/movements"
        
        payload = {
            "id_producto": product_id,
            "tipo_movimiento": "ENTRADA_REABASTECIMIENTO",
            "cantidad": quantity,
            "metodo_registro": "WHATSAPP",
            "id_usuario_registro": None,
            "observaciones": notes or f"Agregado vía WhatsApp por {phone_number}"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info("mercadofiel_add_stock_success", extra={
                        "product_id": product_id,
                        "quantity": quantity,
                        "phone": phone_number
                    })
                    
                    # Format response for WhatsApp
                    stock_data = data.get("data", {})
                    producto = stock_data.get("producto", {})
                    stock_updated = data.get("stock_updated", {})
                    
                    return {
                        "success": True,
                        "message": (
                            f"✅ Stock Actualizado\n\n"
                            f"📦 {producto.get('nombre_producto', 'Producto')}\n"
                            f"📊 Stock anterior: {stock_updated.get('stock_previo', 0)}\n"
                            f"➕ Cantidad agregada: {quantity}\n"
                            f"📈 Stock actual: {stock_updated.get('stock_actual', 0)}"
                        ),
                        "data": data
                    }
                
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "message": f"❌ Producto #{product_id} no encontrado"
                    }
                
                else:
                    error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    error_msg = error_data.get("error", f"Error {response.status_code}")
                    logger.error("mercadofiel_add_stock_error", extra={
                        "status_code": response.status_code,
                        "error": error_msg
                    })
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                    
        except httpx.TimeoutException:
            logger.error("mercadofiel_timeout", extra={"operation": "add_stock"})
            return {
                "success": False,
                "message": "⏱️ Tiempo agotado. Intenta nuevamente"
            }
        except Exception as e:
            logger.error("mercadofiel_exception", extra={"error": str(e)})
            return {
                "success": False,
                "message": f"❌ Error de conexión: {str(e)}"
            }

    async def remove_stock(
        self,
        product_id: int,
        quantity: int,
        phone_number: str,
        is_sale: bool = False,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Remove stock using POST /stock/movements endpoint."""
        
        endpoint = f"{self.base_url}/stock/movements"
        
        movement_type = "SALIDA_VENTA" if is_sale else "SALIDA_AJUSTE"
        
        payload = {
            "id_producto": product_id,
            "tipo_movimiento": movement_type,
            "cantidad": quantity,
            "metodo_registro": "WHATSAPP",
            "id_usuario_registro": None,
            "observaciones": notes or f"{'Venta registrada' if is_sale else 'Salida'} vía WhatsApp por {phone_number}"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info("mercadofiel_remove_stock_success", extra={
                        "product_id": product_id,
                        "quantity": quantity,
                        "is_sale": is_sale
                    })
                    
                    stock_data = data.get("data", {})
                    producto = stock_data.get("producto", {})
                    stock_updated = data.get("stock_updated", {})
                    
                    emoji = "💰" if is_sale else "📤"
                    action_text = "Venta Registrada" if is_sale else "Stock Reducido"
                    
                    return {
                        "success": True,
                        "message": (
                            f"✅ {action_text}\n\n"
                            f"📦 {producto.get('nombre_producto', 'Producto')}\n"
                            f"📊 Stock anterior: {stock_updated.get('stock_previo', 0)}\n"
                            f"➖ Cantidad: {quantity}\n"
                            f"📉 Stock actual: {stock_updated.get('stock_actual', 0)}"
                        ),
                        "data": data
                    }
                
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "message": f"❌ Producto #{product_id} no encontrado"
                    }
                
                elif response.status_code == 400:
                    error_data = response.json()
                    error_msg = error_data.get("error", "")
                    
                    if "insufficient stock" in error_msg.lower():
                        return {
                            "success": False,
                            "message": f"❌ Stock insuficiente para esta operación"
                        }
                    
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                
                else:
                    error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    error_msg = error_data.get("error", f"Error {response.status_code}")
                    logger.error("mercadofiel_remove_stock_error", extra={
                        "status_code": response.status_code,
                        "error": error_msg
                    })
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                    
        except httpx.TimeoutException:
            logger.error("mercadofiel_timeout", extra={"operation": "remove_stock"})
            return {
                "success": False,
                "message": "⏱️ Tiempo agotado. Intenta nuevamente"
            }
        except Exception as e:
            logger.error("mercadofiel_exception", extra={"error": str(e)})
            return {
                "success": False,
                "message": f"❌ Error de conexión: {str(e)}"
            }

    async def query_stock(self, product_id: int) -> Dict[str, Any]:
        """Query current stock using GET /stock/analytics/product/:id endpoint."""
        
        endpoint = f"{self.base_url}/stock/analytics/product/{product_id}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    product_data = data.get("data", {}).get("product", {})
                    reservations = data.get("data", {}).get("active_reservations", {})
                    
                    stock_actual = product_data.get("stock_actual", 0)
                    stock_minimo = product_data.get("stock_minimo", 0)
                    stock_maximo = product_data.get("stock_maximo", 0)
                    reserved = reservations.get("total_quantity", 0)
                    available = reservations.get("available_stock", stock_actual)
                    
                    # Determine status
                    if stock_actual <= stock_minimo:
                        status = "🔴 BAJO"
                        warning = "\n⚠️ ¡Stock bajo! Considera reabastecer"
                    elif stock_actual <= stock_minimo * 1.5:
                        status = "🟡 MEDIO"
                        warning = ""
                    else:
                        status = "🟢 OK"
                        warning = ""
                    
                    logger.info("mercadofiel_query_success", extra={
                        "product_id": product_id,
                        "stock_actual": stock_actual
                    })
                    
                    return {
                        "success": True,
                        "message": (
                            f"📊 Consulta de Stock\n\n"
                            f"📦 {product_data.get('nombre_producto', 'Producto')}\n"
                            f"📈 Stock actual: {stock_actual}\n"
                            f"🔒 Stock reservado: {reserved}\n"
                            f"✅ Stock disponible: {available}\n"
                            f"⚠️ Stock mínimo: {stock_minimo}\n"
                            f"📊 Stock máximo: {stock_maximo}\n"
                            f"📊 Estado: {status}{warning}"
                        ),
                        "data": data
                    }
                
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "message": f"❌ Producto #{product_id} no encontrado"
                    }
                
                else:
                    error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    error_msg = error_data.get("error", f"Error {response.status_code}")
                    logger.error("mercadofiel_query_error", extra={
                        "status_code": response.status_code,
                        "error": error_msg
                    })
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                    
        except httpx.TimeoutException:
            logger.error("mercadofiel_timeout", extra={"operation": "query_stock"})
            return {
                "success": False,
                "message": "⏱️ Tiempo agotado. Intenta nuevamente"
            }
        except Exception as e:
            logger.error("mercadofiel_exception", extra={"error": str(e)})
            return {
                "success": False,
                "message": f"❌ Error de conexión: {str(e)}"
            }

    async def set_stock(
        self,
        product_id: int,
        new_quantity: int,
        phone_number: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Set absolute stock level.
        
        Requires two API calls:
        1. GET current stock
        2. POST adjustment movement
        """
        
        # Step 1: Get current stock
        query_result = await self.query_stock(product_id)
        
        if not query_result.get("success"):
            return query_result
        
        # Extract current stock from response
        product_data = query_result.get("data", {}).get("data", {}).get("product", {})
        current_stock = product_data.get("stock_actual", 0)
        product_name = product_data.get("nombre_producto", "Producto")
        
        # Calculate difference
        difference = new_quantity - current_stock
        
        if difference == 0:
            return {
                "success": True,
                "message": (
                    f"ℹ️ Stock Sin Cambios\n\n"
                    f"📦 {product_name}\n"
                    f"📊 Stock actual: {current_stock}\n"
                    f"El stock ya está en {new_quantity} unidades"
                )
            }
        
        # Step 2: Create adjustment movement
        endpoint = f"{self.base_url}/stock/movements"
        
        if difference > 0:
            # Need to add stock
            movement_type = "ENTRADA_AJUSTE"
            quantity = difference
        else:
            # Need to remove stock
            movement_type = "SALIDA_AJUSTE"
            quantity = abs(difference)
        
        payload = {
            "id_producto": product_id,
            "tipo_movimiento": movement_type,
            "cantidad": quantity,
            "metodo_registro": "WHATSAPP",
            "id_usuario_registro": None,
            "observaciones": notes or f"Ajuste absoluto vía WhatsApp por {phone_number}. Stock establecido a {new_quantity}"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info("mercadofiel_set_stock_success", extra={
                        "product_id": product_id,
                        "from": current_stock,
                        "to": new_quantity
                    })
                    
                    return {
                        "success": True,
                        "message": (
                            f"✅ Stock Establecido\n\n"
                            f"📦 {product_name}\n"
                            f"📊 Stock anterior: {current_stock}\n"
                            f"⚙️ Stock nuevo: {new_quantity}"
                        ),
                        "data": data
                    }
                
                elif response.status_code == 400:
                    error_data = response.json()
                    error_msg = error_data.get("error", "")
                    
                    if "insufficient stock" in error_msg.lower():
                        return {
                            "success": False,
                            "message": f"❌ No se puede reducir el stock a {new_quantity}. Stock insuficiente"
                        }
                    
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                
                else:
                    error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    error_msg = error_data.get("error", f"Error {response.status_code}")
                    logger.error("mercadofiel_set_stock_error", extra={
                        "status_code": response.status_code,
                        "error": error_msg
                    })
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                    
        except httpx.TimeoutException:
            logger.error("mercadofiel_timeout", extra={"operation": "set_stock"})
            return {
                "success": False,
                "message": "⏱️ Tiempo agotado. Intenta nuevamente"
            }
        except Exception as e:
            logger.error("mercadofiel_exception", extra={"error": str(e)})
            return {
                "success": False,
                "message": f"❌ Error de conexión: {str(e)}"
            }

    async def get_product_stock(self, product_id: int, phone_number: str) -> Dict[str, Any]:
        """
        Legacy method - redirects to query_stock.
        Kept for backward compatibility.
        """
        return await self.query_stock(product_id)

    async def check_supplier_permissions(self, phone_number: str) -> bool:
        """
        Verify if the phone number is registered as a supplier.
        
        Note: This endpoint doesn't exist yet in Mercado Fiel API.
        Returns True for now - implement authorization in bot's database instead.
        """
        logger.warning("supplier_verification_not_implemented", extra={
            "phone": phone_number,
            "message": "Supplier verification should be handled in bot's database"
        })
        return True
