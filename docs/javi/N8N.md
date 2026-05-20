# n8n — Automatización de Workflows de Fraude

> Parte del TFG: Sistema de Detección de Fraude Bancario  
> Responsable: Javi | Rama: `feature/hadoop`

---

## Descripción

**n8n** es el motor de automatización de workflows del proyecto. Su rol principal es:

1. **Cron diario** → leer predicciones de HDFS (`/data/fraud-results/`)
2. **Generar informe** con estadísticas de fraude del día
3. **Enviar alerta por email** al administrador si hay fraudes detectados
4. **Triggerar análisis PySpark** vía webhook cuando llegan nuevos datos

---

## Arrancar n8n

```bash
# Prerrequisito: Hadoop y ai-service deben estar corriendo
docker compose -f infrastructure/n8n/docker-compose.yml up -d
```

Interfaz web: **http://localhost:5678**

---

## Variables de entorno (en `.env`)

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu-email@gmail.com
SMTP_PASS=tu-app-password
SMTP_SENDER=fraude@tfg.local
```

> Para Gmail: usar **App Password** (no la contraseña normal). Activar 2FA y generar en  
> Cuenta Google → Seguridad → Contraseñas de aplicaciones.

---

## URLs internas (en shared-ml-network)

| Servicio | URL interna desde n8n |
|---|---|
| FastAPI predict | `http://ai-service:8000/predict` |
| HDFS WebHDFS | `http://hadoop:9870/webhdfs/v1` |
| Neo4j Bolt | `bolt://neo4j:7687` |

---

## Workflows planificados

### Workflow 1: Informe diario de fraude

```
[Cron: 08:00 diario]
    → [HTTP Request] GET http://hadoop:9870/webhdfs/v1/data/fraud-results/?op=LISTSTATUS
    → [Function] Procesar JSON, calcular estadísticas (total, fraudes, porcentaje)
    → [IF] ¿Hay fraudes detectados (>0)?
        Sí → [Email] Enviar alerta con resumen
        No → [No-op] Log "Sin fraudes detectados"
```

### Workflow 2: Predicción en tiempo real (webhook)

```
[Webhook: POST /webhook/predict]
    → [HTTP Request] POST http://ai-service:8000/predict (body: datos transacción)
    → [IF] fraud_probability >= 0.15
        Sí → [Email] Alerta inmediata + [HTTP] Guardar en Neo4j
        No → [Respond] {"status": "ok", "fraud": false}
```

---

## Volumen de persistencia

`n8n_data` → `/home/node/.n8n`

Contiene workflows, credenciales cifradas y configuración.  
**Hacer backup antes de borrar:** `docker cp n8n:/home/node/.n8n ./backup-n8n/`

---

## Parar n8n

```bash
docker compose -f infrastructure/n8n/docker-compose.yml down
# Con borrado de datos (⚠️):
docker compose -f infrastructure/n8n/docker-compose.yml down -v
```
