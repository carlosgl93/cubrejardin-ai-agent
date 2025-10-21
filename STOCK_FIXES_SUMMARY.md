# Stock Management Fixes Summary

## Issues Fixed

### 1. ✅ "Error 201" Message for Successful Operations
**Problem:** API returns 201 (Created) status code on success, but was being formatted as "Error 201"

**Solution:** Updated `MercadoFielService` to accept all 2xx status codes (200-299) as success
- Modified `add_stock()` method
- Modified `remove_stock()` method

**Files Changed:**
- `services/mercadofiel_service.py`

---

### 2. ✅ Natural Language Sales Commands Not Recognized
**Problem:** Messages like "Vendi 5 del producto 3" were not being parsed correctly

**Solution:** 
- Enhanced OpenAI system prompt with better examples and variations
- Improved regex patterns to handle:
  - With/without accents: "vendi", "vendí"
  - Different word orders: "vendi 5 del producto 3" vs "venta 3 5"
  - Natural language: "se vendieron", "venta de"
- Added explicit instruction that "vendi/vendí/venta" always maps to STOCK_SALE (not STOCK_REMOVE)

**Files Changed:**
- `agents/stock_agent.py` - Updated `parse_stock_command()` and `quick_parse()`

---

### 3. ✅ Stock Query Returns Too Much Information
**Problem:** Query response included stock_actual, reserved, available, minimum, maximum, and status - too verbose

**Solution:** Simplified response to show only:
- Product name
- Stock disponible (available stock)

**Before:**
```
📊 Consulta de Stock
📦 [Product Name]
📈 Stock actual: [stock]
🔒 Reservado: [reserved]
✅ Disponible: [available]
⚠️ Mínimo: [minimum]
📊 Estado: [status]
```

**After:**
```
📊 Consulta de Stock
📦 [Product Name]
✅ Stock disponible: [available]
```

**Files Changed:**
- `services/mercadofiel_service.py` - `query_stock()` method

---

### 4. ✅ Shorthand Commands Not Working
**Problem:** Commands like "+3 500", "?3", "historial 3" were not being recognized

**Solution:**
- Updated regex patterns to allow optional spaces: `+3 500` or `+ 3 500`
- Added support for new commands:
  - `historial <product_id>` - View movement history
  - `alertas` - View stock alerts
- Updated Guardian prompt to recognize shorthand patterns
- Implemented `get_history()` and `get_alerts()` methods in MercadoFielService
- Added STOCK_HISTORY and STOCK_ALERTS actions to orchestrator

**Files Changed:**
- `agents/stock_agent.py` - Enhanced regex patterns, added history/alerts support
- `config/prompts.py` - Updated Guardian prompt with shorthand examples
- `services/mercadofiel_service.py` - Added `get_history()` and `get_alerts()` methods
- `agents/orchestrator.py` - Added handlers for STOCK_HISTORY and STOCK_ALERTS
- `models/schemas.py` - Updated StockOperation schema with new actions

---

## New Features Added

### Historial Command
View recent stock movements for a product:
```
historial 123
movimientos 456
history 789
```

**Response Format:**
```
📋 Historial de Movimientos
📦 Producto #123

1. ➕ 50 unidades - 2025-10-15
2. ➖ 30 unidades - 2025-10-16
3. ➕ 100 unidades - 2025-10-18
```

### Alertas Command
View pending stock alerts:
```
alertas
alerts
ver alertas
```

**Response Format:**
```
⚠️ Alertas de Stock (2)

1. 📦 Producto ABC #123
   📊 Stock: 5 unidades
   🔴 STOCK_BAJO

2. 📦 Producto XYZ #456
   📊 Stock: 0 unidades
   🔴 SIN_STOCK
```

---

## Updated Command Reference

### Quick Commands (Regex)
```
entrada <product_id> <quantity>     → Add stock
salida <product_id> <quantity>      → Remove stock
venta <product_id> <quantity>       → Record sale
stock <product_id>                  → Query stock
set <product_id> <quantity>         → Set absolute stock
+<product_id> <quantity>            → Add (shorthand)
-<product_id> <quantity>            → Remove (shorthand)
?<product_id>                       → Query (shorthand)
historial <product_id>              → Movement history
alertas                             → List alerts
```

### Natural Language Examples
- ✅ "agregar 20 unidades del producto 123"
- ✅ "vendí 5 del producto 456"
- ✅ "vendi 10 del 3" (without accent)
- ✅ "se vendieron 20 del producto 789"
- ✅ "cuanto stock tiene el 123"
- ✅ "establecer stock del 123 a 100"
- ✅ "historial del producto 3"
- ✅ "ver alertas"

---

## Testing Instructions

1. **Restart the container** to apply all changes:
   ```bash
   docker-compose restart api
   ```

2. **Test successful operations** (should no longer show "Error 201"):
   ```
   entrada 3 50
   ```
   Expected: ✅ Stock Actualizado message

3. **Test natural language sales**:
   ```
   Vendi 5 del producto 3
   vendí 10 del 456
   ```
   Expected: ✅ Venta Registrada message

4. **Test simplified stock query**:
   ```
   stock 3
   ```
   Expected: Only shows available stock, not all details

5. **Test shorthand commands**:
   ```
   +3 500
   - 3 50
   ?3
   ```
   Expected: All commands work correctly

6. **Test new features**:
   ```
   historial 3
   alertas
   ```
   Expected: Shows formatted movement history and alerts

---

## Files Modified

1. `services/mercadofiel_service.py` - API client improvements
2. `agents/stock_agent.py` - Parser improvements
3. `agents/orchestrator.py` - Added new action handlers
4. `config/prompts.py` - Enhanced Guardian detection
5. `models/schemas.py` - Updated StockOperation schema

---

## Deployment Checklist

- [x] Fix 201 status code handling
- [x] Improve natural language parsing for sales
- [x] Simplify stock query response
- [x] Support shorthand commands (+, -, ?)
- [x] Implement historial command
- [x] Implement alertas command
- [x] Update Guardian prompt
- [x] Update error messages
- [ ] Restart container
- [ ] Test all commands with real WhatsApp messages
- [ ] Verify Mercado Fiel API integration

---

## Next Steps

1. Restart the API container: `docker-compose restart api`
2. Test with real WhatsApp messages
3. Monitor logs for any parsing issues
4. Verify all API calls complete successfully
