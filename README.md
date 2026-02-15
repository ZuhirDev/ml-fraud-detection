# 🛡️ Sistema Inteligente de Detección de Fraude

> **Objetivo Principal:** Desarrollar y desplegar un sistema de detección de fraude basado en **Machine Learning**, integrado en una arquitectura de **Big Data** escalable en la nube, capaz de procesar volúmenes masivos de datos en tiempo real.

---

## 1. 🎯 Definición del problema y objetivos

El fraude financiero digital evoluciona a una velocidad que los sistemas basados en reglas no pueden seguir. El reto técnico reside en procesar volúmenes masivos de datos y detectar patrones sutiles en milisegundos para evitar pérdidas económicas sin bloquear transacciones legítimas.

### Objetivos Específicos:
* 🗄️ **Almacenamiento:** Implementar un almacenamiento distribuido para datos masivos.
* ⚙️ **Data Pipeline:** Diseñar un pipeline de preprocesamiento y transformación de los datos.
* 🧠 **Machine Learning:** Entrenar un modelo predictivo con alta capacidad de discriminación en clases desbalanceadas.
* ⚡ **Automatización:** Orquestar una respuesta automatizada mediante `n8n` que actúe inmediatamente tras la detección de un riesgo elevado.
* 🚀 **Despliegue:** Desplegar un microservicio (API) en la nube que permita la consulta en tiempo real.

---

## 2. 🔬 Exploración del estado del arte y alcance

El proyecto se sitúa en el uso de aprendizaje supervisado para la clasificación binaria. Se utilizarán técnicas de procesamiento distribuido para manejar la carga que requieren los datasets de millones de registros.

El proyecto cubre el **ciclo de vida completo del dato**: 
1. Ingesta en un sistema de archivos distribuido (`HDFS`).
2. Procesamiento masivo (`PySpark` / `Pandas`).
3. Análisis de conexiones espaciales (`Neo4j`).
4. Entrenamiento del modelo predictivo.
5. Puesta en producción como microservicio en `AWS`.



---

## 3. 📅 Planificación del desarrollo

| Fase | Etapa | Descripción Técnica |
| :---: | :--- | :--- |
| **1** | **Infraestructura y Almacenamiento** | Despliegue de instancias en AWS, configuración de HDFS para la persistencia del dataset original y configuración del motor de grafos Neo4j. |
| **2** | **Ingesta y ETL Distribuido** | Lectura de datos desde HDFS mediante PySpark para realizar la limpieza y filtrado inicial a gran escala. |
| **3** | **Análisis y Preprocesamiento** | Transformación de los datos (limpieza, normalización, codificación) procesados utilizando Pandas para la preparación final del set de entrenamiento. |
| **4** | **Entrenamiento y Optimización** | Experimentación con diversos algoritmos, manejo del desbalanceo de clases y ajuste de hiperparámetros. |
| **5** | **Despliegue del Microservicio** | Creación de una API con FastAPI, configuración de n8n y despliegue en instancias EC2, permitiendo la validación externa. |

---

## 4. 🛠️ Herramientas y tecnologías a utilizar

| Categoría | Tecnologías | Propósito en la Arquitectura |
| :--- | :--- | :--- |
| ☁️ **Infraestructura Cloud** | `AWS (EC2)` | Cómputo y servicios de almacenamiento escalable. |
| 🐘 **Ecosistema Big Data** | `HDFS`, `PySpark` | Almacenamiento de datos y lectura/preprocesamiento distribuido. |
| 🕸️ **Base de Datos Grafos** | `Neo4j` | Detección de transacciones, blanqueo de capitales y redes de fraude. |
| 🧠 **Inteligencia Artificial** | `Python`, `Scikit-learn`, `Pandas` | Análisis numérico y desarrollo del modelo predictivo. |
| 🔌 **Despliegue (API)** | `FastAPI` | Interfaz de microservicio para predicciones en tiempo real. |
| 🔄 **Automatización** | `n8n` | Orquestador de alertas y respuestas ante el fraude. |

---

## 5. 📊 Fuentes de datos previstas

* **Dataset Principal:** Dataset sintético de transacciones financieras.
* **Volumen:** `6.3 Millones de registros`.
* **Justificación:** Permite simular un entorno de producción de Big Data real y trabajar la escalabilidad de las herramientas propuestas frente a un problema de clases altamente desbalanceadas.

---

## 🧑‍💻 Autores

- [@Poempollo](https://github.com/Poempollo)
- [@ZuhirDev](https://github.com/ZuhirDev)
