# Migración de Stock Management a FAQ System

## Resumen de Cambios

Este documento describe la migración del sistema de gestión de inventario (stock management) a un sistema de respuesta a preguntas frecuentes (FAQ) para CubreJardin.

## Archivos Nuevos Creados

### 1. `data/documents/faqs.md`
- Archivo con todas las preguntas frecuentes y respuestas
- Mantiene el tono, ortografía y estilo EXACTO de las respuestas originales
- Incluye errores ortográficos intencionales (distintsas, tambine, tines, etc.)
- Organizado en dos secciones principales:
  - **General**: ubicación, regiones, instalación, pedidos, pagos, paisajismo
  - **Tiqui Tiqui**: información del producto, conejos, sombra, pasto, precios, cobertura

### 2. `agents/faq_agent.py`
- Nuevo agente para manejar preguntas frecuentes
- Reemplaza completamente a `stock_agent.py`
- Funciones principales:
  - `identify_faq_intent()`: identifica la categoría de la pregunta FAQ
  - `generate_faq_response()`: genera respuesta manteniendo el tono original
- Categorías de FAQ soportadas:
  - LOCATION, REGIONS, INSTALLATION, MINIMUM_ORDER
  - LANDSCAPING, OTHER_PRODUCTS, WEB_PURCHASE
  - PAYMENT, ORDER_PROCESS
  - TIQUI_INFO, TIQUI_RABBITS, TIQUI_SHADE
  - TIQUI_ON_GRASS, TIQUI_MIX_GRASS, TIQUI_PRICE, TIQUI_COVERAGE
  - GENERAL, NOT_FAQ

## Archivos Modificados

### 1. `config/prompts.py`
- **guardian_prompt()**: 
  - Eliminadas todas las referencias a STOCK_OPERATION
  - Enfocado en clasificar preguntas sobre productos, plantas y servicios como VALID_QUERY
  - Simplificadas las categorías: VALID_QUERY, SPAM, SENSITIVE, ESCALATION_REQUEST, GREETING, OFF_TOPIC

- **rag_prompt()**: 
  - Añadida instrucción explícita: "Mantén EXACTAMENTE el tono, ortografía y estilo"
  - NO corregir errores ortográficos originales
  - Mantener emojis si están presentes

### 2. `agents/orchestrator.py`
- Importación cambiada: `from .faq_agent import FAQAgent` (antes StockAgent)
- Inicialización: `self.faq = FAQAgent(openai_service)` (antes self.stock)
- **Eliminado completamente**: Todo el bloque de manejo de STOCK_OPERATION (~150 líneas)
- Ahora todas las VALID_QUERY van directamente al agente RAG
- El agente RAG utiliza el vector store con las FAQs para responder

### 3. `agents/__init__.py`
- Añadido: `from .faq_agent import FAQAgent`
- Actualizado `__all__` para exportar FAQAgent

### 4. `README.md`
- Título actualizado: "WhatsApp AI Agent - CubreJardin FAQ Bot"
- Sección "Pruebas Recomendadas" completamente reescrita con ejemplos de FAQs
- Diagrama de arquitectura actualizado (eliminado Stock Agent y Mercado Fiel API)
- Componentes Clave actualizado con descripción del FAQ Agent
- Sección "Ejemplos de Comandos" reemplazada con "Ejemplos de Consultas"

## Archivos Obsoletos (No se eliminaron, pero ya no se usan)

- `agents/stock_agent.py` - Reemplazado por `faq_agent.py`
- `services/mercadofiel_service.py` - Ya no se utiliza
- `docs/STOCK_MANAGEMENT.md` - Documentación obsoleta
- Varios archivos de documentación relacionados con stock:
  - `STOCK_FIXES_SUMMARY.md`
  - `STOCK_QUICKSTART.md`
  - `NATURAL_LANGUAGE_STOCK_IMPLEMENTATION.md`
  - `PRODUCT_LIST_FIXES.md`

## Características Importantes del Nuevo Sistema

### 1. Preservación del Tono Original
El sistema está específicamente diseñado para:
- Mantener errores ortográficos originales (distintsas, tambine, tines, etc.)
- Preservar mayúsculas/minúsculas exactas
- Mantener emojis (🌱, ☀️, 💧, 🐶, 🐱, 🏃🏻‍♀️, 🏃🏻‍♂️)
- Mantener el estilo conversacional y amigable
- Preservar formato y estructura de las respuestas largas (ej: info del tiqui tiqui)

### 2. Identificación Inteligente de Preguntas
- Usa OpenAI para identificar la intención de la pregunta
- Extrae información relevante (metros cuadrados, comuna, etc.)
- Calcula automáticamente cantidades cuando es necesario
- Mantiene el formato de las respuestas (ej: cálculos de m2)

### 3. Flujo de Procesamiento
```
Usuario → Guardian (clasifica) → RAG Agent (busca en FAQs) → FAQ Agent (genera respuesta) → WhatsApp
```

## Próximos Pasos Recomendados

1. **Recargar Vector Store**: Ejecutar `python scripts/load_documents.py` para indexar las FAQs
2. **Pruebas**: Probar con las preguntas de ejemplo del README
3. **Limpieza Opcional**: Eliminar archivos obsoletos de stock si se desea
4. **Monitoreo**: Verificar logs para asegurar que las respuestas mantienen el tono correcto

## Configuración Requerida

No se requieren cambios en configuración. El sistema sigue usando:
- Meta WhatsApp Cloud API (sin cambios)
- OpenAI para procesamiento (sin cambios)
- FAISS para vector store (ahora con FAQs)
- PostgreSQL para conversaciones (sin cambios)

## Notas Técnicas

- La migración es completamente funcional
- No se eliminó código legacy para permitir rollback si es necesario
- El vector store debe ser recargado con `load_documents.py`
- Todas las dependencias existentes siguen siendo válidas
- No se requieren nuevas dependencias

## Testing

Para probar el sistema, envía mensajes como:
- "de donde son ustedes?"
- "quiero info del tiqui tiqui"
- "cuanto cuesta cubrir 20 metros cuadrados?"
- "se lo comen los conejos?"

El sistema debe responder con las respuestas exactas del archivo FAQs, manteniendo ortografía y tono.
