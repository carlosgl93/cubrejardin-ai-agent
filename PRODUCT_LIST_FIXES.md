# Product List Bug Fixes

## Issues Fixed

### Issue 1: "productos" classified as VALID_QUERY instead of STOCK_OPERATION

**Problem:** 
- User sends "productos" or "mis productos"
- Guardian classifies it as VALID_QUERY
- Message goes to RAG agent instead of Stock operations
- RAG has low confidence → escalates to human
- Results in 500 error due to pass_thread_control failing

**Root Cause:**
- Guardian AI was interpreting "productos" as a general product inquiry rather than a stock management command
- Prompt wasn't explicit enough about product listing being a stock operation

**Solution:**
1. Made Guardian prompt more explicit with "IMPORTANTE:" section
2. Separated product listing commands from other stock operations in the prompt
3. Emphasized that listing products is a STOCK_OPERATION, not a VALID_QUERY

**Files Changed:**
- `config/prompts.py` - Enhanced Guardian prompt with explicit product list classification

---

### Issue 2: Error message "no pude identificar el producto" for commands without product_id

**Problem:**
- Commands like "productos", "alertas", "mis productos" don't need a product_id
- Orchestrator was validating `if not product_id` for ALL stock operations
- These commands would fail with "no pude identificar el producto. Usa formato: entrada 123 50"
- Error message was not helpful - only showed one example

**Root Cause:**
- Missing check for actions that don't require product_id
- Error messages were static and unhelpful

**Solution:**
1. Added `actions_without_product_id` list: `["STOCK_ALERTS", "PRODUCT_LIST"]`
2. Skip product_id validation for these actions
3. Replaced all static error messages with comprehensive command list
4. New error message shows:
   - Categorized commands (Agregar, Ventas, Consultas, Gestión)
   - Natural language examples
   - Shorthand commands
   - All available operations

**Files Changed:**
- `agents/orchestrator.py` - Updated validation logic and error messages

**New Error Message Format:**
```
❌ No identifiqué el comando correctamente.

📋 *Comandos Disponibles:*

*Agregar Stock:*
• entrada 123 50
• +3 100
• agregar 20 del producto 456

*Ventas:*
• venta 123 5
• vendi 10 del producto 3
• -3 50 (quitar stock)

*Consultas:*
• stock 123
• ?3
• cuanto stock tiene el 456

*Gestión:*
• set 123 100 (establecer stock)
• historial 123
• alertas
• productos (listar tus productos)
• buscar tomates
```

---

### Issue 3: Missing logging for product list requests

**Problem:**
- No visibility into which phone numbers are requesting product lists
- Hard to debug supplier identification issues

**Solution:**
Added comprehensive logging at two levels:

1. **Orchestrator Level** (`agents/orchestrator.py`):
```python
logger.info("product_list_request", extra={
    "phone_number": user_number,
    "page": page,
    "search_term": search_term,
    "text": "Requesting product list for supplier"
})
```

2. **Service Level** (`services/mercadofiel_service.py`):
```python
logger.info("mercadofiel_get_products_request", extra={
    "phone_number": phone_number,
    "endpoint": endpoint,
    "params": params,
    "text": "Fetching products from Mercado Fiel API"
})
```

**Log Output Example:**
```json
{
  "level": "INFO",
  "logger": "whatsapp_ai_agent",
  "message": "product_list_request",
  "phone_number": "+5491123456789",
  "page": 1,
  "search_term": null,
  "text": "Requesting product list for supplier",
  "time": "2025-10-19T12:15:00+0000"
}

{
  "level": "INFO",
  "logger": "whatsapp_ai_agent",
  "message": "mercadofiel_get_products_request",
  "phone_number": "+5491123456789",
  "endpoint": "https://us-central1-mercadofiel.cloudfunctions.net/api/productos",
  "params": {
    "page": 1,
    "limit": 10,
    "sortBy": "nombre_producto",
    "sortOrder": "asc"
  },
  "text": "Fetching products from Mercado Fiel API",
  "time": "2025-10-19T12:15:01+0000"
}
```

**Benefits:**
- Track which phone numbers are using product list feature
- Debug supplier mapping when implemented
- Monitor API calls and parameters
- Audit trail for product list requests

---

## Files Modified Summary

1. **config/prompts.py**
   - Enhanced Guardian prompt with explicit STOCK_OPERATION classification for product lists
   - Added "IMPORTANTE:" section to emphasize product listing commands

2. **agents/orchestrator.py**
   - Added `actions_without_product_id` validation logic
   - Replaced all static error messages with comprehensive command list
   - Added logging for product list requests
   - Fixed product_id validation to skip PRODUCT_LIST and STOCK_ALERTS

3. **services/mercadofiel_service.py**
   - Added logging in `get_products()` method
   - Logs phone number, endpoint, and parameters for debugging

---

## Testing Instructions

### Test 1: Product List Command
```bash
# Send via WhatsApp
"productos"

# Expected:
✅ Message classified as STOCK_OPERATION
✅ Logs show: "product_list_request" with phone number
✅ Logs show: "mercadofiel_get_products_request" with API call
✅ Response shows product list
```

### Test 2: Natural Language Variants
```bash
"mis productos"
"lista"
"inventario"

# Expected:
✅ All classified as STOCK_OPERATION
✅ All execute product list handler
```

### Test 3: Commands Without Product ID
```bash
"alertas"
"productos"

# Expected:
✅ No "no pude identificar el producto" error
✅ Commands execute successfully
```

### Test 4: Invalid Commands
```bash
"xyz123"
"hacer algo"

# Expected:
✅ Shows comprehensive help message
✅ Lists all available commands
✅ Categorized by type
```

### Test 5: Check Logs
```bash
docker-compose logs -f api | grep -E "product_list|mercadofiel_get_products"

# Expected to see:
product_list_request with phone_number
mercadofiel_get_products_request with endpoint and params
```

---

## Next Steps

1. **Restart Container:**
   ```bash
   docker-compose restart api
   ```

2. **Test All Commands:**
   - "productos" → Should work now
   - "mis productos" → Should work now
   - "alertas" → Should work
   - Invalid command → Should show helpful message

3. **Monitor Logs:**
   - Check that phone numbers are being logged
   - Verify API parameters are correct
   - Use logs to implement supplier mapping

4. **Implement Supplier Mapping:**
   - Create phone → supplier_id mapping
   - Add `proveedor` parameter to API calls
   - Filter products by supplier

---

## Notes

- Guardian now explicitly recognizes product listing as stock operation
- All error messages are now helpful and comprehensive
- Phone numbers are logged for future supplier identification
- Product list feature is ready for testing with proper logging

---

## Deployment Checklist

- [x] Fix Guardian classification for "productos"
- [x] Add validation exception for actions without product_id
- [x] Replace static error messages with helpful command list
- [x] Add logging for phone numbers and API calls
- [ ] Restart container
- [ ] Test with real WhatsApp messages
- [ ] Verify logs show phone numbers
- [ ] Implement supplier mapping (future task)
