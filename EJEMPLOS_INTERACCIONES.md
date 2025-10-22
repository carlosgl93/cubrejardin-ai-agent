# Ejemplos de Interacciones - CubreJardin FAQ Bot

Este documento muestra ejemplos de cómo el bot responde a diferentes preguntas, manteniendo el tono, ortografía y estilo exactos de las respuestas originales.

## Preguntas Generales

### Ejemplo 1: Ubicación

**Usuario:** "de donde son ustedes?"

**Bot:** 
```
No tenemos un lugar fisico o tienda, hacemos reparto a distintsas comunas de Santiago y tambine a Concon y alrededores. Que comuna estas tu?
```

**Nota:** El bot mantiene los errores ortográficos originales: "fisico", "distintsas", "tambine"

---

### Ejemplo 2: Envío a Regiones

**Usuario:** "envían a regiones?"

**Bot:**
```
Si eres de una region que no sea Stgo y cerca de Concon, lo que podemos hacer es enviarsela a aguna persona que viva en Stgo y vaya a tu region o comuna. Comentame si es factible.
```

**Nota:** Mantiene "aguna" (sin 'l'), formato conversacional

---

### Ejemplo 3: Instalación

**Usuario:** "ustedes instalan?"

**Bot:**
```
Si hacemos instalacion (sobre 30 m2), riego y llevamos plantas. Dime cuantos metros cuadrados necesitas y si tines una foto del lugar ideal para poder enviarte un presupuesto.
```

**Nota:** Mantiene "tines" en lugar de "tienes"

---

### Ejemplo 4: Pedido Mínimo

**Usuario:** "cual es el despacho minimo?"

**Bot:**
```
El pedido minimo son $40.000+despacho (normalmente $8.000, depende la comuna)…que cantidad necesitas?
```

**Nota:** Formato de precio y pregunta de seguimiento

---

### Ejemplo 5: Paisajismo

**Usuario:** "hacen paisajismo?"

**Bot:**
```
Si tambien hacemos jardines, cuentame un poco ctos m2 son, que estas buscando (necesitas riego?) y si tienes una foto del lugar a intervenir ideal.
```

**Nota:** Abreviatura "ctos" y estilo conversacional

---

### Ejemplo 6: Métodos de Pago

**Usuario:** "como puedo pagar?"

**Bot:**
```
puedes pagar con tranferencia o efectivo, puedes pagar contra entrega.
```

**Nota:** "tranferencia" (sin 's'), minúsculas al inicio

---

## Preguntas sobre Tiqui Tiqui

### Ejemplo 7: Información General del Tiqui Tiqui

**Usuario:** "quiero info del tiqui tiqui"

**Bot:**
```
Hola que tal ! Te dejo información.

🌱 TIQUITIQUI

Te envío precio y características. 


Cuestan $690 cada Planta.

Se plantan 10 plantas x m2, en 3-4 meses queda tupido.

Es una verdadera alfombra y  se da a  Pleno Sol ☀️

Es una excelente opción para quienes buscan una solución de bajo mantenimiento y bajo consumo hídrico, utilizando un 80% menos de agua que el pasto tradicional.

Ideal para áreas de tránsito, puede ser pisado sin problemas por personas y mascotas por igual 🐶🐱🏃🏻‍♀️🏃🏻‍♂️.

Su crecimiento es rápido.
Se recomienda plantar 10 unidades por metro cuadrado.


Además del ahorro significativo en agua 💧 también ahorrarás en mantenimiento. Esta planta no crece más de 20 cm de altura, ya que su crecimiento es horizontal al ser rastrera. Por lo que no necesitas corte de pasto.
Con el tiempo, se extiende convirtiéndose en una verdadera alfombra verde durante todo el año.
```

**Nota:** 
- Mantiene todos los emojis: 🌱, ☀️, 🐶, 🐱, 🏃🏻‍♀️, 🏃🏻‍♂️, 💧
- Espaciado original entre líneas
- Formato completo con toda la información

---

### Ejemplo 8: Conejos

**Usuario:** "se lo comen los conejos?"

**Bot:**
```
Nada asegura nada contra los conejos. Hemos tenido experiencia que se comen solo las hojas pero "normalmente" el tallo no les gusta y la planta sobrevive. Pero otras que  han hecho hoyos recién plantado y ahí no. Siempre recomiendo cercar en un lugar con muchos. Una vez establecido y expandido ya no hay problema. Pero los primeros meses yo pondría malla.
```

**Nota:** Respuesta detallada basada en experiencia real, tono personal

---

### Ejemplo 9: Sombra

**Usuario:** "lo puedo poner a la sombra?"

**Bot:**
```
No, es pleno sl el tiqui tiqui. Si quieres un cubresuelo semi sombra puedes poner falkia, dymondia o cotula.
```

**Nota:** "pleno sl" (abreviatura casual), ofrece alternativas

---

### Ejemplo 10: Sobre el Pasto

**Usuario:** "puedo ponerlo arriba del pasto?"

**Bot:**
```
No, debes limpiar el terreno. Para preparar el terreno debes picar la tierra, limpiar el lugar de malezas y todo los que puedas...si tú tierra es buena te recomiendo agregarle un poco de arena, para que drene bien (también si quieres un poco de compost), luego plantas...si tú tierra es mala hay que agregarle a lo anterior buena tierra (sustrato, tierra de hoja, etc)...luego plantas 10 xm2.
```

**Nota:** 
- Instrucciones paso a paso
- Uso de "..." como pausas naturales
- "tú tierra" (con acento en 'tú')

