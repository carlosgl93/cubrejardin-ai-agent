# Stock Management Integration

This document explains how the WhatsApp bot integrates with Mercado Fiel's stock management system to allow suppliers to manage inventory via WhatsApp messages.

## Overview

The stock management feature allows authorized suppliers to:
- **Add stock**: Register new inventory entries
- **Remove stock**: Deduct inventory (waste, adjustments)
- **Record sales**: Track sold units
- **Query stock**: Check current inventory levels
- **Set absolute stock**: Override current stock count

## Architecture

### Components

1. **StockAgent** (`agents/stock_agent.py`)
   - Parses natural language stock commands
   - Supports both AI-powered and regex-based parsing
   - Formats API responses into user-friendly messages

2. **MercadoFielService** (`services/mercadofiel_service.py`)
   - HTTP client for Mercado Fiel REST API
   - Handles authentication and error handling
   - Verifies supplier permissions

3. **Guardian Agent** (`agents/guardian_agent.py`)
   - Detects `STOCK_OPERATION` intent
   - Routes stock messages to StockAgent

4. **Orchestrator** (`agents/orchestrator.py`)
   - Coordinates stock operation workflow
   - Stores operation logs in conversation history

## Message Formats

### Supported Commands

The bot recognizes multiple natural language patterns:

#### Add Stock
```
entrada 123 50
+123 50
agregar stock producto 123 cantidad 50
stock add 123 50
```

#### Remove Stock
```
salida 123 30
-123 30
quitar stock producto 123 cantidad 30
stock remove 123 30
```

#### Record Sale
```
venta 123 5
sale 123 5
vendí 5 unidades del producto 123
```

#### Query Stock
```
stock 123
?123
cuanto stock tiene el 123
consulta producto 123
```

#### Set Absolute Stock
```
set 123 100
establecer stock 123 a 100
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Mercado Fiel Stock Management API
MERCADO_FIEL_API_URL=https://your-mercadofiel-api.com/api
MERCADO_FIEL_API_KEY=your_api_key_here
```

### API Endpoints

The integration expects the following Mercado Fiel endpoints:

- `POST /stock/webhook` - Main stock operation endpoint
- `GET /stock/product/:id` - Query product stock
- `POST /suppliers/verify` - Verify supplier authorization

### Request Format

Stock webhook payload:
```json
{
  "phone": "+1234567890",
  "message": "entrada 123 50",
  "product_id": 123,
  "quantity": 50,
  "action": "STOCK_ADD"
}
```

### Response Format

Expected API response:
```json
{
  "success": true,
  "response": "✅ Stock agregado: Producto XYZ ahora tiene 150 unidades"
}
```

Or on error:
```json
{
  "success": false,
  "response": "❌ Producto no encontrado"
}
```

## Workflow

1. **User sends WhatsApp message**: `"entrada 123 50"`

2. **Guardian classifies**: Detects `STOCK_OPERATION` category

3. **StockAgent parses command**:
   - Tries quick regex match first (faster)
   - Falls back to OpenAI parsing for complex messages
   - Extracts: `action=STOCK_ADD, product_id=123, quantity=50`

4. **Orchestrator calls MercadoFielService**:
   - Sends parsed data to `/stock/webhook`
   - Includes user's phone number for authorization

5. **Response formatting**:
   - Receives API response with success/error message
   - StockAgent formats user-friendly reply
   - Sends WhatsApp response

6. **Logging**:
   - Operation stored in conversation history
   - Includes stock operation metadata and API result

## Security

### Authorization

- Each request includes `X-WhatsApp-Number` header
- Mercado Fiel API verifies supplier permissions
- Unauthorized users receive error response

### API Authentication

- All requests include `Authorization: Bearer <token>`
- API key configured via `MERCADO_FIEL_API_KEY` env var

## Error Handling

### Common Errors

**Product not found:**
```
❌ Producto 123 no encontrado
```

**Insufficient stock:**
```
❌ Stock insuficiente para la operación
```

**Unauthorized supplier:**
```
❌ No tienes permisos para gestionar este producto
```

**Network timeout:**
```
⏱️ Tiempo de espera agotado. Intenta nuevamente.
```

**Invalid command:**
```
❌ No pude entender el comando de stock. Usa formatos como:
- entrada 123 50
- salida 123 30
- venta 123 5
- stock 123
```

## Testing

### Manual Testing

Send WhatsApp messages to the bot:

```
entrada 123 50          → Should add 50 units to product 123
salida 123 30           → Should remove 30 units from product 123
venta 123 5             → Should record sale of 5 units
stock 123               → Should return current stock level
set 123 100             → Should set absolute stock to 100
```

### Unit Tests

```bash
# Run stock integration tests
pytest tests/test_stock_integration.py -v

# Test specific scenarios
pytest tests/test_stock_integration.py::test_stock_add -v
pytest tests/test_stock_integration.py::test_unauthorized_supplier -v
```

## Monitoring

### Logs

Stock operations are logged with the following events:

- `stock_operation_detected` - Guardian identified stock intent
- `stock_command_parsed` - StockAgent extracted operation details
- `mercadofiel_webhook_success` - API call succeeded
- `mercadofiel_webhook_error` - API call failed
- `stock_parsing_error` - Command parsing failed

### Metrics to Track

1. **Success rate**: Percentage of successful stock operations
2. **Parse accuracy**: Ratio of quick_parse vs AI parsing
3. **Response time**: API latency for stock operations
4. **Error types**: Distribution of error categories

## Deployment

### Docker

The stock management feature is included in the Docker image. Ensure environment variables are set:

```bash
docker-compose up -d
```

### Google Cloud Run

Update Terraform secrets:

```bash
# Add to terraform/main.tf secrets
MERCADO_FIEL_API_URL
MERCADO_FIEL_API_KEY
```

Deploy:
```bash
cd terraform
terraform apply
```

## Future Enhancements

- [ ] Bulk operations (multiple products in one message)
- [ ] Stock alerts integration (low stock notifications)
- [ ] Reservation management via WhatsApp
- [ ] Multi-language support
- [ ] Voice message support for stock commands
- [ ] Barcode/QR code scanning integration
