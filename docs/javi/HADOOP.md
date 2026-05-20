# Infraestructura Hadoop — Guía de Despliegue

> Parte del TFG: Sistema de Detección de Fraude Bancario  
> Responsable: Javi | Rama: `feature/hadoop`

---

## Estructura de archivos

```
infrastructure/hadoop/
├── Dockerfile                  # Imagen basada en apache/hadoop:3.4.1 + PySpark
├── docker-compose.yml          # Servicio hadoop en shared-ml-network
├── conf/
│   ├── core-site.xml           # fs.defaultFS = hdfs://hadoop:9000
│   ├── hdfs-site.xml           # replicación=1, WebHDFS habilitado
│   ├── mapred-site.xml         # framework=yarn, JobHistory en 19888
│   └── yarn-site.xml           # ResourceManager, 2GB NodeManager
└── scripts/
    └── start-hadoop.sh         # Arranque: formato NameNode (1ª vez) + daemons
```

---

## Requisitos previos

- Docker Desktop en ejecución
- Red `shared-ml-network` creada:
  ```bash
  docker network create shared-ml-network
  ```
- Stack de Zuhir levantado (neo4j + ml-env + ai-service):
  ```bash
  docker compose -f infrastructure/ml-env/docker-compose.yml up -d
  docker compose -f infrastructure/api/docker-compose.yml up -d
  ```

---

## Arrancar Hadoop

```bash
# Desde la raíz del proyecto
docker compose -f infrastructure/hadoop/docker-compose.yml up -d
```

La primera vez **formatea el NameNode automáticamente** y crea los directorios HDFS:
- `/data/raw`
- `/data/processed`
- `/data/fraud-results`

### Verificar que está listo

```bash
docker logs hadoop --follow
# Esperar a: "Hadoop arrancado correctamente"

# Comprobar NameNode
curl http://localhost:9870

# Listar directorios HDFS
docker exec hadoop hdfs dfs -ls /data/
```

---

## Interfaces Web

| Servicio | URL | Descripción |
|---|---|---|
| NameNode UI | http://localhost:9870 | Estado de HDFS, bloques, salud |
| YARN UI | http://localhost:8088 | Jobs MapReduce / Spark |
| NodeManager | http://localhost:8042 | Recursos del nodo |
| JobHistory | http://localhost:19888 | Historial de jobs |

---

## Puertos expuestos

| Puerto | Protocolo | Uso |
|---|---|---|
| 9870 | HTTP | NameNode Web UI |
| 9000 | TCP | HDFS RPC (namenode) |
| 8088 | HTTP | YARN ResourceManager UI |
| 8042 | HTTP | NodeManager UI |
| 19888 | HTTP | MapReduce JobHistory |

---

## Estructura HDFS

```
/
├── user/
│   └── hadoop/              # Directorio home del usuario hadoop
└── data/
    ├── raw/                 # Dataset descargado sin procesar (Parquet)
    │   └── transactions.parquet
    ├── processed/           # Dataset limpio con features del modelo
    │   └── transactions_clean.parquet
    └── fraud-results/       # Predicciones de fraude por batch
        └── batch_predictions.parquet
```

---

## Volúmenes Docker

| Volumen | Contenido |
|---|---|
| `hadoop_namenode` | Metadatos del sistema de ficheros HDFS |
| `hadoop_datanode` | Bloques de datos reales |
| `hadoop_logs` | Logs de NameNode, DataNode, YARN |

Los datos **persisten entre reinicios**. Para empezar desde cero:
```bash
docker compose -f infrastructure/hadoop/docker-compose.yml down -v
```

---

## Integración con el resto del stack

### Desde JupyterLab (ml-env → puerto 8888)

El notebook `notebooks/hadoop_pyspark_ingesta.ipynb` realiza el flujo completo:
1. Descarga el dataset de HuggingFace
2. Crea SparkSession con `fs.defaultFS=hdfs://hadoop:9000`
3. Guarda datos raw en HDFS como Parquet
4. Aplica limpieza y feature engineering
5. Llama al API `http://ai-service:8000/predict` vía UDF
6. Guarda predicciones en `/data/fraud-results/`

### Desde n8n (planificado, puerto 5678)

n8n accede a HDFS mediante **WebHDFS REST API**:
```
GET  http://hadoop:9870/webhdfs/v1/data/fraud-results/?op=LISTSTATUS
GET  http://hadoop:9870/webhdfs/v1/data/fraud-results/batch_predictions.parquet?op=OPEN
```

### Conexión entre servicios

Todos los servicios comparten `shared-ml-network`:
```
ml-env      → hadoop:9000   (HDFS RPC)
ml-env      → ai-service:8000  (predicciones)
n8n (futuro)→ hadoop:9870   (WebHDFS)
```

---

## Parar el servicio

```bash
# Parar sin borrar datos
docker compose -f infrastructure/hadoop/docker-compose.yml down

# Parar y borrar datos HDFS (⚠️ irreversible)
docker compose -f infrastructure/hadoop/docker-compose.yml down -v
```

---

## Troubleshooting

### NameNode en modo seguro (safe mode)
```bash
docker exec hadoop hdfs dfsadmin -safemode leave
```

### Error "Connection refused" en puerto 9000
```bash
# Verificar que el NameNode está corriendo
docker exec hadoop jps
# Debe aparecer: NameNode, DataNode, ResourceManager, NodeManager
```

### Permisos denegados en HDFS
```bash
# Los permisos están desactivados en modo desarrollo (dfs.permissions.enabled=false)
# Si persiste:
docker exec hadoop hdfs dfs -chmod -R 777 /data
```
