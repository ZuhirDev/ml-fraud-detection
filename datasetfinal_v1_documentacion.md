# Documentación del proceso de generación del dataset final

## 1. Objetivo

Este documento describe de forma profesional y detallada el proceso seguido en el cuaderno `notebooks/datasetfinal_v1.ipynb` para generar el dataset final que se utilizará en el entrenamiento del modelo de detección de fraude.

El flujo se centra en:
- Ingestar los datos originales de PaySim en Neo4j.
- Enriquecer las transacciones con características de grafo y temporales.
- Exportar un dataset final consolidado en formato CSV comprimido.

## 2. Contexto y alcance

El cuaderno trabaja con un dataset raw en `data/raw/ml_dataset.csv` y utiliza Neo4j como motor de grafos para:
- representar cuentas como nodos `Account`,
- transacciones como relaciones `TRANSACTION`,
- y derivar características que aportan señal para modelos de fraude.

El producto final es un archivo comprimido con las columnas originales más las nuevas características calculadas desde el grafo.

## 3. Dependencias y configuración

### 3.1 Librerías utilizadas

- `os` y `dotenv`: gestionar variables de entorno.
- `neo4j`: conexión y ejecución de consultas en Neo4j.
- `pandas`: lectura y manipulación del dataset raw.
- `time`: medición de tiempos de ejecución.
- `csv` y `gzip`: exportación comprimida de resultados.

### 3.2 Variables de entorno

