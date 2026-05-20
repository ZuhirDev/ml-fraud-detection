# Pipeline de Ingesta Big Data — Documentación Técnica

> Parte del TFG: Sistema de Detección de Fraude Bancario  
> Autor: Javi — Big Data / Infraestructura

---

## Resumen ejecutivo

Se ha implementado un pipeline completo de ingesta y procesamiento de datos de fraude bancario utilizando **Apache Hadoop (HDFS)** como almacenamiento distribuido y **Apache Spark (PySpark)** como motor de procesamiento. El pipeline descarga un dataset real de transacciones financieras nigerianas desde HuggingFace, lo transforma y persiste en HDFS en tres capas, y finalmente lo integra con una API de predicción de fraude basada en Machine Learning.

---

## Dataset

- **Fuente:** HuggingFace — `electricsheepafrica/Nigerian-Financial-Transactions-and-Fraud-Detection-Dataset`
- **Tamaño completo:** ~5 millones de filas, 45 columnas
- **Muestra de desarrollo:** 100.000 filas (muestreo estratificado por clase `is_fraud`)
- **Columnas clave:** `amount_ngn`, `transaction_type`, `is_fraud`, `fraud_type`, `bvn_linked`, `new_device_transaction`, `geospatial_velocity_anomaly`, entre otras
- **Diferencias respecto a PaySim (dataset de referencia):**
  - El importe se llama `amount_ngn` (no `amount`)
  - El tipo de transacción es `transaction_type` (no `type`)
  - `is_fraud` es de tipo BOOLEAN (no entero)
  - No existen columnas de balance (`oldbalanceOrg`, etc.) — se usan placeholders 0.0
  - Contiene columnas adicionales de contexto geográfico, de comportamiento y de dispositivo

---

## Arquitectura del pipeline

```
HuggingFace (5M filas)
        │
        ▼
  Muestreo estratificado (100k filas)
        │
        ▼
  pandas DataFrame (memoria Python)
        │
        ▼  [pandas → /tmp/parquet → spark.read]  ← evita OOM en JVM
  Spark DataFrame
        │
        ├──► HDFS /data/raw/transactions.parquet
        │
        ▼
  Limpieza + Transformaciones (PySpark)
  - Null check por tipo (isnan solo en float/double)
  - Drop filas sin amount_ngn / transaction_type / is_fraud
  - Normalizar transaction_type → UPPERCASE
  - Filtrar importes ≤ 0
        │
        ▼
  Feature Engineering (PySpark)
  - OHE manual: type_CASH_IN, type_CASH_OUT, type_DEBIT, type_PAYMENT, type_TRANSFER
  - Rename: amount_ngn → amount
  - Placeholders 0.0: old_balance_orig, new_balance_orig, old_balance_dest, new_balance_dest
  - Placeholders 0.0: orig_out_degree, orig_pagerank, orig_community (Neo4j pendiente)
  - Placeholders 0.0: dest_in_degree, dest_pagerank, dest_community (Neo4j pendiente)
        │
        ├──► HDFS /data/processed/transactions_clean.parquet
        │
        ▼
  Llamada al API de predicción (http://ai-service:8000/predict)
  - 5 muestras de prueba (validación del pipeline)
  - Batch de 1000 filas con UDF de Spark
        │
        └──► HDFS /data/fraud-results/batch_predictions.parquet
```

---

## Tecnologías utilizadas

| Componente | Versión | Rol |
|---|---|---|
| Apache Hadoop | 3.3.6 | HDFS — almacenamiento distribuido |
| Apache Spark | 3.5.3 | Motor de procesamiento distribuido |
| PySpark | 3.5.3 | API Python de Spark |
| PyArrow | 16.1.0 | Serialización columnar pandas↔Spark |
| HuggingFace datasets | 2.20.0 | Descarga del dataset |
| FastAPI (ai-service) | — | API de predicción ML |
| Docker / Docker Compose | — | Orquestación de servicios |

---

## Infraestructura Docker

Todos los servicios corren en una red Docker bridge llamada `shared-ml-network`:

| Contenedor | Imagen base | Puertos | Función |
|---|---|---|---|
| `hadoop` | hadoop:3.3.6 custom | 9870, 9000, 8088, 8042 | HDFS NameNode + DataNode + YARN |
| `ml-env` | python:3.10 + PySpark | 8888 | JupyterLab — ejecuta el notebook |
| `ai-service` | python:3.10 + FastAPI | 8000 | API de predicción de fraude |
| `neo4j` | neo4j:5 | 7474, 7687 | Base de datos de grafos (PageRank) |
| `n8n` | n8nio/n8n | 5678 | Automatización de workflows |

### Configuración de recursos Hadoop (límites aplicados para entorno local)

```yaml
environment:
  HADOOP_HEAPSIZE: 256
  YARN_HEAPSIZE: 256
  HADOOP_OPTS: -Xmx256m
deploy:
  resources:
    limits:
      memory: "2g"
      cpus: "1.5"
```

> Necesario para evitar saturación de CPU al 150% en entorno de desarrollo local (WSL2 + Docker Desktop).

---

## Estructura de datos en HDFS

```
hdfs://hadoop:9000/
└── data/
    ├── raw/
    │   └── transactions.parquet          (~10 MB, 100k filas, 45 columnas)
    ├── processed/
    │   └── transactions_clean.parquet    (~10 MB, features engineered)
    └── fraud-results/
        └── batch_predictions.parquet     (~5 MB, 1000 filas con fraud_probability)
```

Total en uso: ~25 MB sobre una capacidad configurada de 1 TB (entorno demo).

---

## SparkSession — configuración relevante

```python
SparkSession.builder
    .appName("FraudDetection-Ingesta")
    .master("local[*]")                              # modo local, todos los cores
    .config("spark.driver.memory", "4g")
    .config("spark.driver.maxResultSize", "2g")
    .config("spark.sql.execution.arrow.pyspark.enabled", "true")   # pandas↔Spark vectorizado
    .config("spark.sql.execution.arrow.maxRecordsPerBatch", "50000")
    .config("spark.sql.shuffle.partitions", "8")
    # Si HDFS está disponible:
    .config("spark.hadoop.fs.defaultFS", "hdfs://hadoop:9000")
    .config("spark.hadoop.dfs.client.use.datanode.hostname", "true")
    .config("spark.hadoop.ipc.client.connect.timeout", "10000")
```

---

## Problemas resueltos durante el desarrollo

### 1. Hang al crear el Spark DataFrame desde pandas (30 min colgado)
- **Causa:** `spark.createDataFrame(df_raw)` sin Arrow serializa fila a fila por Py4J
- **Solución:** Activar `spark.sql.execution.arrow.pyspark.enabled=true` + timeouts HDFS

### 2. Saturación de CPU de Hadoop al 150%
- **Causa:** Sin límites de recursos en Docker, Hadoop consumía toda la CPU del host
- **Solución:** `deploy.resources.limits` en `docker-compose.yml` + heap limitado a 256 MB

### 3. Java heap OOM al procesar 5 millones de filas
- **Causa:** `spark.createDataFrame(df_full)` con 5M×45 cols desborda el heap JVM de 2g
- **Solución:** Escritura previa a parquet con `pandas.to_parquet()` + `spark.read.parquet()` (sin pasar por JVM heap)

### 4. HDFS interceptando rutas locales
- **Causa:** Con `spark.hadoop.fs.defaultFS=hdfs://hadoop:9000`, rutas como `/tmp/file` se interpretan como HDFS
- **Solución:** Prefijo explícito `file:///tmp/file` para archivos locales

### 5. Write a HDFS bloqueado indefinidamente
- **Causa:** 5M filas (~589 MB) demasiado para entorno de desarrollo con Hadoop limitado
- **Solución:** Reducir a 100k filas con muestreo estratificado por clase `is_fraud`

### 6. `isnan()` fallando en columnas BOOLEAN
- **Causa:** `isnan()` en PySpark solo acepta tipos float/double; las columnas `is_fraud`, `bvn_linked`, etc. son BOOLEAN
- **Solución:** Función `null_expr(c_name)` que inspecciona el tipo con `isinstance(dtype, (DoubleType, FloatType))` antes de aplicar `isnan`

### 7. `FileNotFoundError: 'hdfs'` en celda 7
- **Causa:** El binario CLI `hdfs` no está instalado en el contenedor `ml-env` (es un entorno Python/ML)
- **Solución:** Usar la API Java de Spark: `spark._jvm.org.apache.hadoop.fs.FileSystem.get(...).getContentSummary(...)`

