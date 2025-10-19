# Stock Management Integration - Quick Start

## What Was Added

The WhatsApp bot can now receive and process stock management commands from suppliers, 
integrating with your Mercado Fiel inventory system.

## Files Created/Modified

### New Files
- `agents/stock_agent.py` - Parses stock commands using AI + regex
- `services/mercadofiel_service.py` - HTTP client for Mercado Fiel API
- `docs/STOCK_MANAGEMENT.md` - Complete documentation
- `tests/test_stock_integration.py` - Unit tests

### Modified Files
- `config/prompts.py` - Added STOCK_OPERATION classification
- `agents/orchestrator.py` - Added stock operation handling
- `models/schemas.py` - Added StockOperation schema
- `.env.example` - Added Mercado Fiel API configuration
- `README.md` - Updated architecture and examples

## How It Works

### 1. User sends stock command via WhatsApp
```
entrada 123 50
```

### 2. Guardian detects STOCK_OPERATION intent
```python
category: "STOCK_OPERATION"
confidence: 0.95
```

### 3. StockAgent parses the command
```python
{
  "action": "STOCK_ADD",
  "product_id": 123,
  "quantity": 50,
  "confidence": 1.0
}
```

### 4. MercadoFielService calls your API
```http
POST https://us-central1-mercadofiel.cloudfunctions.net/api/stock/movements
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
X-Client: WhatsApp-Bot

{
  "id_producto": 123,
  "tipo_movimiento": "ENTRADA_REABASTECIMIENTO",
  "cantidad": 50,
  "metodo_registro": "WHATSAPP",
  "id_usuario_registro": null,
  "observaciones": "Agregado vía WhatsApp por +1234567890. Mensaje original: entrada 123 50"
}
```

### 5. User receives response
```
✅ Stock Actualizado

📦 Producto XYZ
📊 Stock anterior: 100
➕ Cantidad agregada: 50
📈 Stock actual: 150
```

## Setup Steps

### 1. Configure Environment Variables

Add to your `.env` file:

```bash
MERCADO_FIEL_API_URL=https://southamerica-west1-mercado-fiel.cloudfunctions.net/api
MERCADO_FIEL_API_KEY=your_secret_api_key_here
```

### 2. Deploy Updated Code

**Local:**
```bash
docker-compose down
docker-compose up --build
```

**Google Cloud Run (with Terraform):**
```bash
cd terraform

# Add secrets to Secret Manager
echo -n "https://your-api.com/api" | gcloud secrets create mercadofiel-api-url --data-file=-
echo -n "your_secret_key" | gcloud secrets create mercadofiel-api-key --data-file=-

# Update main.tf to include new secrets in Cloud Run environment
terraform apply
```

### 3. Test Stock Commands

Send these WhatsApp messages to your bot:

**Add Stock:**
```
entrada 123 50
+456 30
agregar 20 unidades del producto 789
```

**Remove Stock:**
```
salida 123 30
-456 10
quitar 5 unidades del producto 789
```

**Record Sale:**
```
venta 123 5
vendí 3 del producto 456
```

**Query Stock:**
```
stock 123
cuanto stock tiene el 456
?789
```

**Set Absolute Stock:**
```
set 123 100
establecer stock del 456 a 200
```

## Supported Command Formats

### Quick Commands (Regex Parsed - Fast)
- `entrada PRODUCT_ID QUANTITY` → Add stock
- `salida PRODUCT_ID QUANTITY` → Remove stock
- `venta PRODUCT_ID QUANTITY` → Record sale
- `stock PRODUCT_ID` → Query stock
- `set PRODUCT_ID QUANTITY` → Set absolute stock
- `+PRODUCT_ID QUANTITY` → Add (shorthand)
- `-PRODUCT_ID QUANTITY` → Remove (shorthand)
- `?PRODUCT_ID` → Query (shorthand)

### Natural Language (AI Parsed - Flexible)
- "agregar 20 unidades del producto 123"
- "quitar 5 del inventario del 456"
- "vendí 10 unidades del 789"
- "cuanto stock tiene el producto 123"
- "establecer el stock del 456 a 100 unidades"

The bot automatically tries regex first (faster), then falls back to OpenAI for complex messages.

## Expected API Contract

