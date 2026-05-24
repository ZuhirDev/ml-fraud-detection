# Docker — Documentación del Sistema de Contenedores

> TFG: Sistema de Detección de Fraude Bancario  
> Tecnologías: Docker Engine · Docker Compose · Docker Networks · Volumes

---

## 1. ¿Qué es Docker y por qué lo usamos?

Docker es una plataforma de contenedores que permite empaquetar una aplicación junto con todas sus dependencias (librerías, configuración, sistema operativo base) en una unidad llamada **contenedor**. Un contenedor se ejecuta de forma aislada del sistema operativo anfitrión y produce el mismo resultado en cualquier máquina donde Docker esté instalado.

### ¿Por qué Docker en este proyecto?

El sistema tiene 5 servicios que requieren entornos muy distintos:
- Neo4j necesita Java 17 y configuración de JVM
- Hadoop necesita Java 8/11 y los binarios de Hadoop
- JupyterLab necesita Python con decenas de librerías ML
- FastAPI necesita Python con librerías específicas y el modelo serializado
- n8n necesita Node.js

Sin Docker, instalar y configurar todo esto en la misma máquina generaría conflictos de versiones y haría el proyecto difícil de reproducir. Con Docker, cada servicio tiene su propio entorno aislado y arranca con un solo comando.

**Ventaja clave:** el mismo `docker-compose.yml` funciona en el portátil de desarrollo y en la EC2 de AWS sin ningún cambio.

---

## 2. Conceptos fundamentales aplicados al proyecto

### Imagen vs Contenedor
- **Imagen**: plantilla de solo lectura que define el entorno. Ejemplo: `neo4j:2025.09.0-enterprise`
- **Contenedor**: instancia en ejecución de una imagen. Tiene estado (puede escribir datos), tiene una IP dentro de la red Docker

### Dockerfile
Fichero de instrucciones para construir una imagen personalizada. Ejemplo de `infrastructure/api/Dockerfile`:
```dockerfile
FROM python:3.10-slim          # imagen base oficial de Python
WORKDIR /app                   # directorio de trabajo dentro del contenedor
COPY requirements.txt .        # copiar solo requirements primero (caché)
RUN pip install -r requirements.txt   # instalar dependencias
COPY . .                       # copiar el resto del código
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose
Herramienta para definir y ejecutar múltiples contenedores a la vez mediante un fichero YAML (`docker-compose.yml`). Define qué imagen usar, qué puertos exponer, qué red usar y qué volúmenes montar.

### Red Docker (Networks)
Los contenedores en la misma red pueden comunicarse por nombre de contenedor. En este proyecto todos los servicios comparten `shared-ml-network`, lo que permite que `ml-env` llame a `neo4j:7687` directamente sin conocer la IP.

### Volúmenes (Volumes)
Mecanismo para persistir datos fuera del ciclo de vida del contenedor. Si un contenedor se destruye y se vuelve a crear, los datos del volumen siguen ahí.

---

## 3. Red compartida: `shared-ml-network`

Todos los servicios del proyecto están en la misma red bridge llamada `shared-ml-network`. Esta red es **externa** (creada manualmente una vez) para que varios `docker-compose.yml` independientes puedan compartirla.

```bash
# Crear la red (solo la primera vez, en cualquier máquina o en el user_data de AWS)
docker network create shared-ml-network
```

### ¿Por qué una sola red para todos?

Permite que servicios definidos en **diferentes** `docker-compose.yml` se vean entre sí. Si cada servicio tuviese su propia red, `ml-env` no podría resolver `neo4j` ni `ai-service`.

### Resolución de nombres dentro de la red

| Desde | Llama a | URL |
|---|---|---|
| `ml-env` | Neo4j (Bolt) | `bolt://neo4j:7687` |
| `ml-env` | FastAPI | `http://ai-service:8000/predict` |
| `ml-env` | Hadoop HDFS | `hdfs://hadoop:9000` |
| `n8n` | Neo4j (HTTP) | `http://neo4j:7474/db/neo4j/tx/commit` |
| `n8n` | FastAPI | `http://ai-service:8000/predict` |
| `ai-service` | Neo4j (Bolt) | `bolt://neo4j:7687` |

Desde el **navegador del host** (tu PC o la EC2) se usa `localhost` en lugar del nombre del servicio.

---

## 4. Servicios: Dockerfiles y configuración

### 4.1 — ml-env (JupyterLab + entorno ML)

**Ruta:** `infrastructure/ml-env/`  
**Puerto:** 8888

Imagen basada en `jupyter/scipy-notebook` con librerías adicionales de ML y el driver de Neo4j. Es el entorno donde se ejecutan los notebooks del pipeline de datos y entrenamiento.

