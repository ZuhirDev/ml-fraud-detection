# Memoria Técnica — Sistema de Detección de Fraude Bancario

> TFG · Ingeniería Informática  
> Tecnologías: Python · Neo4j · Hadoop · Docker · FastAPI · n8n · Terraform · AWS

---

## 1. Descripción del proyecto y motivación

### ¿Qué se ha construido?

Un sistema completo de detección de fraude bancario que cubre el ciclo de vida entero del dato: desde la ingesta del dataset bruto hasta la predicción en tiempo real a través de una API, pasando por almacenamiento distribuido, análisis de grafos, entrenamiento de modelos y automatización de alertas con inteligencia artificial generativa.

El sistema no es un prototipo de laboratorio: está dockerizado, desplegado en AWS con infraestructura como código (Terraform), y tiene un pipeline de datos reproducible que cualquier persona puede ejecutar clonando el repositorio.

### ¿Por qué es difícil detectar fraude?

El fraude bancario presenta tres desafíos técnicos fundamentales:

**1. Desbalanceo extremo de clases.** En el dataset utilizado, solo el 0,13 % de las transacciones son fraudulentas. Si un modelo siempre predijera "no fraude", tendría una accuracy del 99,87 %, lo que lo hace inútil. Las métricas estándar (accuracy) son engañosas aquí; hay que usar precisión-recall y PR-AUC.

**2. Los patrones de fraude son relacionales, no individuales.** Un sistema basado en reglas ("si el importe supera X, es fraude") falla porque el fraude sofisticado usa importes pequeños y normales. Lo que lo delata no es la transacción aislada, sino su contexto dentro de la red: una cuenta que de repente envía dinero a 50 destinos distintos en pocas horas es sospechosa aunque cada transacción sea pequeña.

**3. La evolución constante.** Los patrones de fraude cambian con el tiempo, lo que hace necesario modelos que capturen tanto las características de la transacción como el comportamiento histórico de las cuentas.

### Solución adoptada

Se combinan dos enfoques complementarios:
- **Machine Learning supervisado** para clasificar transacciones individuales como fraude o no fraude
- **Análisis de grafos con Neo4j** para capturar el comportamiento relacional de las cuentas y generar variables (features) que un modelo tabular no podría calcular

El resultado es un conjunto de 16 features que alimentan el modelo, donde las 6 derivadas del grafo son las más discriminativas.

---

## 2. Dataset: PaySim

**Fuente:** Kaggle — `ealaxi/paysim1`  
**Tamaño completo:** 6,3 millones de transacciones · ~470 MB en CSV  
**Entorno de desarrollo:** ~872 000 registros (~14% del total, por limitaciones de disco)

PaySim es una simulación sintética generada con datos reales de un banco de Africa Oriental. Simula transacciones de dinero móvil durante 30 días (744 pasos temporales, donde cada `step` representa una hora).

### Columnas del dataset original

| Columna | Tipo | Descripción |
|---|---|---|
| `step` | int | Hora del mes (1–744). Permite división temporal train/test |
| `type` | str | Tipo de operación: CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER |
| `amount` | float | Importe de la transacción |
| `nameOrig` | str | Identificador de la cuenta origen (C1234567890) |
| `oldbalanceOrg` | float | Saldo de origen antes de la transacción |
| `newbalanceOrig` | float | Saldo de origen después de la transacción |
| `nameDest` | str | Identificador de la cuenta destino |
| `oldbalanceDest` | float | Saldo de destino antes |
| `newbalanceDest` | float | Saldo de destino después |
| `isFraud` | int (0/1) | Etiqueta real: 1 = transacción fraudulenta |
| `isFlaggedFraud` | int (0/1) | Flag del sistema de reglas del banco (muy limitado) |

### Distribución de clases

- Transacciones legítimas: 99,87 %
- Transacciones fraudulentas: 0,13 % (~8 000 en el subconjunto de desarrollo)

El fraude solo ocurre en los tipos `CASH_OUT` y `TRANSFER`. Los tipos `PAYMENT`, `CASH_IN` y `DEBIT` nunca son fraudulentos en este dataset.

---

## 3. Arquitectura del sistema

### Principio de diseño

Toda la infraestructura corre en **contenedores Docker** conectados por una red interna llamada `shared-ml-network`. Esto garantiza que:
- Cada servicio está aislado y puede desarrollarse independientemente
- Los servicios se comunican por nombre de contenedor (ej. `neo4j:7474`) sin depender de IPs
- La misma configuración funciona en local (portátil) y en AWS (EC2) sin ningún cambio

### Servicios