El cuaderno carga variables de entorno desde la raíz del proyecto mediante `load_dotenv(find_dotenv())`.
Las variables esperadas son:
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`

Estas variables permiten establecer una conexión segura con Neo4j.

## 4. Flujo de trabajo detallado

### 4.1 Conexión a Neo4j

Se verifica la conectividad con Neo4j usando `GraphDatabase.driver(URI, auth=AUTH)`.
Esto asegura que el entorno está listo para ejecutar la ingesta y los cálculos de grafo.

### 4.2 Carga inicial del dataset raw

El dataset original se lee desde:
- `data/raw/ml_dataset.csv`

Se carga con `pandas.read_csv`, generando un DataFrame `df` que contiene las transacciones originales.

### 4.3 Ingesta optimizada en Neo4j

La función principal de ingesta es `ingestar_raw_data_optimizada(df, batch_size=50000)`.
El proceso sigue una estrategia por fases para evitar cuellos de botella y uso excesivo de memoria.

#### 4.3.1 Fase 0: restricciones e índices

Se crea de forma segura una restricción de unicidad para los nodos `Account`:

- `CREATE CONSTRAINT ACCOUNT_ID_UNIQUE IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE`

Esta restricción evita duplicados de cuenta y acelera las operaciones `MERGE`.

#### 4.3.2 Fase 1: carga de nodos `Account`

Se separa la ingestión de nodos en dos bloques:
- nodos origen (`nameOrig`)
- nodos destino (`nameDest`)

Para cada bloque, se:
- extraen IDs únicos desde el DataFrame,
- dividen en lotes de tamaño `batch_size`,
- ejecutan consultas `UNWIND $rows AS row MERGE (:Account {id: row.nameOrig})` o `row.nameDest`.

Esto evita enviar múltiples registros redundantes a Neo4j y reduce la contención de locks.

#### 4.3.3 Fase 2: creación de relaciones `TRANSACTION`

Se crean las relaciones en Neo4j por lotes, con la siguiente estructura:

- `orig` y `dest` referencian a nodos `Account` existentes.
- cada relación `TRANSACTION` almacena las columnas originales de PaySim.
- se usan conversiones explícitas: `toFloat`, `toInteger`.

Las relaciones incluyen atributos relevantes como:
- `amount`
- `type`
- `step`
- `oldbalanceOrg`, `newbalanceOrig`
- `oldbalanceDest`, `newbalanceDest`
- `isFraud`

Se procesa en lotes para mantener la ingestión controlada y escalable.

### 4.4 Verificación de los datos en Neo4j

La función `verificar_datos_neo4j()` comprueba que la ingesta fue exitosa mediante:
- conteo de nodos `Account`
- conteo de relaciones `TRANSACTION`
- revisión de ejemplos de transacciones cargadas

Este paso valida la integridad básica del grafo antes de continuar con el cálculo de características.

### 4.5 Cálculo de grados históricos con Point-in-Time

La función `calcular_grados_nativos_pit(batch_size=40000)` calcula dos características estructurales para cada transacción:
- `out_degree_hist`: número de transacciones salientes previas del origen
- `in_degree_hist`: número de transacciones entrantes previas del destino

Se utiliza un enfoque Point-in-Time estricto para evitar data leakage:
- solo se consideran transacciones con `step < t.step`
- se calcula cada relación `TRANSACTION` en su contexto histórico

La ejecución se realiza mediante `apoc.periodic.iterate`, lo que permite procesar millones de relaciones en lotes de forma eficiente.

### 4.6 Cálculo de PageRank temporal por bloques

La función `calcular_pagerank_temporal_bloques_produccion(uri, auth, tamaño_bloque=24)` implementa un pipeline temporal de PageRank:

1. Inicializa propiedades base en transacciones: `orig_pagerank_hist` y `dest_pagerank_hist`.
2. Para cada bloque de pasos históricos (`fin_bloque`):
   - proyecta el grafo desde `step <= fin_bloque`.
   - ejecuta `gds.pageRank.write` para obtener PageRank en ese momento histórico.
   - asigna el PageRank calculado como historizado a transacciones posteriores al bloque.
   - elimina la propiedad temporal `pagerank_temporal` de los nodos para mantener el grafo limpio.

Este procedimiento construye una representación temporal robusta del impacto de cada cuenta en el grafo histórico.

### 4.7 Cálculo de comunidades temporales con Louvain

La función `calcular_louvain_temporal_bloques_produccion(tamaño_bloque=24)` calcula características comunitarias en ventanas temporales:

1. Asegura un índice sobre `TRANSACTION(step)`.
2. Inicializa propiedades base en las transacciones:
   - `orig_louvain_size_hist`
   - `same_louvain_community_hist`
3. Para cada bloque histórico:
   - proyecta el grafo limitado a `step <= fin_bloque`.
   - ejecuta `gds.louvain.write` para detectar comunidades.
   - para las transacciones posteriores al bloque, establece:
     - `same_louvain_community_hist = 1` cuando origen y destino comparten comunidad
     - `0` en caso contrario
4. Limpia la propiedad temporal nodo `louvain_id_temp`.

Con esto se obtiene una característica de co-pertenencia comunitaria que refleja dinámica social entre cuentas.

### 4.8 Exportación del dataset final

Existen dos funciones para exportar el dataset final en CSV comprimido:
- `exportacion_absoluta_a_csv(archivo_salida="master_dataset.csv.gz")`
- `exportacion_absoluta_corregida_a_csv(archivo_salida="../data/processed/master_dataset_v2.csv.gz")`

Ambas extraen desde Neo4j todos los atributos originales y estructurales:

- `step`
- `nameOrig`, `nameDest`
- `type`, `amount`
- `oldbalanceOrg`, `newbalanceOrig`, `oldbalanceDest`, `newbalanceDest`
- `isFraud`, `isFlaggedFraud`
- `in_degree_hist`, `out_degree_hist`
- `orig_pagerank_hist`, `dest_pagerank_hist`
- `same_louvain_community_hist`

El dataset final resultante es un CSV comprimido con las columnas necesarias para construir el conjunto de entrenamiento del modelo.

## 5. Resultado esperado

El resultado de este proceso es un dataset tabular enriquecido con información de grafo histórico y temporal.

El archivo final recomendado es:
- `data/processed/master_dataset_v2.csv.gz`

Este dataset puede ser usado directamente para:
- entrenamiento de modelos supervisados de fraude,
- análisis exploratorio con variables estructurales,
- pruebas de calidad de datos y validación de características.

## 6. Recomendaciones y buenas prácticas

- Ejecutar primero la verificación de conectividad a Neo4j.
- Confirmar que el dataset raw `data/raw/ml_dataset.csv` está íntegro antes de la ingesta.
- Asegurarse de que Neo4j cuenta con memoria y configuraciones adecuadas para procesar más de 6 millones de relaciones.
- Ejecutar los cálculos de PageRank y Louvain por bloques en un entorno con suficientes recursos, ya que son operaciones costosas.
- Validar el dataset final exportado verificando el número de filas y la coherencia de los nuevos campos.

## 7. Conclusión

El cuaderno `datasetfinal_v1.ipynb` ofrece un pipeline completo para transformar el dataset raw de PaySim en un dataset final listo para entrenamiento.

Se dedica especial atención a:
- eficiencia de ingesta,
- integridad de datos,
- prevención de data leakage mediante cálculo Point-in-Time,
- enriquecimiento con métricas de grafo históricas y temporales.

Este documento sirve como guía clara y profesional para entender qué se hizo, cómo se hizo y cuál es el resultado final esperado.
