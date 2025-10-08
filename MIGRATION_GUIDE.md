# Migración de Twilio a Meta WhatsApp Cloud API

Este documento describe los pasos necesarios para sustituir el flujo existente basado en Twilio por la integración nativa con **Meta WhatsApp Cloud API v21.0** incluida en este repositorio.

## 1. Requisitos previos

- Tener una cuenta de Facebook Business verificada.
- Registrar una app en [Meta for Developers](https://developers.facebook.com/) con el producto **WhatsApp** habilitado.
- Disponer de un **Phone Number ID**, un **Permanent Access Token** y el **App Secret** de la app.
- Exponer públicamente el backend (ngrok, Cloud Run, Render, etc.) para completar la verificación del webhook.

## 2. Variables de entorno

Actualiza tu `.env` (o variables en tu plataforma de despliegue) con las nuevas claves:

```bash
WHATSAPP_PHONE_NUMBER_ID=123456789012345
FACEBOOK_PAGE_ACCESS_TOKEN=EAAGxxxx
FACEBOOK_APP_SECRET=abc123...
FACEBOOK_TARGET_APP_ID=263902037430900  # Page Inbox por defecto
WHATSAPP_WEBHOOK_VERIFY_TOKEN=token_unico_webhook
```

> ℹ️ Las variables `WHATSAPP_ACCOUNT_SID`, `WHATSAPP_AUTH_TOKEN` y `WHATSAPP_FROM_NUMBER` de Twilio ya no se utilizan. Puedes eliminarlas o dejarlas comentadas como referencia histórica.

## 3. Configurar el webhook en Meta

1. En la app de Meta, ve a **WhatsApp → Configuration → Webhook**.
2. Establece la URL pública hacia `https://tu-dominio/webhook/whatsapp`.
3. Usa el mismo `WHATSAPP_WEBHOOK_VERIFY_TOKEN` configurado en el `.env`.
4. Suscribe los eventos `messages` y `message_status`.

El endpoint `GET /webhook/whatsapp` devolverá el `hub.challenge` si el token coincide.

## 4. Flujo de mensajes

- `POST /webhook/whatsapp` recibe los eventos directamente de Meta.
- El servicio valida la firma `X-Hub-Signature-256` usando `FACEBOOK_APP_SECRET`.
- Los mensajes se marcan como leídos (`mark_as_read`) antes de ser procesados por el orquestador.
- Las respuestas se envían con `send_text_message`; si estás fuera de la ventana de 24 horas, envía plantillas con `send_template_message`.

## 5. Escalaciones y handover

El `HandoffAgent` notifica primero al usuario y luego delega el control:

1. `send_text_message` → informa al usuario.
2. `pass_thread_control` → cede control a la bandeja humana (Page Inbox).
3. Cuando el humano termina, el backend puede invocar `take_thread_control` para devolver el hilo al bot.

## 6. Validación y pruebas

1. Ejecuta `pytest` para verificar la integración básica y los tests del servicio Meta.
2. Usa `scripts/test_conversation.py` para iniciar un diálogo local; el stub imprime los mensajes en consola.
3. Desde Postman o curl, envía payloads de ejemplo al webhook para asegurarte de que el orquestador responde (<https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples>).
4. Envía mensajes reales desde tu dispositivo utilizando el número de prueba de Meta; recuerda que la ventana de 24 h se reinicia cada vez que recibes un mensaje del usuario.

## 7. Diferencias clave respecto a Twilio

- **Autenticación:** ya no se usan SID/AUTH_TOKEN, ahora todo pasa por `Bearer <PAGE_ACCESS_TOKEN>`.
- **Firmas de webhook:** Twilio usaba HMAC-SHA1, Meta usa `X-Hub-Signature-256`.
- **Formato de número:** Meta requiere números en formato internacional sin el prefijo `whatsapp:` ni el símbolo `+`.
- **24h Window & Templates:** fuera de ventana sólo se permiten plantillas aprobadas.
- **Handover Protocol:** ahora es nativo de Meta (Page Inbox) en vez de combinar Twilio + API de Meta.

## 8. Checklist final

- [ ] Webhook verificado desde la consola de Meta.
- [ ] Variables de entorno actualizadas en todos los entornos (local, staging, prod).
- [ ] Pruebas unitarias y de integración (`pytest`) en verde.
- [ ] Logs en `webhook` confirmando `mark_as_read`, `process_message` y `send_text_message`.
- [ ] Escalaciones registradas y handover funcionando (mensaje al usuario + `pass_thread_control`).

Una vez completados estos pasos tu bot funcionará íntegramente sobre la API oficial de Meta sin depender de Twilio.