Your Mercado Fiel API implements these endpoints (already deployed):

### POST /stock/movements

Used for: Add stock, Remove stock, Record sales, Set stock (via adjustments)

**Request:**
```json
{
  "id_producto": 123,
  "tipo_movimiento": "ENTRADA_REABASTECIMIENTO",
  "cantidad": 50,
  "metodo_registro": "WHATSAPP",
  "id_usuario_registro": null,
  "observaciones": "Agregado vía WhatsApp por +1234567890"
}
```

**Movement Types:**
- `ENTRADA_REABASTECIMIENTO` - Add stock (general restock)
- `ENTRADA_COMPRA` - Stock from purchase
- `ENTRADA_DEVOLUCION` - Stock from customer return
- `ENTRADA_AJUSTE` - Manual adjustment (increase)
- `SALIDA_VENTA` - Record sale
- `SALIDA_AJUSTE` - Manual adjustment (decrease)
- `SALIDA_MERMA` - Damaged/expired stock
- `SALIDA_DEVOLUCION` - Return to supplier

**Success Response:**
```json
{
  "success": true,
  "data": {
    "id_movimiento": 456,
    "id_producto": 123,
    "tipo_movimiento": "ENTRADA_REABASTECIMIENTO",
    "cantidad": 50,
    "stock_previo": 100,
    "stock_resultante": 150,
    "fecha_movimiento": "2025-10-15T14:30:00Z",
    "producto": {
      "id_producto": 123,
      "nombre_producto": "Producto XYZ"
    }
  },
  "stock_updated": {
    "stock_previo": 100,
    "stock_actual": 150
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Product not found"
}
```

### GET /stock/analytics/product/:id

Used for: Query current stock levels

**Success Response:**
```json
{
  "success": true,
  "data": {
    "product": {
      "id_producto": 123,
      "nombre_producto": "Producto XYZ",
      "stock_actual": 120,
      "stock_minimo": 20,
      "stock_maximo": 500,
      "ultimo_reabastecimiento": "2025-10-15T14:30:00Z"
    },
    "active_reservations": {
      "count": 2,
      "total_quantity": 15,
      "available_stock": 105
    },
    "unresolved_alerts": 0
  }
}
```

**Note:** The bot automatically calls this endpoint when implementing "set stock" to calculate the difference.

## Monitoring

Check logs for stock operations:

```bash
# Docker Compose
docker-compose logs -f api | grep stock

# Cloud Run
gcloud logging read "resource.type=cloud_run_revision AND textPayload=~stock" --limit 50
```

Key log events:
- `stock_operation_detected` - Guardian classified as stock operation
- `stock_command_parsed` - Command successfully parsed
- `mercadofiel_webhook_success` - API call succeeded
- `mercadofiel_webhook_error` - API call failed

## Troubleshooting

### "No pude entender el comando"
- Command format not recognized
- Check supported patterns in docs/STOCK_MANAGEMENT.md
- Review logs for parsing errors

### "Error de conexión"
- MERCADO_FIEL_API_URL not configured
- API is down or unreachable
- Check network/firewall settings

### "Producto no encontrado"
- Product ID doesn't exist in Mercado Fiel
- User doesn't have permissions for this product
- Check supplier authorization

### "Tiempo de espera agotado"
- API taking >10 seconds to respond
- Increase timeout in services/mercadofiel_service.py
- Optimize Mercado Fiel API performance

## Next Steps

1. **Configure API credentials** in production environment
2. **Deploy updated code** to Cloud Run or Docker
3. **Test with real supplier** phone numbers
4. **Monitor logs** for first few operations
5. **Iterate on error messages** based on user feedback

## Security Notes

- All API calls include `Authorization: Bearer` header
- Supplier phone numbers verified via `/suppliers/verify` endpoint
- Unauthorized users receive error messages
- API keys stored in Secret Manager (production)
- Never commit API keys to git

## Support

For detailed documentation, see:
- [docs/STOCK_MANAGEMENT.md](docs/STOCK_MANAGEMENT.md) - Complete guide
- [README.md](README.md) - Overall architecture
- [tests/test_stock_integration.py](tests/test_stock_integration.py) - Usage examples

For issues or questions, check the logs first:
```bash
docker-compose logs -f api
```
