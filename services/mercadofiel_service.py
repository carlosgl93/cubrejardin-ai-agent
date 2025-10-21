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
            logger.warning("mercadofiel_no_api_key", extra={"info": "MERCADO_FIEL_API_KEY not configured"})

    def _get_headers(self, phone_number: Optional[str] = None) -> Dict[str, str]:
        """
        Build request headers with authentication and WhatsApp phone context.
        
        Args:
            phone_number: WhatsApp phone number making the request (e.g., "+56912345678")
        
        Returns:
            Dictionary of HTTP headers including X-WhatsApp-Phone if provided
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Client": "WhatsApp-Bot",
        }
        
        # Add WhatsApp phone number for supplier identification
        if phone_number:
            headers["X-WhatsApp-Phone"] = phone_number
            
        return headers

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
        product_id: str, 
        quantity: int,
        phone_number: Optional[str] = None,
        reason: str = "entrada",
        notes: Optional[str] = None
    ) -> str:
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
                    headers=self._get_headers(phone_number)
                )
                
                if 200 <= response.status_code < 300:
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
                    headers=self._get_headers(phone_number)
                )
                
                if 200 <= response.status_code < 300:
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

    async def query_stock(self, product_id: int, phone_number: Optional[str] = None) -> Dict[str, Any]:
        """Query current stock using GET /stock/analytics/product/:id endpoint."""
        
        endpoint = f"{self.base_url}/stock/analytics/product/{product_id}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    headers=self._get_headers(phone_number)
                )
                
                if 200 <= response.status_code < 300:
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
                            f"✅ Stock disponible: {available}"
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
        query_result = await self.query_stock(product_id, phone_number)
        
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
                    headers=self._get_headers(phone_number)
                )
                
                if 200 <= response.status_code < 300:
                    data = response.json()
                    logger.info("mercadofiel_set_stock_success", extra={
                        "product_id": product_id,
                        "from": current_stock,
                        "to": new_quantity
                    })
                    
                    stock_data = data.get("data", {})
                    producto = stock_data.get("producto", {})
                    stock_updated = data.get("stock_updated", {})
                    
                    return {
                        "success": True,
                        "message": (
                            f"✅ Stock Establecido\n\n"
                            f"📦 {producto.get('nombre_producto', product_name)}\n"
                            f"📊 Stock anterior: {stock_updated.get('stock_previo', current_stock)}\n"
                            f"⚙️ Stock nuevo: {stock_updated.get('stock_actual', new_quantity)}"
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

    async def get_history(
        self,
        product_id: int,
        phone_number: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get movement history for a product."""
        
        endpoint = f"{self.base_url}/stock/movements"
        params = {
            "id_producto": product_id,
            "metodo_registro": "WHATSAPP",
            "limit": limit
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    params=params,
                    headers=self._get_headers(phone_number)
                )
                
                if 200 <= response.status_code < 300:
                    data = response.json()
                    movements = data.get("data", [])
                    
                    if not movements:
                        return {
                            "success": True,
                            "message": f"📋 Historial de Movimientos\n\nNo hay movimientos registrados para el producto #{product_id}"
                        }
                    
                    # Format movements for WhatsApp
                    history_text = f"📋 Historial de Movimientos\n📦 Producto #{product_id}\n\n"
                    
                    for i, mov in enumerate(movements[:limit], 1):
                        tipo = mov.get("tipo_movimiento", "")
                        cantidad = mov.get("cantidad", 0)
                        fecha = mov.get("fecha_movimiento", "")
                        
                        emoji = "➕" if "ENTRADA" in tipo else "➖"
                        history_text += f"{i}. {emoji} {cantidad} unidades - {fecha[:10]}\n"
                    
                    logger.info("mercadofiel_history_success", extra={"product_id": product_id})
                    
                    return {
                        "success": True,
                        "message": history_text,
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
                    logger.error("mercadofiel_history_error", extra={
                        "status_code": response.status_code,
                        "error": error_msg
                    })
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                    
        except httpx.TimeoutException:
            logger.error("mercadofiel_timeout", extra={"operation": "get_history"})
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

    async def get_alerts(self, phone_number: Optional[str] = None, resolved: bool = False) -> Dict[str, Any]:
        """Get stock alerts."""
        
        endpoint = f"{self.base_url}/stock/alerts"
        params = {"resuelta": str(resolved).lower()}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    params=params,
                    headers=self._get_headers(phone_number)
                )
                
                if 200 <= response.status_code < 300:
                    data = response.json()
                    alerts = data.get("data", [])
                    
                    if not alerts:
                        return {
                            "success": True,
                            "message": "✅ No hay alertas de stock pendientes"
                        }
                    
                    # Format alerts for WhatsApp
                    alerts_text = f"⚠️ Alertas de Stock ({len(alerts)})\n\n"
                    
                    for i, alert in enumerate(alerts[:10], 1):
                        producto = alert.get("producto", {})
                        tipo = alert.get("tipo_alerta", "")
                        stock = alert.get("stock_actual", 0)
                        
                        alerts_text += f"{i}. 📦 {producto.get('nombre_producto', 'Producto')} #{producto.get('id', 'N/A')}\n"
                        alerts_text += f"   📊 Stock: {stock} unidades\n"
                        alerts_text += f"   🔴 {tipo}\n\n"
                    
                    logger.info("mercadofiel_alerts_success", extra={"count": len(alerts)})
                    
                    return {
                        "success": True,
                        "message": alerts_text,
                        "data": data
                    }
                
                else:
                    error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    error_msg = error_data.get("error", f"Error {response.status_code}")
                    logger.error("mercadofiel_alerts_error", extra={
                        "status_code": response.status_code,
                        "error": error_msg
                    })
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                    
        except httpx.TimeoutException:
            logger.error("mercadofiel_timeout", extra={"operation": "get_alerts"})
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

    async def get_products(
        self,
        phone_number: str,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        show_low_stock_only: bool = False
    ) -> Dict[str, Any]:
        """
        Get supplier's product list.
        
        Note: This requires mapping phone_number to proveedor ID.
        For now, we'll use the API without proveedor filter until we have that mapping.
        """
        
        endpoint = f"{self.base_url}/productos"
        
        params = {
            "page": page,
            "limit": min(limit, 50),  # Max 50 per API spec
            "sortBy": "nombre_producto",
            "sortOrder": "asc"
        }
        
        if search:
            params["search"] = search
        
        if show_low_stock_only:
            params["disponible"] = "true"
        
        # TODO: Map phone_number to proveedor ID
        # For now, this will return all products unless we add proveedor mapping
        # params["proveedor"] = supplier_id
        
        logger.info("mercadofiel_get_products_request", extra={
            "phone_number": phone_number,
            "endpoint": endpoint,
            "params": params,
            "text": "Fetching products from Mercado Fiel API"
        })
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    endpoint,
                    params=params,
                    headers=self._get_headers(phone_number)
                )
                
                if 200 <= response.status_code < 300:
                    data = response.json()
                    result_data = data.get("data", {})
                    productos = result_data.get("productos", [])
                    pagination = result_data.get("pagination", {})
                    
                    if not productos:
                        search_msg = f" con '{search}'" if search else ""
                        return {
                            "success": True,
                            "message": f"📦 No se encontraron productos{search_msg}"
                        }
                    
                    # Count products by stock status
                    low_stock_count = sum(1 for p in productos if p.get("stock_actual", 0) <= p.get("stock_minimo", 0))
                    available_count = sum(1 for p in productos if p.get("disponible", False))
                    
                    # Format products for WhatsApp
                    current_page = pagination.get("currentPage", page)
                    total_pages = pagination.get("totalPages", 1)
                    total_items = pagination.get("totalItems", len(productos))
                    
                    products_text = f"📦 *Tus Productos* (Página {current_page}/{total_pages})\n"
                    if search:
                        products_text += f"🔍 Búsqueda: '{search}'\n"
                    products_text += f"Total: {total_items} productos\n\n"
                    
                    # Show products
                    for i, producto in enumerate(productos[:limit], 1):
                        prod_id = producto.get("id_producto", "N/A")
                        nombre = producto.get("nombre_producto", "Sin nombre")
                        
                        # Ensure stock values are numbers
                        try:
                            stock_actual = int(producto.get("stock_actual", 0))
                        except (ValueError, TypeError):
                            stock_actual = 0
                        
                        try:
                            stock_minimo = int(producto.get("stock_minimo", 0))
                        except (ValueError, TypeError):
                            stock_minimo = 0
                        
                        precio_raw = producto.get("precio_unitario", 0)
                        # Ensure precio is a number
                        try:
                            precio = float(precio_raw) if precio_raw else 0
                        except (ValueError, TypeError):
                            precio = 0
                        unit_type = producto.get("unit_type", "unidad")
                        disponible = producto.get("disponible", False)
                        
                        # Determine stock status (with safe division)
                        if stock_actual == 0:
                            status_emoji = "⚫"
                            status_text = "Sin stock"
                        elif stock_minimo > 0 and stock_actual <= stock_minimo / 2:
                            status_emoji = "🔴"
                            status_text = "Stock crítico"
                        elif stock_actual <= stock_minimo:
                            status_emoji = "🟡"
                            status_text = "Stock bajo"
                        else:
                            status_emoji = "🟢"
                            status_text = "OK"
                        
                        products_text += f"{i}️⃣ {nombre} (#{prod_id})\n"
                        products_text += f"   📊 Stock: {stock_actual} / Min: {stock_minimo}\n"
                        products_text += f"   💰 ${precio:,.0f} por {unit_type}\n"
                        products_text += f"   {status_emoji} {status_text}\n"
                        
                        if not disponible:
                            products_text += f"   ⛔ No disponible\n"
                        
                        products_text += "\n"
                    
                    # Add summary footer
                    if low_stock_count > 0:
                        products_text += f"⚠️ {low_stock_count} producto(s) con stock bajo\n"
                    
                    products_text += f"✅ {available_count} disponible(s)\n"
                    
                    # Add pagination hint
                    if pagination.get("hasNextPage"):
                        next_page = current_page + 1
                        products_text += f"\n💡 Para ver más: \"productos pagina {next_page}\""
                    
                    if search:
                        products_text += f"\n💡 Ver todos: \"productos\""
                    
                    logger.info("mercadofiel_products_success", extra={
                        "phone": phone_number,
                        "count": len(productos),
                        "page": current_page
                    })
                    
                    return {
                        "success": True,
                        "message": products_text,
                        "data": data
                    }
                
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "message": "❌ No se encontraron productos"
                    }
                
                else:
                    error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    error_msg = error_data.get("error", f"Error {response.status_code}")
                    logger.error("mercadofiel_products_error", extra={
                        "status_code": response.status_code,
                        "error": error_msg
                    })
                    return {
                        "success": False,
                        "message": f"❌ {error_msg}"
                    }
                    
        except httpx.TimeoutException:
            logger.error("mercadofiel_timeout", extra={"operation": "get_products"})
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

    async def check_supplier_permissions(self, phone_number: str) -> bool:
        """
        Verify if the phone number is registered as a supplier.
        
        Note: This endpoint doesn't exist yet in Mercado Fiel API.
        Returns True for now - implement authorization in bot's database instead.
        """
        logger.warning("supplier_verification_not_implemented", extra={
            "phone": phone_number,
            "info": "Supplier verification should be handled in bot's database"
        })
        return True
