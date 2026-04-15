# Guía de Configuración - CubreJardin FAQ Bot

## Pasos Rápidos de Instalación

### 1. Instalar Dependencias

```bash
cd /Users/consultor/cgl/cubrejardin-bot

# Crear entorno virtual (recomendado)
python3 -m venv venv
source venv/bin/activate  # En macOS/Linux

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar Variables de Entorno

Copia el archivo `.env.example` a `.env` y configura tus credenciales:

```bash
cp .env.example .env
```

Edita `.env` con tus valores reales:

```env
# OpenAI
OPENAI_API_KEY=tu-api-key-aqui

# Meta WhatsApp Cloud API
WHATSAPP_PHONE_NUMBER_ID=tu-phone-number-id
FACEBOOK_PAGE_ACCESS_TOKEN=tu-page-access-token
FACEBOOK_APP_SECRET=tu-app-secret
FACEBOOK_TARGET_APP_ID=tu-app-id
WHATSAPP_WEBHOOK_VERIFY_TOKEN=tu-verify-token

# Base URL para webhooks
WEBHOOK_BASE_URL=https://tu-dominio.com

# Plantillas
DEFAULT_TEMPLATE_NAME=session_expired
TEMPLATE_MAPPING={"handoff":"handoff_notification"}

# Base de datos (opcional para desarrollo)
DATABASE_URL=sqlite:///./test.db
```

### 3. Ejecutar migraciones y cargar FAQs en pgvector

**IMPORTANTE**: Este paso es crucial para que el bot funcione correctamente.

```bash
# Asegúrate de estar en el entorno virtual
source venv/bin/activate

# Ejecuta primero las migraciones SQL en tu Postgres/Supabase
# sql/migrations/001_enable_pgvector.sql
# sql/migrations/002_documents_and_match_documents.sql

# Cargar documentos (FAQs) al tenant en pgvector
python scripts/load_documents.py --tenant-id <tenant_uuid>
```

Este comando:
- Lee todos los archivos `.md` en `data/documents/`
- Incluye el nuevo archivo `faqs.md` con todas las preguntas frecuentes
- Genera embeddings usando OpenAI
- Inserta los chunks directamente en `documents` (`tenant_id`, `metadata`, `embedding`)

### 4. Iniciar el Servidor

```bash
# Desarrollo
uvicorn main:app --reload --port 8000

# Producción (con Docker)
docker-compose up -d
```

### 5. Configurar Webhook en Meta

1. Ve a tu app de Meta (https://developers.facebook.com)
2. Configura el webhook con:
   - URL: `https://tu-dominio.com/webhooks/whatsapp`
   - Token de verificación: el mismo que pusiste en `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
3. Suscríbete a los eventos: `messages`

## Estructura de Archivos Importantes

```
cubrejardin-bot/
├── data/
│   ├── documents/
│   │   ├── faqs.md                    # ← NUEVO: Preguntas frecuentes
│   │   ├── catalogo_productos.md
│   │   └── ...
│   └── documents/                     # ← Fuente Markdown para ingesta
├── sql/
│   └── migrations/                    # ← Migraciones pgvector/documents
├── agents/
│   ├── faq_agent.py                   # ← NUEVO: Maneja FAQs
│   ├── guardian_agent.py              # Clasifica mensajes
│   ├── rag_agent.py                   # Busca en pgvector vía RPC
│   └── orchestrator.py                # Coordina agentes
├── config/
│   └── prompts.py                     # Prompts actualizados para FAQs
└── main.py                            # Punto de entrada FastAPI
```

## Verificación

### Test Local

Puedes probar el bot localmente:

```bash
# Ejecutar tests
pytest tests/test_faq_agent.py -v

# Probar conversación interactiva (si existe)
python scripts/test_conversation.py
```

### Test con WhatsApp

Envía un mensaje al número de WhatsApp configurado:

1. "hola" → Debe responder con saludo
2. "de donde son ustedes?" → Debe responder con info de ubicación
3. "quiero info del tiqui tiqui" → Debe enviar info completa con emojis y precio
4. "cuanto cuesta cubrir 20 metros cuadrados?" → Debe calcular 200 plantas

## Solución de Problemas

### Error: "No module named 'openai'"

```bash
# Activa el entorno virtual
source venv/bin/activate

# Instala dependencias
pip install -r requirements.txt
```

### El bot no responde correctamente a FAQs

```bash
# Reingesta documentos del tenant
python scripts/load_documents.py --tenant-id <tenant_uuid>
```

### Error en webhooks

1. Verifica que `WEBHOOK_BASE_URL` sea accesible públicamente (usa ngrok para desarrollo)
2. Verifica que el token de verificación coincida
3. Revisa los logs: `docker-compose logs -f api`

### El bot responde pero no mantiene el tono original

- Verifica que el archivo `data/documents/faqs.md` tenga los textos exactos
- Verifica que `config/prompts.py` tenga las instrucciones de preservar ortografía
- Reingesta el tenant: `python scripts/load_documents.py --tenant-id <tenant_uuid>`

## Desarrollo

### Añadir Nuevas FAQs

1. Edita `data/documents/faqs.md`
2. Añade la nueva pregunta y respuesta
3. Reingesta el tenant: `python scripts/load_documents.py --tenant-id <tenant_uuid>`
4. Prueba con un mensaje de WhatsApp

### Modificar Categorías de FAQs

Edita `agents/faq_agent.py` en el método `identify_faq_intent()`:

```python
# Añade nuevas categorías en el prompt
system_prompt = """
...
17. NUEVA_CATEGORIA - descripción de cuándo usar esta categoría
...
"""
```

## Monitoreo

### Logs Importantes

```bash
# Ver logs en tiempo real
docker-compose logs -f api

# Buscar eventos específicos
docker-compose logs api | grep "faq_intent_identified"
docker-compose logs api | grep "faq_response_generated"
```

### Eventos Clave

- `guardian_classification` - Cómo se clasificó el mensaje
- `faq_intent_identified` - Qué categoría de FAQ se identificó
- `faq_response_generated` - Respuesta generada
- `rag_answer` - Resultado de búsqueda en pgvector

## Siguientes Pasos

1. ✅ Sistema básico de FAQs funcionando
2. 🔜 Añadir más preguntas frecuentes al archivo `faqs.md`
3. 🔜 Ajustar respuestas basado en feedback de usuarios
4. 🔜 Implementar métricas y analytics
5. 🔜 A/B testing de respuestas

## Soporte

Para problemas o preguntas sobre la implementación, revisa:

- `FAQ_MIGRATION_SUMMARY.md` - Resumen de cambios realizados
- `README.md` - Documentación general del proyecto
- Logs del sistema - `docker-compose logs -f api`
