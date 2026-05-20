# Plan Técnico de Despliegue — Big Data + Cloud (Javi)

> Rama: `feature/hadoop` | Fecha de referencia: Mayo 2026  
> Este documento cubre únicamente la parte de infraestructura Big Data, orquestación y despliegue AWS.

---

## 1. Visión de la Arquitectura Global

```
[Frontend bancario]
        │  POST /predict  (JSON transacción)
        ▼
[EC2-1] FastAPI  (puerto 8000)
        │  ─── responde fraud_probability + fraud_prediction
        │  ─── guarda transacción en HDFS (raw zone)
        ▼
[EC2-2] Hadoop Single-Node (HDFS + YARN)  (puertos 9870/9000/8088)
        │  almacena: transacciones raw, informes diarios
        ▼
[EC2-3] n8n  (puerto 5678)
        │  Cron diario 00:00 → lee HDFS → genera informe → envía email admin
        ▼
[EC2-1 también] Neo4j (puertos 7474/7687)
        │  grafo de relaciones origen-destino ya integrado con el modelo
```

**Red privada:** todas las EC2 en la misma VPC, subred privada, se comunican por IP privada.  
**Acceso externo:** solo los puertos necesarios expuestos vía Security Groups.

---

## 2. Resumen de Entregables Propios

| # | Entregable | Estado objetivo |
|---|------------|-----------------|
| 1 | Notebook `hadoop_pyspark_ingesta.ipynb` | Dataset Kaggle → HDFS vía PySpark |
| 2 | `infrastructure/hadoop/docker-compose.yml` | Hadoop single-node dockerizado |
| 3 | `infrastructure/n8n/docker-compose.yml` | n8n con volumen persistente |
| 4 | `infrastructure/n8n/workflow_informe_diario.json` | Workflow exportado de n8n |
| 5 | `docs/javi/AWS_SETUP.md` | Guía paso a paso para EC2 |
| 6 | `.env.example` actualizado | Variables nuevas documentadas |

---

## 3. Notebook: Ingesta Kaggle → Hadoop/PySpark

**Archivo:** `notebooks/hadoop_pyspark_ingesta.ipynb`

### 3.1 Dataset

