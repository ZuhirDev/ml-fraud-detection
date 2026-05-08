# 🛡️ Sistema Inteligente de Detección de Fraude Bancario
**Basado en Machine Learning y Análisis de Grafos (Neo4j)**

## 1. Contexto del Proyecto
El objetivo es detectar transacciones fraudulentas en un entorno bancario altamente desbalanceado (0.1% de fraude). A diferencia de los métodos tradicionales que solo analizan el importe o la fecha, este proyecto utiliza la **topología de la red** para identificar patrones de blanqueo y estructuras criminales mediante el uso de bases de datos de grafos.

---

## 2. Feature Engineering: El Poder de los Grafos
Para mejorar la capacidad de detección, se integró **Neo4j** para calcular métricas que un modelo tabular estándar no podría ver. Estas variables capturan el comportamiento relacional de los usuarios:

* **PageRank (`orig_pagerank`, `dest_pagerank`)**: Mide la importancia o influencia de una cuenta dentro de la red de transacciones.
* **Degree (`orig_out_degree`, `dest_in_degree`)**: Identifica cuentas que actúan como "hubs" (muchas transacciones entrantes o salientes en poco tiempo).
* **Louvain Community Detection (`orig_community`, `dest_community`)**: Agrupa usuarios en comunidades. El fraude suele concentrarse en círculos cerrados de cuentas sintéticas o "mulas".

---

## 3. Preprocesamiento y Limpieza
El pipeline de datos asegura que la información sea digerible para el algoritmo:

* **One-Hot Encoding**: Transformación de la variable categórica `type` en columnas binarias (CASH_OUT, TRANSFER, etc.).
* **Limpieza de Datos**: Tratamiento de registros con saldos inconsistentes.
* **Escalado Robusto (`StandardScaler`)**: Normalización de las 16 variables finales para asegurar que las métricas financieras y las de grafos operen en la misma escala jerárquica.

---
