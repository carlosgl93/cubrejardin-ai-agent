# Product List Feature

## Overview

Suppliers can now list and search their products directly through WhatsApp, viewing current stock levels, pricing, and availability status.

## WhatsApp Commands

### Basic List Commands
```
productos          → List all products (page 1)
mis productos      → Natural language variant
lista              → Shorthand
inventario         → Alternative command
```

### Pagination
```
productos pagina 2       → View page 2
productos página 3       → With accent
lista page 4             → English variant
```

### Search Commands
```
buscar tomates          → Search for products containing "tomates"
buscar manzanas         → Search for "manzanas"
productos tomates       → Alternative search format
lista pagina 2          → Search results pagination
```

## Response Format

### Standard Product List
```
📦 *Tus Productos* (Página 1/3)
Total: 58 productos

1️⃣ Producto XYZ (#123)
   📊 Stock: 120 / Min: 20
   💰 $1,500 por kg
   🟢 OK

2️⃣ Producto ABC (#124)
   📊 Stock: 45 / Min: 10
   💰 $2,500 por unidad
   🟢 OK

3️⃣ Producto DEF (#125)
   📊 Stock: 5 / Min: 15
   💰 $800 por kg
   🔴 Stock crítico

⚠️ 1 producto(s) con stock bajo
✅ 10 disponible(s)

💡 Para ver más: "productos pagina 2"
```

### Search Results
```
📦 *Tus Productos* (Página 1/2)
🔍 Búsqueda: 'tomates'
Total: 12 productos

1️⃣ Tomate Cherry (#456)
   📊 Stock: 200 / Min: 50
   💰 $3,500 por kg
   🟢 OK

2️⃣ Tomate Regular (#789)
   📊 Stock: 8 / Min: 20
   💰 $2,000 por kg
   🟡 Stock bajo

⚠️ 1 producto(s) con stock bajo
✅ 2 disponible(s)

💡 Para ver más: "productos pagina 2"
💡 Ver todos: "productos"
```

### No Results
```
📦 No se encontraron productos con 'xyz'
```

## Stock Status Indicators

| Emoji | Status | Condition |
|-------|--------|-----------|
| 🟢 | OK | Stock > minimum |
| 🟡 | Stock bajo | Stock ≤ minimum |
| 🔴 | Stock crítico | Stock ≤ minimum/2 |
| ⚫ | Sin stock | Stock = 0 |

## API Integration

### Endpoint
```http
GET /productos
Authorization: Bearer YOUR_API_KEY
```

### Query Parameters
- `page` - Page number (default: 1)
- `limit` - Items per page (default: 10, max: 50)
- `search` - Search term
- `sortBy` - Sort field (default: "nombre_producto")
- `sortOrder` - Sort direction (default: "asc")

### Response Structure
```json
{
  "success": true,
  "data": {
    "productos": [
      {
        "id_producto": 123,
        "nombre_producto": "Producto XYZ",
        "precio_unitario": 1500,
        "unit_type": "kg",
        "stock_actual": 120,
        "stock_minimo": 20,
        "disponible": true
      }
    ],
    "pagination": {
      "currentPage": 1,
      "totalPages": 3,
      "totalItems": 58,
      "hasNextPage": true
    }
  }
}
```

## Implementation Details

### Components Modified

1. **models/schemas.py**
   - Added `PRODUCT_LIST` action to `StockOperation`
   - Added `page` and `search_term` fields

2. **agents/stock_agent.py**
   - Added regex patterns for "productos", "lista", "inventario"
   - Added search pattern: "buscar [term]"
   - Added pagination pattern: "productos pagina 2"
   - Updated OpenAI prompt with product list examples

3. **services/mercadofiel_service.py**
   - Implemented `get_products()` method
   - Formats WhatsApp-friendly product list
   - Handles pagination and search
   - Shows stock status indicators

4. **agents/orchestrator.py**
   - Added `PRODUCT_LIST` action handler
   - Extracts page and search_term from parsed operation
   - Passes phone_number for supplier identification

5. **config/prompts.py**
   - Updated Guardian prompt to recognize product list commands

## Usage Examples

### List All Products
**User:** `productos`

**Bot Response:**
- Shows first 10 products
- Displays stock levels and pricing
- Indicates low stock items
- Shows pagination hint

### Search Products
**User:** `buscar manzanas`

**Bot Response:**
- Shows products matching "manzanas"
- Displays search term in header
- Provides option to clear search

### Navigate Pages
**User:** `productos pagina 2`

**Bot Response:**
- Shows products 11-20
- Updates page indicator
- Shows next page hint if available

## Supplier Identification

**Current Implementation:**
- Phone number is passed to `get_products()`
- API call is made without `proveedor` filter

**TODO:**
- Map WhatsApp phone number to `id_proveedor`
- Add `proveedor=<id>` query parameter
- Filter products by supplier

**Implementation Options:**
1. Database table: `phone_number` → `id_proveedor`
2. Mercado Fiel API: GET `/proveedores/by-phone/{phone}`
3. Configuration file: Hardcoded mappings for testing

## Testing

### Manual Testing Commands
```bash
# List products
"productos"
"mis productos"
"lista"
"inventario"

# Pagination
"productos pagina 2"
"lista página 3"

# Search
"buscar tomates"
"buscar manzanas pagina 2"

# Combined with other operations
"entrada 123 50"   # Then: "productos"
"stock 456"        # Then: "buscar 456"
```

### Expected Behaviors
- ✅ Lists products with stock status
- ✅ Shows pagination information
- ✅ Handles search queries
- ✅ Displays price and unit type
- ✅ Highlights low stock items
- ✅ Provides navigation hints

## Future Enhancements

1. **Supplier Filtering**
   - Implement phone → supplier mapping
   - Filter products by `proveedor` parameter

2. **Advanced Filters**
   - Filter by category: "productos categoria frutas"
   - Filter by availability: "productos disponibles"
   - Sort options: "productos por precio"

3. **Bulk Operations**
   - Quick stock update from list: "actualizar 123,456,789"
   - Export to CSV: "exportar productos"

4. **Product Details**
   - Deep link to product: "ver producto 123"
   - Show full description and images

5. **Analytics**
   - "productos mas vendidos"
   - "productos bajo stock"
   - "productos sin movimiento"

---

## Notes

- Maximum 10 products per page (WhatsApp readability)
- Search is case-insensitive
- Results sorted alphabetically by default
- Pagination required for >10 products
- Stock status calculated from `stock_actual` vs `stock_minimo`