- **Fuente:** [PaySim — Synthetic Financial Dataset](https://www.kaggle.com/datasets/ealaxi/paysim1) en Kaggle.
- **Fichero:** `PS_20174392719_1491204439457_log.csv` (~470 MB, 6.3M filas).
- **Descarga programática** con `kaggle` CLI (requiere `~/.kaggle/kaggle.json`).

### 3.2 Estructura de celdas del Notebook

```
Celda 1  — Markdown: introducción y objetivo
Celda 2  — Instalar/importar dependencias (kaggle, pyspark, findspark)
Celda 3  — Descargar dataset desde Kaggle API
Celda 4  — Arrancar SparkSession conectada a HDFS
Celda 5  — Leer CSV local y mostrar schema + primeras filas
Celda 6  — EDA básico: conteo, distribución de fraude, estadísticas
Celda 7  — Subir fichero raw a HDFS (zona /data/raw/)
Celda 8  — Limpieza básica con PySpark (tipos, nulls, columnas)
Celda 9  — Guardar datos limpios en HDFS (zona /data/processed/) en Parquet
Celda 10 — Verificación: leer desde HDFS y mostrar conteo final
Celda 11 — Markdown: conclusiones y siguientes pasos
```

### 3.3 Configuración de SparkSession

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("FraudDetection-Ingesta") \
    .master("yarn") \                          # o "local[*]" para pruebas locales
    .config("spark.hadoop.fs.defaultFS", "hdfs://namenode:9000") \
    .config("spark.sql.shuffle.partitions", "8") \
    .getOrCreate()
```

> En local (sin Hadoop arrancado) cambiar `.master("local[*]")` y omitir `fs.defaultFS`.

### 3.4 Zonas HDFS a crear

```
/data/
  raw/         ← CSV original tal cual llega de Kaggle
  processed/   ← Parquet limpio, particionado por type (TRANSFER, CASH_OUT…)
/informes/
  diarios/     ← n8n deposita aquí JSON de resumen cada día
```

Comandos de creación (ejecutables desde el notebook o desde el contenedor):

```bash
hdfs dfs -mkdir -p /data/raw /data/processed /informes/diarios
hdfs dfs -chmod -R 777 /data /informes
```

---

## 4. Docker: Hadoop Single-Node

**Archivo:** `infrastructure/hadoop/docker-compose.yml`

### 4.1 Decisión de arquitectura

Se usa **un único contenedor `apache/hadoop`** (imagen oficial) que levanta NameNode + DataNode + ResourceManager + NodeManager en el mismo proceso. Es suficiente para un TFG y evita la complejidad de un cluster multi-nodo.

### 4.2 Puertos expuestos

| Puerto | Servicio |
|--------|----------|
| `9870` | NameNode Web UI (HDFS) |
| `9000` | HDFS RPC (para clientes Spark/Python) |
| `8088` | ResourceManager (YARN UI) |
| `19888` | JobHistory Server |

### 4.3 Variables de entorno relevantes (añadir a `.env`)

```env
HADOOP_NAMENODE_HOST=namenode      # nombre del servicio docker
HADOOP_NAMENODE_PORT=9000
HDFS_RAW_PATH=/data/raw
HDFS_PROCESSED_PATH=/data/processed
HDFS_INFORMES_PATH=/informes/diarios
```

### 4.4 Integración con la red compartida

El `docker-compose.yml` de Hadoop debe usar la misma red que el resto:

```yaml
networks:
  shared-ml-network:
    external: true
```

Así la API y el notebook JupyterLab pueden resolver `namenode:9000` sin exponer el puerto al exterior.

---

## 5. Docker: n8n

**Archivo:** `infrastructure/n8n/docker-compose.yml`

### 5.1 Imagen y configuración básica

```yaml
services:
  n8n:
    image: n8nio/n8n:latest
    container_name: n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_HOST=0.0.0.0
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - WEBHOOK_URL=http://<EC2-IP>:5678/
      - N8N_EMAIL_MODE=smtp
      - N8N_SMTP_HOST=${SMTP_HOST}
      - N8N_SMTP_PORT=${SMTP_PORT}
      - N8N_SMTP_USER=${SMTP_USER}
      - N8N_SMTP_PASS=${SMTP_PASS}
      - N8N_SMTP_SENDER=${SMTP_SENDER}
    volumes:
      - n8n_data:/home/node/.n8n
    networks:
      - shared-ml-network

volumes:
  n8n_data:

networks:
  shared-ml-network:
    external: true
```

### 5.2 Variables de entorno para n8n (añadir a `.env`)

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_email@gmail.com
SMTP_PASS=tu_app_password
SMTP_SENDER=fraude-sistema@tudominio.com
ADMIN_EMAIL=admin@tudominio.com
```

> Para Gmail usar una **App Password** (no la contraseña normal). Activar en: Google Account → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones.

### 5.3 Workflow diario de n8n — Diseño

El workflow `workflow_informe_diario.json` tiene estos nodos:

```
[Cron: 00:00 cada día]
        │
        ▼
[HTTP Request → GET hdfs://namenode:9870/webhdfs/v1/...]
        │  Lee transacciones del día anterior desde WebHDFS REST API
        │  (o alternativamente, consulta la API FastAPI /transactions/today)
        ▼
[Function: procesar y agregar datos]
        │  total_transacciones, total_fraudes, importe_total_fraude,
        │  top_10_cuentas_sospechosas, distribución por tipo
        ▼
[HTML/Markdown → construir cuerpo del email]
        ▼
[Send Email → ADMIN_EMAIL]
        │  Asunto: "Informe Diario Fraude — {{fecha}}"
        ▼
[HTTP Request → POST /informes al API FastAPI]
        │  Persiste el informe en HDFS /informes/diarios/YYYY-MM-DD.json
```

> **Alternativa recomendada para el acceso a datos:** en lugar de leer HDFS directamente desde n8n (que requiere cliente Java), añadir un endpoint `GET /transactions/summary?date=YYYY-MM-DD` a la API FastAPI que consulte los datos y devuelva el JSON. n8n simplemente llama esa URL. Más limpio y desacoplado.

---

## 6. Integración: API FastAPI ← → Hadoop

Para que la API guarde transacciones en HDFS, hay que añadir una dependencia a `hdfs` (Python) o `requests` (WebHDFS REST). La forma más simple es usar **WebHDFS**:

```python
# En src/main.py, tras devolver la predicción:
import requests, json
from datetime import date

def save_to_hdfs(transaction: dict, prediction: dict):
    today = date.today().isoformat()
    payload = {**transaction, **prediction, "timestamp": today}
    url = f"http://namenode:9870/webhdfs/v1/data/raw/{today}/{payload['timestamp']}.json?op=CREATE&overwrite=false"
    # WebHDFS devuelve redirect al DataNode
    r = requests.put(url, allow_redirects=False)
    redirect_url = r.headers['Location']
    requests.put(redirect_url, data=json.dumps(payload))
```

> Esto es orientativo, no implementar hasta tener Hadoop corriendo en local.

---

## 7. Despliegue en AWS

### 7.1 Infraestructura mínima

| Recurso | Tipo sugerido | Propósito |
|---------|---------------|-----------|
| EC2 #1 | `t3.medium` (2vCPU, 4GB) | API FastAPI + Neo4j |
| EC2 #2 | `t3.large` (2vCPU, 8GB) | Hadoop NameNode+DataNode |
| EC2 #3 | `t3.small` (2vCPU, 2GB) | n8n |
| VPC | Default o nueva | Subred privada compartida |
| Security Groups | Uno por servicio | Control de acceso |
| Elastic IP | Una por EC2 pública | IPs estables |

> **Consejo de coste:** Si el presupuesto es ajustado, se puede meter API+n8n en la misma `t3.medium` y Hadoop solo en la suya (necesita RAM).

### 7.2 Security Groups

**SG-API (EC2 #1):**
```
Inbound:
  TCP 8000  0.0.0.0/0   ← FastAPI (acceso frontend)
  TCP 7474  0.0.0.0/0   ← Neo4j Browser
  TCP 7687  SG-interno  ← Bolt (solo interno)
  TCP 22    tu-IP/32    ← SSH solo desde tu IP
Outbound: All
```

**SG-Hadoop (EC2 #2):**
```
Inbound:
  TCP 9870  0.0.0.0/0        ← NameNode Web UI
  TCP 9000  SG-interno       ← HDFS RPC (solo servicios internos)
  TCP 8088  0.0.0.0/0        ← YARN UI
  TCP 22    tu-IP/32
Outbound: All
```

**SG-N8N (EC2 #3):**
```
Inbound:
  TCP 5678  0.0.0.0/0   ← n8n UI + webhooks
  TCP 22    tu-IP/32
Outbound: All
```

### 7.3 Pasos de aprovisionamiento AWS (orden)

```
1. Crear VPC  (o usar la default)
2. Crear Key Pair (.pem)  →  guardar en local
3. Lanzar EC2 #2 (Hadoop)  →  Ubuntu 22.04 LTS
4. Lanzar EC2 #1 (API+Neo4j)  →  Ubuntu 22.04 LTS
5. Lanzar EC2 #3 (n8n)  →  Ubuntu 22.04 LTS
6. Asignar Elastic IPs a cada instancia
7. Configurar Security Groups según tabla anterior
8. SSH a cada instancia → instalar Docker + Docker Compose
9. Clonar repo en cada instancia (git clone)
10. Copiar .env con variables correctas (scp o secrets manager)
11. Levantar servicios con docker compose up -d
12. Verificar conectividad inter-servicios
```

### 7.4 Instalación de Docker en EC2 (Ubuntu)

```bash
# Ejecutar en cada instancia tras hacer SSH
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu
newgrp docker

# Verificar
docker --version
docker compose version
```

### 7.5 Variables de entorno en producción

Copiar `.env` a cada instancia con `scp`:

```bash
scp -i clave.pem .env ubuntu@<EC2-IP>:~/ml-fraud-detection/
```

O usar **AWS Systems Manager Parameter Store** para secretos (más seguro, recomendado si el tiempo lo permite).

### 7.6 Comandos de arranque por instancia

**EC2 #2 — Hadoop:**
```bash
cd ~/ml-fraud-detection
docker compose -f infrastructure/hadoop/docker-compose.yml up -d
# Verificar:  curl http://localhost:9870
```

**EC2 #1 — API + Neo4j:**
```bash
cd ~/ml-fraud-detection
# Primero crear la red compartida
docker network create shared-ml-network
docker compose -f infrastructure/ml-env/docker-compose.yml up -d neo4j
docker compose -f infrastructure/api/docker-compose.yml up -d
# Verificar:  curl http://localhost:8000/health
```

**EC2 #3 — n8n:**
```bash
cd ~/ml-fraud-detection
docker compose -f infrastructure/n8n/docker-compose.yml up -d
# Acceder:  http://<Elastic-IP>:5678
# Importar workflow_informe_diario.json desde la UI
```

---

## 8. Pruebas de integración end-to-end

### 8.1 Prueba local (antes de AWS)

```bash
# 1. Crear red compartida local
docker network create shared-ml-network

# 2. Levantar Hadoop
docker compose -f infrastructure/hadoop/docker-compose.yml up -d

# 3. Levantar API + Neo4j
docker compose -f infrastructure/ml-env/docker-compose.yml up -d

# 4. Levantar n8n
docker compose -f infrastructure/n8n/docker-compose.yml up -d

# 5. Ejecutar notebook de ingesta (con Jupyter en puerto 8888)

# 6. Lanzar transacción de prueba a la API
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 9000.0,
    "old_balance_orig": 10000.0,
    "new_balance_orig": 1000.0,
    "old_balance_dest": 0.0,
    "new_balance_dest": 9000.0,
    "orig_out_degree": 5.0,
    "orig_pagerank": 0.01,
    "orig_community": 2.0,
    "dest_in_degree": 3.0,
    "dest_pagerank": 0.005,
    "dest_community": 7.0,
    "type_CASH_IN": 0.0,
    "type_CASH_OUT": 0.0,
    "type_DEBIT": 0.0,
    "type_PAYMENT": 0.0,
    "type_TRANSFER": 1.0
  }'

# 7. Verificar en HDFS que la transacción fue guardada
# http://localhost:9870  → Browser → /data/raw/

# 8. Disparar manualmente el workflow de n8n y verificar email
```

### 8.2 Checklist de validación

- [ ] `curl http://<API-IP>:8000/health` → `{"status":"ok"}`
- [ ] `curl http://<Hadoop-IP>:9870` → NameNode Web UI accesible
- [ ] NameNode en modo ACTIVE (no safe mode)
- [ ] `hdfs dfs -ls /data/raw/` → muestra datos ingestados
- [ ] n8n UI accesible en `http://<N8N-IP>:5678`
- [ ] Workflow de informe diario ejecuta sin errores
- [ ] Email de informe llega a la cuenta admin
- [ ] Neo4j Browser accesible en `http://<API-IP>:7474`

---

## 9. Orden de trabajo recomendado

```
Semana actual:
  [x] Revisar proyecto del compañero (este documento)
  [ ] Levantar stack de Zuhir en local (red + neo4j + api)
  [ ] Verificar que POST /predict funciona correctamente en local

Próximos pasos:
  [ ] Crear infrastructure/hadoop/docker-compose.yml
  [ ] Crear infrastructure/n8n/docker-compose.yml
  [ ] Levantar Hadoop local y verificar UI en puerto 9870
  [ ] Crear notebook hadoop_pyspark_ingesta.ipynb
  [ ] Probar notebook completo (descarga Kaggle → HDFS → Parquet)
  [ ] Diseñar y probar workflow n8n en local
  [ ] Solicitar créditos AWS Educate o activar Free Tier
  [ ] Desplegar en AWS siguiendo sección 7
  [ ] Pruebas end-to-end en producción
  [ ] Documentar IPs públicas y credenciales en .env.prod (NO subir a git)
```

---

## 10. Referencias técnicas

| Recurso | URL |
|---------|-----|
| Imagen Docker Hadoop oficial | `apache/hadoop:3` |
| WebHDFS REST API docs | https://hadoop.apache.org/docs/current/hadoop-project-dist/hadoop-hdfs/WebHDFS.html |
| PySpark SparkSession con HDFS | https://spark.apache.org/docs/latest/api/python/ |
| Dataset Kaggle PaySim | https://www.kaggle.com/datasets/ealaxi/paysim1 |
| n8n Docker docs | https://docs.n8n.io/hosting/installation/docker/ |
| n8n HTTP Request node | https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/ |
| AWS EC2 Free Tier | https://aws.amazon.com/free/ |
| AWS Security Groups | https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html |

---

*Documento generado con el contexto del repositorio en rama `feature/hadoop`. Actualizar conforme avance la implementación.*