```yaml
# infrastructure/ml-env/docker-compose.yml (extracto)
services:
  ml-env:
    build: .
    container_name: ml-env
    ports:
      - "8888:8888"
    volumes:
      - ../../notebooks:/home/jovyan/notebooks  # notebooks del proyecto
      - ../../models:/home/jovyan/models         # modelo .pkl compartido con api
      - ../../data:/home/jovyan/data
    networks:
      - shared-ml-network
```

**Volúmenes montados:**
- `notebooks/` → `/home/jovyan/notebooks` — los notebooks del repo son accesibles en Jupyter
- `models/` → `/home/jovyan/models` — el modelo entrenado se guarda aquí y la API lo lee del mismo volumen

### 4.2 — ai-service (FastAPI)

**Ruta:** `infrastructure/api/`  
**Puerto:** 8000

Microservicio de predicción que carga el modelo al arrancar. Imagen construida desde `Dockerfile` sobre `python:3.10-slim`.

```yaml
services:
  ai-service:
    build: .
    container_name: ai-service
    ports:
      - "8000:8000"
    volumes:
      - ../../models:/app/models    # lee el modelo .pkl del volumen compartido
      - ../../src:/app/src
    env_file:
      - ../../.env                  # MODEL_NAME, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    networks:
      - shared-ml-network
```

**Variables de entorno relevantes** (desde `.env`):
```env
MODEL_NAME=modelo_arbol_optimizado.pkl
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### 4.3 — neo4j (Base de datos de grafos)

**Ruta:** `infrastructure/ml-env/docker-compose.yml` (junto con ml-env, ya que Neo4j es del stack de ML)  
**Puertos:** 7474 (HTTP Browser), 7687 (Bolt)

Usa la imagen oficial `neo4j:2025.09.0-enterprise`. Los datos se persisten en el volumen `data-neo/` del repositorio (carpeta local).

```yaml
services:
  neo4j:
    image: neo4j:2025.09.0-enterprise
    container_name: neo4j
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password
      - NEO4J_PLUGINS=["graph-data-science"]   # habilita GDS (PageRank, Louvain...)
      - NEO4J_ACCEPT_LICENSE_AGREEMENT=yes
    volumes:
      - ../../data-neo:/data    # persistencia de los datos del grafo
    networks:
      - shared-ml-network
```

**Por qué Enterprise:** la versión Community no incluye el plugin Graph Data Science (GDS), que es necesario para calcular PageRank y Louvain. La versión Enterprise es gratuita para uso educativo.

### 4.4 — hadoop (HDFS + YARN)

**Ruta:** `infrastructure/hadoop/`  
**Puertos:** 9870 (NameNode UI), 9000 (HDFS RPC), 8088 (YARN), 8042 (NodeManager)

Imagen construida desde `apache/hadoop:3.4.1` con PySpark añadido. El script `start-hadoop.sh` formatea el NameNode la primera vez y arranca todos los daemons (NameNode, DataNode, ResourceManager, NodeManager).

```yaml
services:
  hadoop:
    build: .
    container_name: hadoop
    hostname: hadoop
    ports:
      - "9870:9870"
      - "9000:9000"
      - "8088:8088"
      - "8042:8042"
    volumes:
      - hadoop_namenode:/opt/hadoop/data/nameNode
      - hadoop_datanode:/opt/hadoop/data/dataNode
    networks:
      - shared-ml-network
    healthcheck:
      test: ["CMD", "hdfs", "dfs", "-ls", "/"]
      interval: 30s
      retries: 5
```

**Ficheros de configuración en `conf/`:**
- `core-site.xml` — define `fs.defaultFS=hdfs://hadoop:9000`
- `hdfs-site.xml` — replicación=1 (single node), habilita WebHDFS
- `yarn-site.xml` — ResourceManager y NodeManager
- `mapred-site.xml` — framework MapReduce sobre YARN

### 4.5 — n8n (Automatización)

**Ruta:** `infrastructure/n8n/`  
**Puerto:** 5678

Usa la imagen oficial `n8nio/n8n:latest`. Los workflows y credenciales se persisten en el volumen `n8n_data`.

```yaml
services:
  n8n:
    image: n8nio/n8n:latest
    container_name: n8n
    ports:
      - "5678:5678"
    environment:
      - N8N_SECURE_COOKIE=false      # necesario para HTTP (sin HTTPS)
      - N8N_ENCRYPTION_KEY=fraud-detection-n8n-secret-key-2024
    volumes:
      - n8n_data:/home/node/.n8n     # persistencia de workflows y credenciales
    networks:
      - shared-ml-network
```

---

## 5. Volúmenes: persistencia de datos