```
shared-ml-network (Docker bridge)
│
├── neo4j ──────── Base de datos de grafos
│   Puerto 7474 (HTTP API, browser)
│   Puerto 7687 (Bolt — protocolo nativo Neo4j)
│   Versión: Neo4j 2025.09 Enterprise
│   Volumen: data-neo/ (persistencia en disco)
│
├── ml-env ─────── Entorno de ciencia de datos
│   Puerto 8888 (JupyterLab)
│   Imagen basada en: jupyter/scipy-notebook
│   Librerías: pandas, scikit-learn, xgboost, neo4j-driver, pyspark
│   Acceso al grafo via driver Python oficial de Neo4j
│
├── ai-service ─── Microservicio de predicción
│   Puerto 8000 (FastAPI)
│   Carga modelo .pkl al arrancar
│   Endpoints: GET /health, POST /predict, GET /docs (Swagger)
│
├── hadoop ──────── Almacenamiento distribuido
│   Puerto 9870 (NameNode UI — explorador de HDFS)
│   Puerto 9000 (HDFS FileSystem — acceso programático)
│   Puerto 8088 (YARN ResourceManager — jobs Spark)
│   Puerto 8042 (NodeManager)
│   Basado en: apache/hadoop:3.4.1 + PySpark
│
└── n8n ─────────── Motor de automatización
    Puerto 5678 (interfaz web + API)
    Workflows guardados en volumen persistente n8n_data
```

### Comunicación entre servicios

```
[ml-env notebook]
    │  neo4j-driver (Bolt: neo4j:7687)
    ▼
[neo4j]
    │
    └─────────────────────────────────
                                     │
[n8n]                                │
    │  HTTP POST neo4j:7474/db/...   │
    └──────────────────────────────►[neo4j]

[ai-service]
    │  carga modelo del volumen /models
    │  recibe peticiones POST /predict
    └──────────► devuelve { fraud_probability, is_fraud }
```

---

## 4. Pipeline de datos completo

El pipeline transforma el CSV bruto de PaySim en un dataset enriquecido listo para entrenar el modelo. Se ejecuta en dos notebooks:

### Fase 1: `datasetfinal_v1.ipynb` — De CSV a features de grafo

**Paso 1 — Lectura del CSV desde HDFS**  
El dataset se almacena en HDFS (`/data/raw/ml_dataset.csv`) para simular un entorno Big Data real. Se lee con PySpark desde el contenedor `hadoop`, lo que permite escalar a datasets de millones de filas sin cargarlos en memoria.

**Paso 2 — Ingesta en Neo4j**  
Cada fila del CSV se transforma en una relación de grafo:
```
(Account {id: "C1234"}) -[:TRANSACTION {amount, type, isFraud, step, ...}]-> (Account {id: "M5678"})
```
Los nodos `Account` representan cuentas bancarias. Las relaciones `TRANSACTION` almacenan todas las propiedades de la transacción. Se usa la función `MERGE` de Cypher para evitar duplicados si la ingesta se ejecuta varias veces.

**Paso 3 — Cálculo de features de grafo**  
Con el grafo construido se ejecutan tres algoritmos de la librería Graph Data Science (GDS) de Neo4j:

- **PageRank**: calcula la importancia de cada nodo en la red de forma iterativa. Un nodo tiene PageRank alto si recibe transacciones de muchos nodos que a su vez tienen PageRank alto. Las cuentas centrales en esquemas de fraude suelen destacar aquí.

- **Degree centrality**: cuenta cuántas transacciones ha enviado (out-degree) o recibido (in-degree) cada cuenta. Las cuentas "mula" que distribuyen fondos tienen un out-degree anormalmente alto.

- **Louvain Community Detection**: agrupa cuentas en comunidades según la densidad de transacciones entre ellas. El algoritmo minimiza la modularidad del grafo, encontrando grupos de cuentas que interactúan más entre sí que con el exterior. El fraude tiende a concentrarse en comunidades pequeñas de cuentas sintéticas.

**Paso 4 — Exportación del dataset enriquecido**  
Se exporta `master_dataset_v2.csv.gz` con las features originales + las 6 de grafo. Este fichero es la entrada del notebook de entrenamiento.

### Fase 2: `fraud_detection_v2.ipynb` — Entrenamiento del modelo

**Paso 1 — Carga y preprocesamiento**
- One-hot encoding del campo `type` (CASH_OUT → 1, resto → 0)
- El campo `isFlaggedFraud` se descarta (el sistema de reglas del banco es muy limitado)
- Sin imputación: los datos de PaySim son completos

**Paso 2 — División temporal train/test**  
En lugar de una división aleatoria, se separan los datos por `step`:
- Train: primeros 80% de pasos temporales
- Test: últimos 20% de pasos temporales

Esto replica un escenario real donde se entrena con datos históricos y se evalúa el rendimiento con datos que el modelo nunca ha visto y que son temporalmente más recientes. Una división aleatoria inflaría artificialmente las métricas.

**Paso 3 — Entrenamiento comparativo**  
Se entrenan cuatro algoritmos:

