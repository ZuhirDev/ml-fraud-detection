# n8n — Automatización de Workflows de Fraude

> TFG: Sistema de Detección de Fraude Bancario  
> Tecnologías: n8n 2.20.11 · Groq API · Neo4j HTTP · Gmail SMTP

---

## 1. ¿Qué es n8n y por qué lo usamos?

**n8n** (pronunciado "n-eight-n") es una plataforma de automatización de workflows de código abierto, auto-hospedable. Permite conectar servicios y APIs mediante un editor visual de nodos, sin necesidad de escribir código para la mayoría de integraciones.

En este proyecto, n8n actúa como el **orquestador de informes**: recopila estadísticas de Neo4j, las enriquece con análisis de IA generativa y entrega el resultado por email de forma automática.

### ¿Por qué n8n en lugar de un script Python?

| Criterio | Script Python | n8n |
|---|---|---|
| Programación (cron) | crontab del sistema | Scheduler visual integrado |
| Editor visual del flujo | No | Sí, drag & drop |
| Manejo de errores | Manual | Reintentos, alertas automáticas |
| Integraciones | Manual (requests, smtplib) | +400 nodos nativos |
| Auto-hospedable | Script | Contenedor Docker, datos cifrados |
| Debugging | Logs de terminal | Inspector de ejecución por nodo |

n8n facilita la modificación del flujo (añadir pasos, cambiar el destinatario del email, probar con datos distintos) sin reescribir código.

---

## 2. Arquitectura del workflow

```
[Schedule]     [Manual Trigger]
      │               │
      └───────┬───────┘
              ▼
    [HTTP Request → Neo4j]      ← POST /db/neo4j/tx/commit
         Consulta Cypher
              │
              ▼
         [Code: Stats]           ← Parsea resultados de Neo4j
         Calcula estadísticas
              │
              ▼
    [HTTP Request → Groq]        ← POST api.groq.com/openai/v1/...
         Llama-3.1-8b-instant
              │
              ▼
        [Code: HTML]             ← Construye el email HTML
              │
              ▼
        [Send Email]             ← Gmail SMTP port 465 SSL/TLS
```

---

## 3. Descripción

**n8n** es el motor de automatización del proyecto. Workflow implementado:

- Se dispara **diariamente a las 08:00** o **manualmente** (para demos en clase)
- Consulta Neo4j para obtener estadísticas reales de fraude
- Envía los datos a **Groq** (llama-3.1-8b-instant, gratuito) para generar análisis narrativo en español
- Manda un **email HTML profesional** con el informe completo

El JSON del workflow está en: `workflows/n8n-ml.json`

---

## 4. Arrancar n8n

```bash
# Prerrequisito: shared-ml-network debe existir y neo4j estar corriendo
docker compose -f infrastructure/n8n/docker-compose.yml up -d
```

Interfaz web: **http://localhost:5678**

> **Credenciales en n8n moderno:** NO están en Settings. Se crean directamente dentro de cada nodo en el campo "Credential". External Secrets y Environments son features de pago.

---

## Requisitos previos

### Gmail — App Password (para envío de email)
1. Cuenta Google → **Seguridad** → **Verificación en 2 pasos** → activar
2. Volver a **Seguridad** → **Contraseñas de aplicaciones** → genera una para "n8n"
3. Guarda el código de 16 caracteres (sin espacios)

### Groq API Key (para el análisis con IA — gratuito)
1. https://console.groq.com → **API Keys** → **Create API Key**
2. La clave empieza por `gsk_...`
3. Modelo usado: `llama-3.1-8b-instant` — rápido y gratuito

---

## URLs internas (solo funcionan dentro de Docker)

| Servicio | URL desde n8n |
|---|---|
| Neo4j HTTP API | `http://neo4j:7474/db/neo4j/tx/commit` |
| FastAPI predict | `http://ai-service:8000/predict` |

Desde el navegador usa `localhost` en lugar del nombre del servicio.

---

## Workflow: Informe de Fraude con IA

### Flujo completo

```
[Schedule Trigger: 08:00 diario]  ─┐
                                    ├─→ [HTTP Request] Neo4j stats
[Manual Trigger: botón en clase]  ─┘
                                        → [Code] Formatear datos  ("Stats")
                                        → [HTTP Request] Groq — generar análisis
                                        → [Code] Construir HTML del email
                                        → [Send Email] Informe completo
```

---

### Nodo 1A — Schedule Trigger

Click en **"Add first step..."** → busca **Schedule Trigger**

| Campo | Valor |
|---|---|
| Trigger interval | Custom (Cron) |
| Cron expression | `0 8 * * *` |

---

### Nodo 1B — Manual Trigger (para demo en clase)