### 8. `AnalysisException: column 'amount' cannot be resolved`
- **Causa:** El dataset nigeriano tiene `amount_ngn`, no `amount`; la celda de feature engineering usaba nombres PaySim
- **Solución:** Renombrar `amount_ngn → amount` en el `rename_map` y añadir placeholders 0.0 para las 4 columnas de balance inexistentes

### 9. OHE generando solo ceros (todas las columnas `type_*` = 0)
- **Causa:** El OHE comprobaba `if "type" in columns` pero la columna se llama `transaction_type`
- **Solución:** `next((c for c in ["transaction_type", "type"] if c in columns), None)`

### 10. Arrow memory leak en `toPandas()`
- **Causa:** Con Arrow habilitado globalmente, la conversión de un plan lógico que arrastra columnas BOOLEAN genera un leak en el `ArrowAllocator`
- **Solución:** Desactivar Arrow temporalmente para el `toPandas()` de muestra pequeña:
  ```python
  spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "false")
  sample_rows = sdf_sample.toPandas()
  spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
  ```

---

## Features generadas para el modelo

El modelo de Random Forest (`modelo_fraude_rf_final.joblib`) espera exactamente estas 16 features:

| Feature | Origen | Valor en dataset nigeriano |
|---|---|---|
| `amount` | `amount_ngn` renombrada | Importe real de la transacción |
| `old_balance_orig` | PaySim — no existe | 0.0 (placeholder) |
| `new_balance_orig` | PaySim — no existe | 0.0 (placeholder) |
| `old_balance_dest` | PaySim — no existe | 0.0 (placeholder) |
| `new_balance_dest` | PaySim — no existe | 0.0 (placeholder) |
| `orig_out_degree` | Neo4j PageRank | 0.0 (pendiente integración) |
| `orig_pagerank` | Neo4j PageRank | 0.0 (pendiente integración) |
| `orig_community` | Neo4j Louvain | 0.0 (pendiente integración) |
| `dest_in_degree` | Neo4j PageRank | 0.0 (pendiente integración) |
| `dest_pagerank` | Neo4j PageRank | 0.0 (pendiente integración) |
| `dest_community` | Neo4j Louvain | 0.0 (pendiente integración) |
| `type_CASH_IN` | OHE de `transaction_type` | 0.0 o 1.0 |
| `type_CASH_OUT` | OHE de `transaction_type` | 0.0 o 1.0 |
| `type_DEBIT` | OHE de `transaction_type` | 0.0 o 1.0 |
| `type_PAYMENT` | OHE de `transaction_type` | 0.0 o 1.0 |
| `type_TRANSFER` | OHE de `transaction_type` | 0.0 o 1.0 |

> **Nota para la memoria:** El modelo fue entrenado con el dataset PaySim. Al aplicarlo sobre el dataset nigeriano, las features de balance y las de grafo son placeholders. Esto es una limitación conocida del TFG demo: en producción, el dataset nigeriano tendría que re-entrenar el modelo o mapear sus columnas correctamente.

---

## Verificación del resultado

Desde la UI de Hadoop (http://localhost:9870):
- 1 DataNode activo y en estado `Live`
- ~25 MB en uso de 1 TB de capacidad configurada
- 3 directorios activos bajo `/data/`

Desde el notebook (celda 10):
```
=== Estructura de datos (hdfs://hadoop:9000) ===

/data/raw/
  part-00000-....parquet  (X.XX MB)
  _SUCCESS

/data/processed/
  part-00000-....parquet  (X.XX MB)
  _SUCCESS

/data/fraud-results/
  part-00000-....parquet  (X.XX MB)
  _SUCCESS
```

---

## Notebook de referencia

`notebooks/hadoop_pyspark_ingesta.ipynb` — 10 secciones:

1. Instalación de dependencias
2. Descarga dataset HuggingFace (100k muestreo estratificado)
3. SparkSession con autodetección HDFS
4. pandas → parquet temporal → Spark → HDFS raw
5. Transformaciones y limpieza
6. Feature engineering para el modelo
7. Guardar procesados en HDFS
8. Llamar al API con 5 muestras de prueba
9. Predicciones en batch (1000 filas) guardadas en HDFS
10. Verificación final + `spark.stop()`