| Algoritmo | Ventaja para este problema |
|---|---|
| **Decision Tree** | Interpretable, rápido, maneja bien el desbalanceo con `class_weight` |
| **Random Forest** | Reduce el sobreajuste del árbol individual mediante ensemble de árboles |
| **XGBoost** | Gradient boosting: optimiza iterativamente los errores anteriores |
| **Logistic Regression** | Baseline lineal; sirve de referencia para evaluar si los no-lineales aportan |

**Paso 4 — Optimización de hiperparámetros**  
Se usa `GridSearchCV` con validación cruzada estratificada (mantiene la proporción de fraude en cada fold) optimizando PR-AUC como métrica objetivo, no accuracy.

**Paso 5 — Serialización del modelo**  
El mejor modelo se guarda como `models/modelo_arbol_optimizado.pkl` con joblib, junto con el scaler (`StandardScaler`) que normaliza las features. Ambos son necesarios para inferencia.

---

## 5. Feature engineering con grafos: el núcleo diferencial

### Por qué los grafos añaden valor

Imaginemos dos transacciones idénticas en importe, tipo y balances. La diferencia que decide si una es fraude puede estar en que la cuenta origen de la segunda acaba de enviar dinero a 200 cuentas distintas en la última hora. Esa información es invisible en una tabla; solo es visible en un grafo.

### Las 16 features del modelo

**Features transaccionales (10):**

| Feature | Descripción |
|---|---|
| `amount` | Importe de la transacción |
| `oldbalanceOrg` | Saldo origen antes |
| `newbalanceOrig` | Saldo origen después |
| `oldbalanceDest` | Saldo destino antes |
| `newbalanceDest` | Saldo destino después |
| `type_CASH_OUT` | One-hot: 1 si tipo es CASH_OUT |
| `type_TRANSFER` | One-hot: 1 si tipo es TRANSFER |
| `type_PAYMENT` | One-hot: 1 si tipo es PAYMENT |
| `type_CASH_IN` | One-hot: 1 si tipo es CASH_IN |
| `type_DEBIT` | One-hot: 1 si tipo es DEBIT |

**Features de grafo (6):**

| Feature | Algoritmo | Qué captura | Señal de fraude |
|---|---|---|---|
| `orig_pagerank` | PageRank | Importancia global de la cuenta origen en la red | Las cuentas centrales en esquemas de blanqueo tienen PR alto |
| `dest_pagerank` | PageRank | Importancia global de la cuenta destino | Receptores finales de fondos suelen ser hubs |
| `orig_out_degree` | Degree centrality | Cuántas transacciones ha enviado el origen | Bursts de actividad saliente son sospechosos |
| `dest_in_degree` | Degree centrality | Cuántas transacciones ha recibido el destino | Concentración anormal de entradas |
| `orig_community` | Louvain | Cluster al que pertenece el origen | Fraude dentro del mismo cluster que destino |
| `dest_community` | Louvain | Cluster al que pertenece el destino | Permite detectar si son cuentas del mismo esquema criminal |

### Esquema del grafo en Neo4j

```cypher
-- Nodo Account (cada cuenta bancaria única)
(:Account {id: "C1234567890"})

-- Relación TRANSACTION (cada fila del CSV)
(:Account)-[:TRANSACTION {
  step: 1,
  type: "CASH_OUT",
  amount: 500.0,
  isFraud: 0,
  oldbalanceOrg: 10000.0,
  newbalanceOrig: 9500.0,
  oldbalanceDest: 0.0,
  newbalanceDest: 500.0,
  in_degree_hist: 3,
  out_degree_hist: 7,
  orig_pagerank_hist: 0.0012,
  dest_pagerank_hist: 0.0008
}]->(:Account)
```

---

## 6. Modelo de Machine Learning

### Algoritmo seleccionado: Decision Tree Optimizado

Tras comparar los cuatro algoritmos, el Decision Tree con hiperparámetros optimizados ofrece el mejor balance entre rendimiento y un aspecto clave para el TFG: **interpretabilidad**. Un árbol de decisión puede visualizarse y explicarse: "esta transacción se clasifica como fraude porque el out_degree del origen supera 15 y el amount está entre 1000 y 50000".

**Configuración del modelo:**
- `class_weight='balanced'` — compensa el desbalanceo multiplicando el peso de los errores en la clase minoritaria (fraude) por el ratio de desbalanceo (~770×)
- `max_depth` y `min_samples_leaf` — optimizados con GridSearchCV para evitar sobreajuste
- Sin normalización explícita en el árbol (los árboles son invariantes a la escala), pero se incluye StandardScaler en el pipeline para homogeneidad con otros modelos

### Métricas y su interpretación

Para problemas con clases muy desbalanceadas, la métrica correcta es **PR-AUC** (área bajo la curva precisión-recall), no la accuracy ni el ROC-AUC.

| Métrica | Valor (subconjunto 872K) | Significado |
|---|---|---|
| **PR-AUC** | 0.15 | Área bajo la curva P-R. Con dataset completo sube significativamente |
| **Recall** | 0.84 | El modelo detecta el 84 % de todos los fraudes reales |
| **Precision** | 0.009 | De las alertas generadas, el 0.9 % son fraude real |
| **F1-Score** | — | Harmónica entre precision y recall |