`+` en un área vacía del canvas → **"When Executed Manually"**.  
Conéctalo al mismo nodo 2 que el Schedule Trigger.

> En clase: pulsa **"Test workflow"** en la barra superior para ejecutarlo al momento.

---

### Nodo 2 — HTTP Request → Neo4j

| Campo | Valor |
|---|---|
| Method | `POST` |
| URL | `http://neo4j:7474/db/neo4j/tx/commit` |
| Authentication | Generic Credential Type → Header Auth |

Credencial **Neo4j Basic Auth**:
- Header Name: `Authorization`
- Header Value: `Basic bmVvNGo6cGFzc3dvcmQ=`  
  *(base64 de `neo4j:password` — si cambias la contraseña: `btoa('neo4j:nuevapass')`)*

Header adicional: `Content-Type` → `application/json`

**Body → JSON:**
```json
{
  "statements": [
    {
      "statement": "MATCH ()-[t:TRANSACTION]->() RETURN count(t) AS total, sum(CASE WHEN t.isFraud = 1 THEN 1 ELSE 0 END) AS fraudes, round(sum(CASE WHEN t.isFraud = 1 THEN t.amount ELSE 0.0 END)) AS importe_fraude, max(t.step) AS ultimo_step"
    },
    {
      "statement": "MATCH ()-[t:TRANSACTION]->() WHERE t.isFraud = 1 RETURN t.type AS tipo, count(t) AS cantidad ORDER BY cantidad DESC LIMIT 3"
    }
  ]
}
```

---

### Nodo 3 — Code → Formatear estadísticas

Renombrar el nodo a **"Stats"** (doble click sobre el nombre en el canvas).

```js
const results = $input.first().json.results;

const row0 = results[0].data[0]?.row ?? [0, 0, 0, 0];
const total       = row0[0];
const fraudes     = row0[1];
const importe     = row0[2];
const ultimo_step = row0[3];
const porcentaje  = total > 0 ? ((fraudes / total) * 100).toFixed(3) : '0';

const tipos = (results[1].data ?? []).map(d => ({
  tipo: d.row[0],
  cantidad: d.row[1]
}));
const tipos_str = tipos.map(t => `${t.tipo}: ${t.cantidad}`).join(', ') || 'Sin datos';

const fecha = new Date().toLocaleDateString('es-ES', {
  weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
});

return [{ json: { total, fraudes, importe, porcentaje, ultimo_step, tipos_str, tipos, fecha } }];
```

---

### Nodo 4 — HTTP Request → Groq (análisis con IA)

| Campo | Valor |
|---|---|
| Method | `POST` |
| URL | `https://api.groq.com/openai/v1/chat/completions` |
| Authentication | Generic Credential Type → Header Auth |

Credencial **Groq API Key**:
- Header Name: `Authorization`
- Header Value: `Bearer gsk_XXXXXXXXXXXXXXXXXX` ← tu clave de Groq

Header adicional: `Content-Type` → `application/json`

**Body → JSON:**
```json
{
  "model": "llama-3.1-8b-instant",
  "max_tokens": 400,
  "messages": [
    {
      "role": "system",
      "content": "Eres un analista experto en ciberseguridad financiera. Redactas informes ejecutivos concisos, profesionales y en español. Usas datos reales del sistema para dar contexto y recomendaciones."
    },
    {
      "role": "user",
      "content": "Genera un informe ejecutivo breve (2-3 párrafos) para el sistema de detección de fraude bancario.\n\nDatos del sistema a {{ $json.fecha }}:\n- Transacciones analizadas en total: {{ $json.total }}\n- Fraudes detectados: {{ $json.fraudes }} ({{ $json.porcentaje }}% del total)\n- Importe total fraudulento interceptado: ${{ $json.importe }}\n- Último paso temporal procesado: {{ $json.ultimo_step }}\n- Fraude por tipo de operación: {{ $json.tipos_str }}\n\nIncluye: situación actual, patrones detectados y una recomendación operativa."
    }
  ]
}
```

---

### Nodo 5 — Code → Construir email HTML

