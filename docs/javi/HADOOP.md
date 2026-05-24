# Hadoop y HDFS — Documentación del Sistema de Big Data

> TFG: Sistema de Detección de Fraude Bancario  
> Tecnologías: Apache Hadoop 3.4.1 · HDFS · YARN · PySpark · WebHDFS

---

## 1. ¿Qué es Hadoop y por qué lo usamos?

**Apache Hadoop** es un framework de código abierto para el almacenamiento y procesamiento distribuido de grandes volúmenes de datos. Nació en Google (GFS + MapReduce, 2003-2004) y se convirtió en el estándar de Big Data durante la última década.

Hadoop tiene dos componentes fundamentales:
- **HDFS** (Hadoop Distributed File System): sistema de ficheros distribuido que divide los datos en bloques y los replica en varios nodos
- **YARN** (Yet Another Resource Negotiator): gestor de recursos del cluster que permite ejecutar jobs de procesamiento (MapReduce, Spark...) sobre los datos de HDFS

### ¿Por qué en este proyecto?

El dataset de fraude bancario (PaySim) tiene 6.3 millones de transacciones. En un contexto real de producción, estos datasets pueden tener miles de millones de filas. Hadoop/HDFS permite:

1. **Almacenamiento desacoplado del código:** los datos viven en HDFS independientemente de qué aplicación los procese
2. **Integración con PySpark:** Spark lee nativamente de HDFS y distribuye el procesamiento entre workers
3. **Reproducibilidad del pipeline:** el notebook de ingesta descarga el dataset a HDFS una vez; cualquier otro servicio puede leerlo sin volver a descargarlo
4. **Contexto académico/profesional:** el uso de HDFS + Spark es el patrón estándar en entornos de Data Engineering, y su inclusión en el TFG demuestra conocimiento del stack Big Data real

### Configuración en este proyecto: pseudo-distribuido

En producción real, Hadoop corre en un cluster de 10-100 nodos físicos. En este proyecto usamos el modo **pseudo-distribuido**: todos los daemons de Hadoop (NameNode, DataNode, ResourceManager, NodeManager) corren en el mismo contenedor Docker, simulando un cluster de 1 nodo.

Esto es suficiente para el volumen de datos del TFG y reproduce la misma arquitectura y APIs que un cluster real.

---

## 2. Arquitectura de HDFS

### Componentes

```
┌────────────────────────────────────────────────────────┐
│                  Contenedor Hadoop                     │
│                                                        │
│   ┌──────────────┐         ┌──────────────────────┐   │
│   │   NameNode   │         │      DataNode        │   │
│   │              │         │                      │   │
│   │ Metadatos:   │◄───────►│  Bloques de datos    │   │
│   │ - árbol de   │         │  (ficheros reales)   │   │
│   │   directorios│         │                      │   │
│   │ - ubicación  │         └──────────────────────┘   │
│   │   de bloques │                                     │
│   └──────────────┘                                     │
│                                                        │
│   ┌──────────────────┐     ┌──────────────────────┐   │
│   │ ResourceManager  │     │    NodeManager       │   │
│   │  (YARN)          │◄───►│    (YARN)            │   │
│   │                  │     │                      │   │
│   │ Asigna recursos  │     │ Ejecuta containers   │   │
│   │ a jobs Spark/MR  │     │ de jobs              │   │
│   └──────────────────┘     └──────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

### NameNode
El "maestro" del sistema de ficheros. Guarda en memoria el árbol de directorios y la ubicación de cada bloque en qué DataNode está. No guarda los datos en sí. Es el único punto de fallo en este setup (en producción se tienen dos NameNodes: activo + standby).

### DataNode
El "obrero" que almacena los bloques de datos reales. En producción hay decenas o centenares de DataNodes. Aquí solo hay uno (mismo contenedor). Los bloques tienen 128 MB por defecto; un fichero de 500 MB se divide en 4 bloques.

### Replicación
En producción HDFS replica cada bloque en 3 DataNodes para tolerancia a fallos. En este proyecto la replicación está configurada a **1** (solo hay 1 DataNode, no tiene sentido replicar).

---

## 3. Ficheros de configuración

### `conf/core-site.xml` — Configuración global

```xml
<configuration>
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://hadoop:9000</value>   <!-- URI del NameNode -->
  </property>
  <property>
    <name>hadoop.tmp.dir</name>
    <value>/opt/hadoop/data</value>
  </property>
</configuration>
```

El `fs.defaultFS` establece que el sistema de ficheros por defecto es el NameNode que escucha en `hadoop:9000`. Desde cualquier servicio en la red Docker (`ml-env`, `ai-service`...) se puede referenciar un fichero HDFS como `hdfs://hadoop:9000/data/raw/transactions.parquet`.

### `conf/hdfs-site.xml` — Configuración HDFS