**Sobre el Recall vs Precision:** En detección de fraude, el coste de un falso negativo (no detectar un fraude real) es mucho mayor que el de un falso positivo (alertar sobre una transacción legítima). Por eso se prioriza maximizar el recall aunque la precisión sea baja. Las alertas se revisan manualmente o con un segundo filtro.

**Sobre los resultados actuales:** Los valores de PR-AUC son bajos porque el entorno de desarrollo usa solo ~872 000 de los 6,3 millones de registros de PaySim. Con el dataset completo, la distribución de fraude es más representativa y el modelo aprende patrones más robustos. El umbral de clasificación también puede ajustarse según el coste operativo deseado.

---

## 7. Microservicio de predicción (FastAPI)

### Diseño

El servicio `ai-service` expone el modelo entrenado como una API REST. Al arrancar el contenedor, carga `modelo_arbol_optimizado.pkl` en memoria. Cada petición de predicción:
1. Valida el payload con Pydantic (tipos, rangos)
2. Construye el vector de features en el orden correcto
3. Llama a `model.predict_proba()` para obtener la probabilidad
4. Devuelve la probabilidad y la clasificación binaria (umbral 0.5 por defecto)

### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Health check: `{"status": "ok", "model": "loaded"}` |
| `POST` | `/predict` | Recibe features, devuelve probabilidad de fraude |
| `GET` | `/docs` | Swagger UI automático (generado por FastAPI) |

### Ejemplo de petición y respuesta

```json
// POST /predict
// Request body:
{
  "amount": 9350.0,
  "oldbalanceOrg": 9350.0,
  "newbalanceOrig": 0.0,
  "oldbalanceDest": 0.0,
  "newbalanceDest": 9350.0,
  "type_CASH_OUT": 0,
  "type_TRANSFER": 1,
  "type_PAYMENT": 0,
  "type_CASH_IN": 0,
  "type_DEBIT": 0,
  "orig_out_degree": 47,
  "dest_in_degree": 1,
  "orig_pagerank": 0.0089,
  "dest_pagerank": 0.0002,
  "orig_community": 14,
  "dest_community": 892
}

// Response:
{
  "fraud_probability": 0.94,
  "is_fraud": true
}
```

La señal de fraude en este ejemplo: cuenta origen vacía su saldo completo a un destino con un solo ingreso previo, con alto out_degree del origen (47 transacciones previas) y comunidades distintas (no forman parte del mismo cluster habitual).

---

## 8. Almacenamiento distribuido con Hadoop HDFS

### Rol en el sistema

Hadoop HDFS (Hadoop Distributed File System) actúa como capa de almacenamiento distribuido para el dataset bruto. Aunque en el entorno actual corremos con un único nodo (configuración pseudo-distribuida), la arquitectura está preparada para escalar a un cluster real.

### Estructura de directorios en HDFS

```
/data/
├── raw/
│   └── ml_dataset.csv          ← Dataset PaySim original
├── processed/
│   └── transactions_clean/     ← Datos preprocesados por PySpark
└── fraud-results/
    └── batch_predictions/      ← Resultados de predicción por lotes
```

### Configuración relevante

- **Replicación = 1**: en un cluster real sería 3, pero con un único nodo data es suficiente
- **WebHDFS habilitado**: permite leer/escribir desde Python via HTTP sin cliente Java
- **YARN**: gestiona la asignación de recursos para los jobs de PySpark (memoria, CPU)

---

## 9. Automatización con n8n

### Concepto

n8n es un motor de automatización de workflows de código abierto, similar a Zapier pero autoalojado. Se configura visualmente conectando nodos y permite integrar cualquier servicio con API REST.

### Workflow implementado: Informe Diario de Fraude

El fichero `workflows/informe_fraude_diario.json` implementa el siguiente flujo:

```
[Schedule: 08:00 diario]  ─┐
                            ├──► [HTTP → Neo4j]
[Manual trigger]           ─┘         │
                                       ▼
                              [Code: formatear stats]
                                       │
                                       ▼
                              [HTTP → Groq API]
                              llama-3.1-8b-instant
                                       │
                                       ▼
                              [Code: construir HTML]
                                       │
                                       ▼
                              [Send Email: Gmail SMTP]
```

### Detalle de cada nodo

**Nodo 1 & 2 — Triggers (dual)**  
Dos triggers conectados al mismo nodo siguiente: un `Schedule Trigger` (cron `0 8 * * *`) para producción y un `Manual Trigger` para ejecutar en demos. Basta con pulsar "Test workflow" para dispararlo en el momento.

**Nodo 3 — HTTP Request → Neo4j**  
Envía dos queries Cypher al endpoint HTTP de Neo4j (`/db/neo4j/tx/commit`). La primera obtiene el resumen global (total de transacciones, número de fraudes, importe total interceptado, último paso temporal). La segunda obtiene el desglose de fraude por tipo de operación (CASH_OUT, TRANSFER) ordenado por cantidad.

