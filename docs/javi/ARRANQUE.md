# Stack Completo — Guía de Arranque Rápido

> TFG: Sistema de Detección de Fraude Bancario  
> Zuhir (ML core) + Javi (Big Data / Infra)

---

## Arquitectura de servicios

```
┌──────────────────────────────────────────────────────────────┐
│                      shared-ml-network                       │
│                                                              │
│  ── ZUHIR ─────────────────────────────────────────────────  │
│  ┌──────────────┐    ┌──────────────┐  ┌─────────────┐       │
│  │  ml-env      │──> │  ai-service  │  │   neo4j     │       │
│  │  JupyterLab  │    │  FastAPI     │  │  Graph DB   │       │
│  │  :8888       │    │  :8000       │  │ :7474/:7687 │       │
│  └──────────────┘    └──────────────┘  └─────────────┘       │
│                                                              │
│  ── JAVI ──────────────────────────────────────────────────  │
│  ┌──────────────┐    ┌──────────────┐                        │
│  │  hadoop      │    │  n8n         │                        │
│  │  HDFS + YARN │    │  Workflows   │                        │
│  │  :9870/:9000 │    │  :5678       │                        │
│  │  :8088/:8042 │    │              │                        │
│  └──────────────┘    └──────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

---

## Prerrequisito (solo la primera vez)

```bash
docker network create shared-ml-network
```

---

## Arrancar todo (desde la raíz del proyecto)

```bash
# 1. Stack de Zuhir — ML core
docker compose -f infrastructure/ml-env/docker-compose.yml up -d
docker compose -f infrastructure/api/docker-compose.yml up -d

# 2. Hadoop (Javi) — HDFS + YARN
docker compose -f infrastructure/hadoop/docker-compose.yml up -d

# 3. n8n (Javi) — Automatización de workflows
docker compose -f infrastructure/n8n/docker-compose.yml up -d
```

> Hadoop tarda ~30-60s en inicializar HDFS la primera vez. Los demás arrancan en segundos.

---

## Verificar que todo está bien

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Salida esperada con los 5 servicios:

| NAMES | STATUS | PORTS |
|---|---|---|
| ml-env | Up | 0.0.0.0:8888 |
| neo4j | Up | 0.0.0.0:7474, 7687 |
| ai-service | Up | 0.0.0.0:8000 |
| hadoop | Up (healthy) | 0.0.0.0:9870, 9000, 8088, 8042 |
| n8n | Up | 0.0.0.0:5678 |

```bash
# Test rápido del API de predicción
curl -s http://localhost:8000/health

# Test HDFS
docker exec hadoop hdfs dfs -ls /data/
```

---

## Interfaces Web

| Servicio | URL | Quién | Descripción |
|---|---|---|---|
| JupyterLab | http://localhost:8888 | Zuhir | Notebooks ML |
| FastAPI docs | http://localhost:8000/docs | Zuhir | Swagger /predict |
| Neo4j Browser | http://localhost:7474 | Zuhir | Explorar grafo |
| NameNode UI | http://localhost:9870 | Javi | Estado HDFS |
| YARN UI | http://localhost:8088 | Javi | Jobs Spark |
| n8n | http://localhost:5678 | Javi | Workflows fraude |

**Credenciales Neo4j:** `neo4j` / `password`

---

## Parar todo

```bash
docker compose -f infrastructure/n8n/docker-compose.yml down
docker compose -f infrastructure/hadoop/docker-compose.yml down
docker compose -f infrastructure/api/docker-compose.yml down
docker compose -f infrastructure/ml-env/docker-compose.yml down
```

Para borrar también los datos de HDFS (⚠️ irreversible):
```bash
docker compose -f infrastructure/hadoop/docker-compose.yml down -v
```

---

## Variables de entorno (.env en raíz)

```env
MODEL_NAME=modelo_fraude_rf_final.joblib
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_AUTH=neo4j/password
```

---

## Documentación detallada

- [HADOOP.md](HADOOP.md) — Configuración HDFS, estructura de directorios, troubleshooting
- [N8N.md](N8N.md) — Workflow de informe diario con Groq + Neo4j + email HTML, configuración SMTP, credenciales
- [AWS.md](AWS.md) — Despliegue completo en AWS: instalar Terraform, crear EC2, SSH, gestión de contenedores
- [aws-start.md](aws-start.md) — Guía rápida de arranque: nuevo despliegue vs relanzar instancia existente