```xml
<configuration>
  <property>
    <name>dfs.replication</name>
    <value>1</value>                   <!-- 1 DataNode, no replicar -->
  </property>
  <property>
    <name>dfs.webhdfs.enabled</name>
    <value>true</value>                <!-- API REST WebHDFS activa -->
  </property>
  <property>
    <name>dfs.namenode.name.dir</name>
    <value>/opt/hadoop/data/nameNode</value>
  </property>
  <property>
    <name>dfs.datanode.data.dir</name>
    <value>/opt/hadoop/data/dataNode</value>
  </property>
</configuration>
```

### `conf/yarn-site.xml` — Gestión de recursos para Spark

```xml
<configuration>
  <property>
    <name>yarn.nodemanager.aux-services</name>
    <value>mapreduce_shuffle</value>
  </property>
  <property>
    <name>yarn.resourcemanager.hostname</name>
    <value>hadoop</value>
  </property>
  <property>
    <name>yarn.nodemanager.resource.memory-mb</name>
    <value>2048</value>               <!-- 2 GB para jobs Spark -->
  </property>
</configuration>
```

### `conf/mapred-site.xml` — Framework de ejecución

```xml
<configuration>
  <property>
    <name>mapreduce.framework.name</name>
    <value>yarn</value>               <!-- Jobs corren sobre YARN, no local -->
  </property>
  <property>
    <name>mapreduce.jobhistory.address</name>
    <value>hadoop:10020</value>
  </property>
</configuration>
```

---

## 4. Estructura de archivos del proyecto

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

---

## 5. Arranque del servicio

```bash
# Prerrequisito: red compartida debe existir
docker network create shared-ml-network

# Levantar Hadoop
docker compose -f infrastructure/hadoop/docker-compose.yml up -d
```

**La primera vez** el script `start-hadoop.sh` formatea el NameNode automáticamente y crea los directorios HDFS:
- `/data/raw` — datos sin procesar
- `/data/processed` — datos limpios con features
- `/data/fraud-results` — predicciones de batch

### Verificar que está listo

```bash
docker logs hadoop --follow
# Esperar a: "Hadoop arrancado correctamente"

# Comprobar que el NameNode responde:
curl http://localhost:9870

# Listar directorios HDFS:
docker exec hadoop hdfs dfs -ls /data/

# Verificar todos los daemons en ejecución:
docker exec hadoop jps
# Debe mostrar: NameNode, DataNode, ResourceManager, NodeManager, Jps
```

### Cuánto tarda en arrancar

El primer arranque (formato del NameNode) tarda ~30 segundos. Los reinicios posteriores son más rápidos (~10-15 s). El NameNode entra en **safe mode** brevemente al arrancar; sale automáticamente en unos segundos.

---

## 6. Interfaces Web

| Servicio | URL | Descripción |
|---|---|---|
| NameNode UI | http://localhost:9870 | Estado de HDFS, bloques, capacidad, salud del cluster |
| YARN ResourceManager | http://localhost:8088 | Monitoring de jobs Spark/MapReduce |
| NodeManager | http://localhost:8042 | Recursos del nodo (CPU, memoria) |
| JobHistory Server | http://localhost:19888 | Historial de jobs completados |

### Qué ver en el NameNode UI (puerto 9870)

La interfaz web del NameNode muestra:
- **Overview**: estado del cluster, versión Hadoop, modo (active/standby)
- **Datanodes**: nodos de datos registrados, capacidad total, usada y disponible
- **Filesystem**: árbol de directorios HDFS navegable
- **Logs**: logs del NameNode en tiempo real

---

## 7. Puertos expuestos

| Puerto | Protocolo | Uso |
|---|---|---|
| 9870 | HTTP | NameNode Web UI + WebHDFS REST API |
| 9000 | TCP | HDFS RPC (acceso programático: Spark, Python) |
| 8088 | HTTP | YARN ResourceManager UI |
| 8042 | HTTP | NodeManager UI |
| 19888 | HTTP | MapReduce JobHistory Server |

---

## 8. Estructura de datos en HDFS

```
/
├── user/
│   └── hadoop/              # Directorio home del usuario hadoop
└── data/
    ├── raw/                 # Dataset descargado sin procesar (formato Parquet)
    │   └── transactions.parquet
    ├── processed/           # Dataset limpio con todas las features del modelo
    │   └── transactions_clean.parquet
    └── fraud-results/       # Predicciones de fraude por batch
        └── batch_predictions.parquet
```

### ¿Por qué Parquet?

Parquet es el formato de almacenamiento columnar estándar en Big Data. Ventajas frente a CSV:
- **Compresión:** 5-10x menos espacio en disco
- **Velocidad:** Spark solo lee las columnas necesarias, no toda la fila
- **Tipos:** guarda el schema (tipos de datos) junto con los datos, no hay ambigüedad
- **Interoperabilidad:** puede leerlo Spark, pandas, DuckDB, Athena, BigQuery...

---

## 9. Volúmenes Docker

| Volumen | Contenido | Tipo |
|---|---|---|
| `hadoop_namenode` | Metadatos del sistema de ficheros HDFS | Named volume |
| `hadoop_datanode` | Bloques de datos reales (los ficheros Parquet) | Named volume |
| `hadoop_logs` | Logs de NameNode, DataNode, YARN | Named volume |