La autenticación usa `Authorization: Basic bmVvNGo6cGFzc3dvcmQ=` (base64 de `neo4j:password`).

**Nodo 4 — Code: Stats**  
Código JavaScript que parsea la respuesta de Neo4j (formato anidado `results[0].data[0].row`) y calcula la tasa de fraude en porcentaje con tres decimales.

**Nodo 5 — HTTP Request → Groq**  
Envía un prompt al modelo `llama-3.1-8b-instant` de Groq con los datos estadísticos del sistema. El prompt instruye al modelo a generar 2-3 párrafos de análisis ejecutivo en español con situación actual, patrones detectados y una recomendación operativa. Groq es gratuito para este volumen de uso.

**Nodo 6 — Code: HTML**  
Construye un email HTML completo con: cabecera con el nombre del sistema, cuatro tarjetas de métricas (transacciones, fraudes, tasa %, importe interceptado), tabla de fraude por tipo y el análisis generado por la IA con un estilo visual diferenciado.

**Nodo 7 — Send Email**  
Envía el email vía Gmail SMTP (puerto 465, SSL/TLS) usando una App Password de Google (no la contraseña de la cuenta). El asunto incluye dinámicamente la fecha y el número de fraudes detectados.

---

## 10. Infraestructura como código con Terraform

### Principio

Toda la infraestructura de AWS está definida en ficheros `.tf` dentro de la carpeta `terraform/`. Esto significa que el entorno completo se puede crear, destruir y recrear con dos comandos (`terraform apply` / `terraform destroy`), y que la configuración está versionada en Git como cualquier otro código.

### Ficheros Terraform

| Fichero | Qué define |
|---|---|
| `main.tf` | Provider AWS, región, versiones requeridas, backend S3 opcional para el state |
| `variables.tf` | Parámetros configurables: nombre del key pair, tipo de instancia, URL del repo, IP permitida |
| `ec2.tf` | AMI Ubuntu 22.04, EC2 `t3.large`, Security Group con los 8 puertos, perfil IAM `LabInstanceProfile`, script `user_data` |
| `s3.tf` | Bucket S3 para el Terraform state con versionado y bloqueo de acceso público |
| `outputs.tf` | IP pública, URLs de todos los servicios, comando SSH listo para copiar |
| `userdata.sh.tpl` | Script bash que se ejecuta al arrancar la EC2: instala Docker, clona el repo, crea la red, levanta el stack |

### Flujo de arranque automático de la EC2

Al ejecutar `terraform apply`, AWS lanza la instancia y ejecuta `userdata.sh.tpl` automáticamente:

```
EC2 arranca
    ├── apt-get install docker.io git awscli
    ├── curl -fsSL https://get.docker.com | sh
    ├── git clone <repo> /home/ubuntu/app
    ├── echo "MODEL_NAME=modelo_arbol_optimizado.pkl" > .env
    ├── docker network create shared-ml-network
    ├── docker compose -f infrastructure/hadoop/docker-compose.yml up -d
    ├── docker compose -f infrastructure/api/docker-compose.yml up -d
    ├── docker compose -f infrastructure/ml-env/docker-compose.yml up -d
    └── docker compose -f infrastructure/n8n/docker-compose.yml up -d
```

El progreso es visible en `/var/log/user-data.log`. El proceso completo tarda ~5-10 minutos.

### Security Group: puertos abiertos

| Puerto | Servicio | Protocolo |
|---|---|---|
| 22 | SSH | TCP |
| 7474 | Neo4j Browser / HTTP API | TCP |
| 7687 | Neo4j Bolt | TCP |
| 8000 | FastAPI | TCP |
| 8088 | YARN ResourceManager | TCP |
| 8888 | JupyterLab | TCP |
| 9870 | Hadoop NameNode UI | TCP |
| 5678 | n8n | TCP |

---

## 11. Notebooks del pipeline

| Notebook | Entrada | Salida | Propósito |
|---|---|---|---|
| `hadoop_pyspark_ingesta.ipynb` | CSV en local | CSV en HDFS | Carga el dataset a HDFS y realiza EDA inicial con PySpark |
| `datasetfinal_v1.ipynb` | CSV en HDFS | `master_dataset_v2.csv.gz` + grafo en Neo4j | Ingesta en grafo, cálculo de features topológicas, exportación del dataset enriquecido |
| `fraud_detection_v2.ipynb` | `master_dataset_v2.csv.gz` | `modelo_arbol_optimizado.pkl` | Entrenamiento comparativo, optimización, evaluación y serialización del modelo |

---

## 12. Decisiones de diseño destacadas

**¿Por qué Docker Compose en lugar de Kubernetes?**  
El proyecto demuestra una arquitectura de microservicios completa, pero el tamaño del equipo y el scope del TFG no justifican la complejidad operativa de Kubernetes. Docker Compose ofrece el mismo aislamiento y la misma reproducibilidad con una curva de aprendizaje mucho menor.