| Volumen | Servicio | Qué guarda | Dónde en disco |
|---|---|---|---|
| `../../data-neo` (bind mount) | neo4j | Grafo completo de transacciones | `data-neo/` en el repo |
| `../../models` (bind mount) | ml-env, ai-service | Modelo .pkl entrenado | `models/` en el repo |
| `hadoop_namenode` (named) | hadoop | Metadatos HDFS (estructura de directorios) | Gestionado por Docker |
| `hadoop_datanode` (named) | hadoop | Bloques de datos reales | Gestionado por Docker |
| `n8n_data` (named) | n8n | Workflows, credenciales cifradas | Gestionado por Docker |

**Diferencia entre bind mount y named volume:**
- **Bind mount** (`../../models`): apunta a una carpeta del host. Se puede acceder desde el explorador de archivos del PC. Útil para datos que quieres editar desde fuera del contenedor.
- **Named volume** (`n8n_data`): gestionado internamente por Docker. No es fácilmente accesible desde el host, pero tiene mejor rendimiento y portabilidad.

---

## 6. Arranque del stack completo

```bash
# Prerrequisito (solo la primera vez):
docker network create shared-ml-network

# Levantar en este orden (hadoop necesita estar antes que los que usan HDFS):
docker compose -f infrastructure/ml-env/docker-compose.yml up -d
docker compose -f infrastructure/api/docker-compose.yml    up -d
docker compose -f infrastructure/hadoop/docker-compose.yml up -d
docker compose -f infrastructure/n8n/docker-compose.yml    up -d
```

### Verificar que todo está bien

```bash
# Ver todos los contenedores y su estado
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Resultado esperado:
# NAMES        STATUS           PORTS
# n8n          Up               0.0.0.0:5678->5678/tcp
# hadoop       Up (healthy)     0.0.0.0:9870->9870/tcp, ...
# ai-service   Up               0.0.0.0:8000->8000/tcp
# neo4j        Up               0.0.0.0:7474->7474/tcp, 7687->7687/tcp
# ml-env       Up               0.0.0.0:8888->8888/tcp
```

---

## 7. Comandos de referencia

### Gestión de contenedores

```bash
# Parar todos los servicios (sin borrar datos):
docker compose -f infrastructure/ml-env/docker-compose.yml  stop
docker compose -f infrastructure/api/docker-compose.yml     stop
docker compose -f infrastructure/hadoop/docker-compose.yml  stop
docker compose -f infrastructure/n8n/docker-compose.yml     stop

# Borrar contenedores (datos persisten en volúmenes):
docker compose -f infrastructure/ml-env/docker-compose.yml  down
docker compose -f infrastructure/hadoop/docker-compose.yml  down

# Borrar contenedores Y volúmenes (⚠️ se pierden los datos de HDFS/Neo4j):
docker compose -f infrastructure/hadoop/docker-compose.yml  down -v
```

### Inspección y debug

```bash
# Ver logs de un servicio en tiempo real:
docker logs neo4j --follow
docker logs hadoop --tail 50

# Entrar en un contenedor con bash:
docker exec -it neo4j bash
docker exec -it ml-env bash

# Ver uso de recursos:
docker stats

# Ver redes:
docker network ls
docker network inspect shared-ml-network

# Ver volúmenes:
docker volume ls
docker volume inspect n8n_data
```

### Rebuild tras cambios en código

```bash
# Si modificas el Dockerfile o requirements.txt:
docker compose -f infrastructure/api/docker-compose.yml up -d --build

# Forzar rebuild desde cero (sin caché):
docker compose -f infrastructure/api/docker-compose.yml build --no-cache
docker compose -f infrastructure/api/docker-compose.yml up -d
```

---

## 8. Solución de problemas frecuentes

### "network shared-ml-network not found"
La red no existe. Créala:
```bash
docker network create shared-ml-network
```

### "port is already allocated"
El puerto ya lo usa otro proceso. Ver cuál:
```bash
netstat -ano | findstr :8000   # Windows
lsof -i :8000                  # Linux/Mac
```

### Neo4j no arranca / "Authentication failed"
El volumen `data-neo/` tiene datos de una sesión anterior con diferente contraseña. Borrar el volumen:
```bash
# Parar neo4j primero:
docker compose -f infrastructure/ml-env/docker-compose.yml down
# Borrar los datos (⚠️ se pierde el grafo):
Remove-Item -Recurse -Force data-neo\  # Windows PowerShell
# Volver a arrancar:
docker compose -f infrastructure/ml-env/docker-compose.yml up -d
```

### Hadoop arranca pero HDFS no responde
El NameNode puede tardar 30-60 segundos en inicializar. Esperar y comprobar:
```bash
docker logs hadoop --tail 30
# Buscar: "NameNode: entering safemode" → "leaving safemode"
```

### Contenedor reiniciándose en bucle
```bash
docker logs <nombre_contenedor> --tail 50
# El error suele estar en las últimas líneas
```