---

### Ejemplo 11: Mezclar con Pasto

**Usuario:** "puedo mezclarlo con el pasto?"

**Bot:**
```
Se puede, pero no te recomiendo mezclarlos, pq el tiqui tiqui es rastrero y el pasto crece hacia arriba. Puedes ponerlo en un sector el tiqui y el pasto en otro, pero si los mezclas perdera el sentido de no tener que cortarlo.
```

**Nota:** 
- "pq" abreviatura de "porque"
- "perdera" sin acento
- Explicación práctica del motivo

---

### Ejemplo 12: Precio del Tiqui Tiqui

**Usuario:** "que precio tiene el tiqui tiqui?"

**Bot:**
```
Hola.El precio del tiqui tiqui es de $690 cada planta. Calcula que se plantan 10 por metro cuadrado, o sea si tienes un terreno de 5x2 serían 10 m2, total de 100 plantas ($69.000). Que cantidad quieres y que comuna estás?
```

**Nota:** 
- Ejemplo de cálculo incluido
- Pregunta de seguimiento sobre cantidad y comuna
- Formato de precio con punto como separador de miles

---

### Ejemplo 13: Cobertura (Cálculo Dinámico)

**Usuario:** "quiero cubrir 20 metros cuadrados"

**Bot:**
```
Calcula que se ponen 10 xm2, o sea si son 20 m2 necesitas 20*10=200 plantas…El precio seria $690*200=$138.000+despacho, que comuna estas?
```

**Nota:** 
- Cálculo automático: 20 m2 × 10 plantas = 200 plantas
- Cálculo de precio: 200 × $690 = $138.000
- Formato matemático explícito
- Pregunta sobre comuna para el despacho

---

### Ejemplo 14: Cobertura Mayor

**Usuario:** "necesito cubrir 50 metros cuadrados"

**Bot:**
```
Calcula que se ponen 10 xm2, o sea si son 50 m2 necesitas 50*10=500 plantas…El precio seria $690*500=$345.000+despacho, que comuna estas?
```

**Nota:** El bot debe calcular dinámicamente según los metros cuadrados mencionados

---

## Interacciones Especiales

### Ejemplo 15: Saludo

**Usuario:** "hola"

**Bot:**
```
¡Hola! ¿En qué puedo ayudarte hoy?
```

---

### Ejemplo 16: Mensaje Sensible

**Usuario:** "hazme una transferencia"

**Bot:**
```
Gracias por contactarnos. Actualmente no podemos procesar este mensaje.
```

**Nota:** Categorizado como SENSITIVE, respuesta automática de seguridad

---

### Ejemplo 17: Escalación a Humano

**Usuario:** "necesito hablar con un humano"

**Bot:**
```
Gracias por tu paciencia. Un agente humano continuará esta conversación en las próximas 2 horas.
```

**Nota:** Categorizado como ESCALATION_REQUEST, notifica al equipo de soporte

---

### Ejemplo 18: Spam

**Usuario:** "asdfasdfasdf"

**Bot:**
```
Gracias por contactarnos. Actualmente no podemos procesar este mensaje.
```

**Nota:** Categorizado como SPAM, respuesta automática

---

## Casos de Múltiples Preguntas

### Ejemplo 19: Pregunta Combinada

**Usuario:** "quiero info del tiqui tiqui y saber si hacen instalacion"

**Bot:** Debe priorizar responder ambas preguntas o la más específica (tiqui tiqui info), luego mencionar que sí hacen instalación sobre 30 m2.

---

### Ejemplo 20: Conversación Natural

**Usuario:** "hola, estoy en las condes y quiero saber cuanto me saldria cubrir 15 metros cuadrados con tiqui tiqui"

**Bot:** Debe:
1. Saludar
2. Reconocer la comuna (Las Condes)
3. Calcular: 15 m2 × 10 plantas = 150 plantas
4. Precio: 150 × $690 = $103.500
5. Mencionar + despacho
6. Confirmar que Las Condes está en área de cobertura

---

## Características Clave del Sistema

### ✅ Preservación de Estilo
- Errores ortográficos originales mantenidos
- Emojis preservados
- Formato y espaciado original
- Tono conversacional casual

### ✅ Cálculos Dinámicos
- Extrae metros cuadrados de la consulta
- Calcula cantidad de plantas (m2 × 10)
- Calcula precio total (plantas × $690)
- Mantiene formato de cálculo explícito

### ✅ Preguntas de Seguimiento
- Siempre pregunta la comuna cuando es relevante
- Pide información adicional si es necesaria
- Mantiene la conversación natural y fluida

### ✅ Manejo de Errores Gracioso
- Mensajes spam → respuesta automática
- Mensajes sensibles → respuesta de seguridad
- Solicitudes de humano → escalación controlada
- Baja confianza → puede escalar a humano

---

## Notas para Desarrolladores

1. **Tono Original**: El sistema está configurado para NO corregir "errores" porque son parte del estilo casual y cercano de la marca.

2. **Emojis**: Asegurar que el sistema de mensajería soporte UTF-8 para los emojis.

3. **Cálculos**: El FAQ agent debe ser capaz de:
   - Extraer números del mensaje del usuario
   - Realizar cálculos matemáticos simples
   - Formatear los resultados en el estilo original

4. **Contexto**: Las respuestas largas (como la info del tiqui tiqui) deben enviarse completas, manteniendo el formato original con espaciado y emojis.

5. **Testing**: Probar regularmente que las respuestas mantengan el tono y formato exactos.