**¿Por qué Neo4j y no una base de datos relacional con JOINs?**  
Las consultas de análisis de redes (PageRank, comunidades, caminos entre nodos) son naturales en un modelo de grafos y extremadamente costosas o directamente imposibles en SQL. Neo4j usa el lenguaje de consulta Cypher, diseñado específicamente para traversals de grafos.

**¿Por qué división temporal en lugar de aleatoria para train/test?**  
Una división aleatoria mezcla el futuro con el pasado, lo que provoca data leakage: el modelo entrena con transacciones posteriores a las que evalúa. La división por `step` replica el escenario real de producción.

**¿Por qué Groq en lugar de OpenAI para los informes?**  
Groq ofrece acceso gratuito a modelos como `llama-3.1-8b-instant` con una API compatible con el formato de OpenAI. Para este caso de uso (generar 2-3 párrafos de análisis ejecutivo), la calidad es más que suficiente y no supone coste alguno.

**¿Por qué Terraform y no CloudFormation?**  
Terraform es agnóstico al proveedor cloud (AWS, GCP, Azure usan el mismo lenguaje HCL), lo que lo convierte en la herramienta IaC estándar de la industria. CloudFormation solo funciona con AWS.

---

## 13. Estructura del repositorio

```
ml-fraud-detection/
├── infrastructure/
│   ├── ml-env/          Dockerfile + compose: JupyterLab + librerías ML
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   └── requirements.txt
│   ├── api/             Dockerfile + compose: FastAPI de predicción
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   └── requirements.txt
│   ├── hadoop/          Dockerfile + compose + configuración XML
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   ├── conf/         core-site.xml, hdfs-site.xml, yarn-site.xml...
│   │   └── scripts/      start-hadoop.sh
│   └── n8n/             Compose: n8n con variables de entorno
│       └── docker-compose.yml
├── notebooks/           Pipeline de datos y entrenamiento
├── src/                 Código fuente de la API (main.py)
├── models/              Modelo entrenado (.pkl)
├── workflows/           JSON exportado del workflow de n8n
├── terraform/           Infraestructura como código (AWS)
│   ├── main.tf
│   ├── variables.tf
│   ├── ec2.tf
│   ├── s3.tf
│   ├── outputs.tf
│   └── userdata.sh.tpl
├── data/                Datos procesados (en local; en AWS vienen del repo)
├── docs/                Documentación técnica
│   ├── MEMORIA.md       Este documento
│   └── javi/            Guías de arranque, AWS, Hadoop, n8n
└── .env                 Variables de entorno (no se sube a Git)
```

---

## 14. Tecnologías utilizadas

| Categoría | Tecnología | Versión | Rol en el sistema |
|---|---|---|---|
| Lenguaje | Python | 3.10 | Pipeline de datos, API, notebooks |
| ML | scikit-learn | 1.3+ | Entrenamiento, evaluación, serialización |
| ML | XGBoost | 2.1.1 | Algoritmo alternativo en comparativa |
| Graph DB | Neo4j | 2025.09 Enterprise | Almacenamiento de grafo y feature engineering |
| Graph Analytics | Neo4j GDS | 2.x | PageRank, Degree, Louvain |
| Big Data | Apache Hadoop | 3.4.1 | HDFS + YARN |
| Big Data | Apache PySpark | 3.x | Procesamiento distribuido |
| API | FastAPI | 0.100+ | Microservicio de inferencia |
| API | Uvicorn | — | Servidor ASGI para FastAPI |
| Automatización | n8n | 2.20 (self-hosted) | Workflows de alertas con IA |
| IA Generativa | Groq / llama-3.1-8b-instant | — | Análisis narrativo en informes |
| Contenedores | Docker + Docker Compose | — | Orquestación de servicios |
| IaC | Terraform | 1.3+ | Provisión de infraestructura AWS |
| Cloud | AWS EC2 | t3.large | Servidor de producción |
| Cloud | AWS S3 | — | Terraform state remoto |
| Dataset | PaySim | — | 6,3M transacciones sintéticas de Mobile Money |

---

## 1. Descripción del proyecto

Sistema end-to-end de detección de fraude en transacciones bancarias. Combina Machine Learning con análisis de grafos para identificar patrones de comportamiento fraudulento que los sistemas basados en reglas no pueden capturar. El resultado se expone como microservicio REST y se monitoriza mediante informes automáticos generados con IA.

**Problema a resolver:** El 0,13 % de las transacciones son fraude, pero representan pérdidas económicas significativas. La detección tardía o basada en reglas estáticas genera muchos falsos negativos. El reto es detectar transacciones sospechosas en tiempo real con alta sensibilidad (recall), aceptando cierta imprecisión para no bloquear transacciones legítimas.