Los datos **persisten entre reinicios** del contenedor. Para empezar desde cero:
```bash
# ⚠️ Esto borra todos los datos de HDFS
docker compose -f infrastructure/hadoop/docker-compose.yml down -v
```

---

## 10. Integración con PySpark

### Cómo ml-env se conecta a HDFS

Desde el contenedor `ml-env` (JupyterLab), PySpark se conecta a Hadoop usando la URI `hdfs://hadoop:9000` gracias a la red compartida `shared-ml-network`. El nombre `hadoop` se resuelve automáticamente al IP del contenedor.

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("FraudDetection-Ingesta") \
    .config("spark.hadoop.fs.defaultFS", "hdfs://hadoop:9000") \
    .getOrCreate()

# Leer desde HDFS
df = spark.read.parquet("hdfs://hadoop:9000/data/raw/transactions.parquet")

# Escribir a HDFS
df_procesado.write.mode("overwrite").parquet("hdfs://hadoop:9000/data/processed/")
```

### Pipeline del notebook de ingesta (`hadoop_pyspark_ingesta.ipynb`)

```
[1] Descargar dataset (HuggingFace API)
         │  5M+ filas → sample de 100K para desarrollo
         ▼
[2] Crear SparkSession conectada a HDFS
         │
         ▼
[3] Guardar datos raw en /data/raw/ (Parquet)
         │
         ▼
[4] Feature engineering con PySpark
         │  Limpiar nulos, transformar tipos, calcular features derivadas
         ▼
[5] Llamar a FastAPI (ai-service:8000/predict) vía pandas UDF
         │  Batch de predicciones por cada partición del DataFrame
         ▼
[6] Guardar predicciones en /data/fraud-results/ (Parquet)
```

---

## 11. WebHDFS REST API

HDFS ofrece una API REST llamada **WebHDFS** para acceder al sistema de ficheros sin necesidad de instalar el cliente de Hadoop. Es la forma de acceder desde n8n u otros servicios que no tienen las librerías Java de Hadoop.

### Endpoints principales

```
# Listar directorio:
GET http://hadoop:9870/webhdfs/v1/data/fraud-results/?op=LISTSTATUS

# Leer fichero (devuelve el contenido):
GET http://hadoop:9870/webhdfs/v1/data/fraud-results/predictions.parquet?op=OPEN

# Crear directorio:
PUT http://hadoop:9870/webhdfs/v1/data/nuevo-dir?op=MKDIRS

# Subir fichero:
PUT http://hadoop:9870/webhdfs/v1/data/raw/nuevo.parquet?op=CREATE
```

---

## 12. Comandos de referencia

### Gestión de HDFS

```bash
# Listar ficheros:
docker exec hadoop hdfs dfs -ls /data/

# Ver tamaño de un directorio:
docker exec hadoop hdfs dfs -du -h /data/

# Copiar fichero del host a HDFS:
docker exec hadoop hdfs dfs -put /ruta/local.parquet /data/raw/

# Copiar fichero de HDFS al host:
docker exec hadoop hdfs dfs -get /data/raw/transactions.parquet /tmp/

# Borrar fichero:
docker exec hadoop hdfs dfs -rm /data/raw/transactions.parquet

# Borrar directorio recursivamente:
docker exec hadoop hdfs dfs -rm -r /data/processed/

# Ver estado del cluster:
docker exec hadoop hdfs dfsadmin -report
```

### Gestión del servicio

```bash
# Parar sin borrar datos:
docker compose -f infrastructure/hadoop/docker-compose.yml down

# Parar y borrar datos HDFS (⚠️ irreversible):
docker compose -f infrastructure/hadoop/docker-compose.yml down -v

# Ver logs en tiempo real:
docker logs hadoop --follow

# Entrar al contenedor:
docker exec -it hadoop bash
```

---

## 13. Solución de problemas

### NameNode en modo seguro (safe mode)

Ocurre al arrancar y cuando el DataNode reporta menos bloques de los esperados:
```bash
docker exec hadoop hdfs dfsadmin -safemode leave
```

### Error "Connection refused" en puerto 9000

El NameNode no ha arrancado. Verificar:
```bash
docker exec hadoop jps
# Debe aparecer: NameNode, DataNode, ResourceManager, NodeManager
```

Si falta alguno:
```bash
docker logs hadoop --tail 50
# Buscar errores de Java o problemas de permisos en /opt/hadoop/data
```

### Error "Could not obtain block" al leer Parquet

El DataNode no está registrado con el NameNode. Reiniciar:
```bash
docker compose -f infrastructure/hadoop/docker-compose.yml restart
```

### Permisos denegados en HDFS

Los permisos están desactivados en desarrollo (`dfs.permissions.enabled=false`). Si persisten errores:
```bash
docker exec hadoop hdfs dfs -chmod -R 777 /data
docker exec hadoop hdfs dfs -chown -R hadoop:hadoop /data
```

### Spark no encuentra el NameNode desde ml-env

Verificar que ambos contenedores están en la misma red:
```bash
docker network inspect shared-ml-network
# Deben aparecer: hadoop, ml-env (y el resto del stack)
```