```js
const analisis = $input.first().json.choices[0].message.content;
const {
  total, fraudes, porcentaje, importe, fecha, tipos, ultimo_step
} = $('Stats').first().json;

const tipos_html = tipos.map(t =>
  `<tr><td style="padding:8px 16px;">${t.tipo}</td><td style="padding:8px 16px;font-weight:bold;">${t.cantidad}</td></tr>`
).join('');

const html = `
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 20px; }
  .card { background: white; border-radius: 8px; padding: 24px; margin-bottom: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
  .header { background: #1a1a2e; color: white; border-radius: 8px; padding: 24px; margin-bottom: 16px; }
  .metric { display: inline-block; text-align: center; margin: 0 16px; }
  .metric .value { font-size: 2em; font-weight: bold; color: #e63946; }
  .metric .label { font-size: 0.85em; color: #666; margin-top: 4px; }
  .metric.safe .value { color: #2a9d8f; }
  table { width: 100%; border-collapse: collapse; }
  th { background: #1a1a2e; color: white; padding: 10px 16px; text-align: left; }
  tr:nth-child(even) { background: #f8f8f8; }
  .ai-box { background: #f0f4ff; border-left: 4px solid #4361ee; padding: 16px 20px; border-radius: 0 8px 8px 0; }
  .footer { text-align: center; color: #aaa; font-size: 0.8em; margin-top: 24px; }
</style>
</head>
<body>
  <div class="header">
    <h1 style="margin:0">🛡️ Sistema de Detección de Fraude Bancario</h1>
    <p style="margin:8px 0 0;opacity:0.8">Informe generado: ${fecha} · Paso temporal: ${ultimo_step}</p>
  </div>
  <div class="card" style="text-align:center">
    <div class="metric">
      <div class="value safe">${Number(total).toLocaleString('es-ES')}</div>
      <div class="label">Transacciones analizadas</div>
    </div>
    <div class="metric">
      <div class="value">${Number(fraudes).toLocaleString('es-ES')}</div>
      <div class="label">Fraudes detectados</div>
    </div>
    <div class="metric">
      <div class="value">${porcentaje}%</div>
      <div class="label">Tasa de fraude</div>
    </div>
    <div class="metric">
      <div class="value">$${Number(importe).toLocaleString('es-ES')}</div>
      <div class="label">Importe interceptado</div>
    </div>
  </div>
  <div class="card">
    <h2 style="margin-top:0">📊 Fraude por tipo de operación</h2>
    <table>
      <tr><th>Tipo</th><th>Casos</th></tr>
      ${tipos_html || '<tr><td colspan="2" style="padding:8px 16px;color:#999">Sin datos disponibles</td></tr>'}
    </table>
  </div>
  <div class="card">
    <h2 style="margin-top:0">🤖 Análisis generado por IA (Groq · llama-3.1-8b-instant)</h2>
    <div class="ai-box">${analisis.replace(/\n/g, '<br>')}</div>
  </div>
  <div class="footer">Generado automáticamente por el sistema de fraude · TFG 2025-2026</div>
</body>
</html>`;

return [{ json: { html, subject: `Informe de Fraude — ${fecha} · ${fraudes} fraudes detectados` } }];
```

---

### Nodo 6 — Send Email

Credencial **SMTP Gmail**:

| Campo | Valor |
|---|---|
| Host | `smtp.gmail.com` |
| Port | `587` |
| SSL/TLS | `SSL/TLS` |
| User | tu Gmail completo |
| Password | App Password de Google (16 caracteres, sin espacios) |

Configuración del email:

| Campo | Valor |
|---|---|
| From | tu Gmail |
| To | tu Gmail (o el del profesor) |
| Subject | `{{ $json.subject }}` |
| Email Format | HTML |
| HTML | `{{ $json.html }}` |

---

## Publicar y probar

1. **Guardar**: `Ctrl+S`
2. **Demo en clase**: botón **"Test workflow"** en la barra superior → ejecuta al momento
3. **Producción**: toggle **"Inactive"** → **"Active"** — corre solo a las 08:00

---

## Desplegar en AWS

El JSON del workflow está en `workflows/n8n-ml.json`. Para importarlo en la instancia EC2:

1. `http://[EC2_IP]:5678` → menú superior → **Import from file** → sube el JSON
2. Reconfigura las 3 credenciales (n8n te avisará cuáles faltan):
   - **Neo4j Basic Auth** → igual que en local (`Basic bmVvNGo6cGFzc3dvcmQ=`)
   - **Groq API Key** → misma clave `gsk_...`
   - **SMTP Gmail** → mismos datos de Gmail
3. Las URLs internas (`neo4j`, `ai-service`) funcionan igual — misma red Docker

> La IP del EC2 solo la necesitas para abrir el navegador. No hay nada hardcodeado en el workflow.

---

## Volumen de persistencia

`n8n_data` → `/home/node/.n8n` — workflows, credenciales cifradas y configuración.

```bash
# Backup antes de borrar:
docker cp n8n:/home/node/.n8n ./backup-n8n/
```

---

## Parar n8n

```bash
docker compose -f infrastructure/n8n/docker-compose.yml down
# Con borrado de datos (⚠️):
docker compose -f infrastructure/n8n/docker-compose.yml down -v
```