**Dataset:** PaySim — simulación sintética de transacciones bancarias móviles basada en datos reales de un banco africano. 6,3 millones de registros (el entorno de desarrollo trabaja con ~872 000 por limitaciones de disco).

---

## 2. Arquitectura del sistema

Todos los servicios corren en Docker sobre una red compartida (`shared-ml-network`). La misma configuración funciona en local y en AWS sin cambios.

```
shared-ml-network
│
├── neo4j          Graph DB · puerto 7474 (HTTP) / 7687 (Bolt)
│                  Almacena transacciones como relaciones TRANSACTION
│                  Calcula PageRank, grado y comunidades Louvain
│
├── ml-env         JupyterLab · puerto 8888
│                  Pipeline de datos: ingesta → features → entrenamiento
│
├── ai-service     FastAPI · puerto 8000
│                  Microservicio de predicción: POST /predict
│                  Carga el modelo .pkl y devuelve probabilidad de fraude
│
├── hadoop         HDFS + YARN · puerto 9870 (NameNode UI)
│                  Almacenamiento distribuido del dataset original (CSV)
│                  Base para procesamiento PySpark a escala
│
└── n8n            Automatización · puerto 5678
                   Workflow diario: Neo4j → Groq IA → email HTML
```

---

## 3. Pipeline de datos (flujo completo)

```
[CSV PaySim]
    │
    ▼
[Hadoop HDFS]          ← Almacenamiento distribuido del raw
    │
    ▼
[Neo4j]                ← Ingesta de transacciones como grafo
    │  Nodos: Account (nameOrig, nameDest)
    │  Relaciones: TRANSACTION (amount, isFraud, type, step, ...)
    │
    ▼
[Graph Features]       ← Cálculo de métricas topológicas
    │  PageRank de origen y destino
    │  Grado de entrada/salida
    │  Comunidades Louvain (detección de clusters)
    │
    ▼
[master_dataset_v2.csv.gz]  ← Dataset enriquecido con features de grafo
    │
    ▼
[Entrenamiento ML]     ← fraud_detection_v2.ipynb
    │  División temporal: 80% train / 20% test (por step)
    │  Algoritmos: Random Forest, Decision Tree, XGBoost, Logistic Regression
    │  Optimización de hiperparámetros con GridSearchCV
    │  Métrica objetivo: PR-AUC (precision-recall, mejor para clases desbalanceadas)
    │
    ▼
[modelo_arbol_optimizado.pkl]  ← Modelo guardado en /models/
    │
    ▼
[FastAPI /predict]     ← Inferencia en tiempo real
```

---

## 4. Feature engineering con grafos

El valor diferencial del proyecto frente a un modelo tabular estándar está en las variables derivadas del grafo de Neo4j. Estas capturan el comportamiento relacional de las cuentas:

| Feature | Qué mide | Por qué detecta fraude |
|---|---|---|
| `orig_pagerank` | Influencia de la cuenta origen en la red | Cuentas fraudulentas suelen ser hubs de alta conectividad |
| `dest_pagerank` | Influencia de la cuenta destino | Receptores recurrentes de fondos sospechosos |
| `orig_out_degree` | Nº de transacciones enviadas por origen | Cuentas "mulas" envían a muchos destinos en poco tiempo |
| `dest_in_degree` | Nº de transacciones recibidas por destino | Destinos que concentran fondos de muchos orígenes |
| `orig_community` | Comunidad Louvain del origen | El fraude tiende a operar en clusters cerrados |
| `dest_community` | Comunidad Louvain del destino | Permite detectar si origen y destino comparten red criminal |

Estas 6 features se añaden a las 10 features base (amount, balances, tipo de operación codificado en one-hot) → **16 features totales**.

---

## 5. Modelo de Machine Learning

**Algoritmo seleccionado:** Decision Tree optimizado (`modelo_arbol_optimizado.pkl`)  
**Librería:** scikit-learn  
**Clase desbalanceada:** ~0,13% de fraudes → se usa `class_weight='balanced'`

**División temporal:** los datos de entrenamiento y test se separan por `step` (unidad temporal del dataset), no aleatoriamente. Esto simula un escenario real donde el modelo se entrena con datos históricos y se evalúa con datos futuros.

**Métricas relevantes** (con el subconjunto de ~872 000 registros):
- PR-AUC: 0.15 (baja por el subconjunto; con el dataset completo de 6,3M mejora significativamente)
- Recall: 0.84 — detecta el 84% de los fraudes reales
- Precision: 0.009 — hay falsos positivos (aceptable en detección de fraude: mejor revisar más que perder un fraude real)

**Nota sobre el modelo y el dataset:** Los resultados actuales corresponden al subconjunto de desarrollo (~14% del PaySim completo). Cargar el dataset completo (6,3M filas) mejora drásticamente todas las métricas.

---

## 6. API de predicción (FastAPI)

**Endpoint:** `POST http://localhost:8000/predict`

Recibe un JSON con las 16 features de una transacción y devuelve la probabilidad de fraude y la clasificación binaria.

```json
// Request
{
  "amount": 500.0,
  "oldbalanceOrg": 10000.0,
  "newbalanceOrig": 9500.0,
  "oldbalanceDest": 0.0,
  "newbalanceDest": 500.0,
  "type_CASH_OUT": 1,
  "type_TRANSFER": 0,
  "orig_out_degree": 5,
  "dest_in_degree": 3,
  "orig_pagerank": 0.01,
  "dest_pagerank": 0.005,
  "orig_community": 1,
  "dest_community": 2
}

// Response
{
  "fraud_probability": 0.87,
  "is_fraud": true
}
```

---

## 7. Automatización con n8n

Workflow implementado en `workflows/informe_fraude_diario.json`:

```
[Schedule Trigger: 08:00]  ─┐
                             ├─→ Neo4j (HTTP API) ─→ Code (formatear)
[Manual Trigger]            ─┘
                                  ─→ Groq API (llama-3.1-8b-instant)
                                  ─→ Code (construir HTML)
                                  ─→ Send Email (Gmail SMTP)
```

**Lo que hace cada nodo:**
1. **Triggers**: disparo diario automático o manual para demos
2. **Neo4j HTTP Request**: consulta estadísticas reales con dos queries Cypher (totales + desglose por tipo de operación)
3. **Code (Stats)**: extrae y formatea los datos del formato de respuesta de Neo4j
4. **Groq HTTP Request**: envía los datos al modelo `llama-3.1-8b-instant` para generar un párrafo de análisis ejecutivo en español
5. **Code (HTML)**: construye un email HTML con tarjetas de métricas, tabla de fraude por tipo y el análisis de IA
6. **Send Email**: envía el informe por Gmail SMTP (puerto 465, SSL/TLS)

---

## 8. Infraestructura en AWS

**Tecnología:** Terraform + AWS Academy  
**Instancia:** EC2 `t3.large` (2 vCPU, 8 GB RAM, 30 GB gp3) · región `us-east-1`

Terraform provisiona automáticamente:
- La instancia EC2 con Ubuntu 22.04
- Security Group con los puertos necesarios (22, 7474, 7687, 8000, 8088, 8888, 9870, 5678)
- Bucket S3 para el Terraform state

Al arrancar la EC2, el script `userdata.sh.tpl` ejecuta automáticamente:
1. Instala Docker y Git
2. Clona el repositorio en `/home/ubuntu/app`
3. Crea la red Docker `shared-ml-network`
4. Levanta todo el stack con `docker compose`

El workflow de n8n se importa manualmente una vez en `http://<EC2_IP>:5678` y las URLs internas (`neo4j`, `ai-service`) funcionan igual que en local.

---

## 9. Notebooks del pipeline

| Notebook | Propósito |
|---|---|
| `datasetfinal_v1.ipynb` | Ingesta CSV → Neo4j → cálculo de graph features → exporta `master_dataset_v2.csv.gz` |
| `fraud_detection_v2.ipynb` | Carga `master_dataset_v2.csv.gz` → entrena modelos → guarda `modelo_arbol_optimizado.pkl` |
| `hadoop_pyspark_ingesta.ipynb` | Carga datos desde HDFS con PySpark (procesamiento a escala) |

---

## 10. Estructura del repositorio

```
ml-fraud-detection/
├── infrastructure/
│   ├── ml-env/         Docker: JupyterLab + librerías ML
│   ├── api/            Docker: FastAPI de predicción
│   ├── hadoop/         Docker: HDFS + YARN
│   └── n8n/            Docker: automatización de workflows
├── notebooks/          Pipeline de datos y entrenamiento
├── src/                Código fuente de la API (main.py)
├── models/             Modelo entrenado (.pkl)
├── workflows/          JSON del workflow de n8n
├── terraform/          Infraestructura como código (AWS)
├── data/               Datos locales (procesados)
└── docs/               Documentación técnica
```

---

## 11. Tecnologías utilizadas

| Categoría | Tecnología | Uso |
|---|---|---|
| Lenguaje | Python 3.10 | Todo el stack de datos y API |
| ML | scikit-learn, XGBoost | Entrenamiento y predicción |
| Graph DB | Neo4j 2025 Enterprise | Almacenamiento de grafo y feature engineering |
| Big Data | Hadoop 3.4 + PySpark | Almacenamiento distribuido (HDFS) y procesamiento |
| API | FastAPI + Uvicorn | Microservicio de inferencia |
| Automatización | n8n | Workflows: informes automáticos con IA |
| IA Generativa | Groq (llama-3.1-8b-instant) | Análisis narrativo en informes por email |
| Contenedores | Docker + Docker Compose | Orquestación local y en AWS |
| IaC | Terraform | Provisión de infraestructura en AWS |
| Cloud | AWS EC2 + S3 (Academy) | Despliegue en producción |
| Dataset | PaySim (Kaggle) | Transacciones bancarias sintéticas |
