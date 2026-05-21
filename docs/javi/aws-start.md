# Guía de arranque AWS — TFG Detección de Fraude

> Dos escenarios: **A) Despliegue desde cero** (nueva EC2) y **B) Relanzar instancia existente** (la EC2 ya existe pero estaba parada).

---

## Requisitos previos (siempre)

- Fichero `.pem` del Key Pair en `C:\Users\Javi\.ssh\claves-ml.pem`
- Terraform instalado (`terraform -v`)
- Credenciales AWS Academy frescas (caducan cada ~4 h)

### Pegar credenciales en PowerShell

Cada vez que abras un terminal nuevo o caduquen las claves, ve a **AWS Academy → AWS Details → Show** y pega:

```powershell
$env:AWS_ACCESS_KEY_ID     = "ASIA..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_SESSION_TOKEN     = "..."
$env:AWS_DEFAULT_REGION    = "us-east-1"
```

---

## A) Despliegue desde cero (nueva EC2)

Usa este escenario si la instancia fue terminada (`terraform destroy`) o si es la primera vez.

### 1. Clonar el repo y preparar Terraform

```powershell
git clone https://github.com/ZuhirDev/ml-fraud-detection.git
cd ml-fraud-detection\terraform
```

Crear `terraform\terraform.tfvars` (ya está en `.gitignore`, no se sube):

```hcl
key_pair_name = "claves-ml"
repo_url      = "https://github.com/ZuhirDev/ml-fraud-detection.git"
```

### 2. Inicializar y desplegar

```powershell
terraform init
terraform apply   # confirmar con "yes"
```

Terraform imprime al terminar la IP pública y todas las URLs. Guarda la IP.

### 3. Monitorizar el arranque (~15-20 min primera vez)

```powershell
ssh -i "$env:USERPROFILE\.ssh\claves-ml.pem" ubuntu@<IP> "sudo tail -f /var/log/user-data.log"
```

Cuando veas `DONE — Stack levantado`, todos los contenedores están arriba.

### 4. Instalar Terraform en Debian/Linux (PC de clase)

```bash
wget https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip
unzip terraform_*.zip && sudo mv terraform /usr/local/bin/

# Credenciales en Linux/Mac (export en lugar de $env:):
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_DEFAULT_REGION="us-east-1"
```

---

## B) Relanzar instancia existente (la EC2 ya está creada)

Usa este escenario cuando el laboratorio se paró y se reinició, pero la EC2 sigue existiendo con otra IP pública.

### 1. Obtener la nueva IP

En la consola AWS → **EC2 → Instances → fraud-detection-server** → columna *Public IPv4 address*.  
O desde PowerShell (con credenciales activas):

```powershell
aws ec2 describe-instances --filters "Name=tag:Name,Values=fraud-detection-server" `
  --query "Reservations[].Instances[].PublicIpAddress" --output text
```

### 2. Conectar por SSH

```powershell
# Windows PowerShell:
ssh -i "$env:USERPROFILE\.ssh\claves-ml.pem" ubuntu@<IP>

# Linux/Mac:
ssh -i ~/.ssh/claves-ml.pem ubuntu@<IP>
```

Si da error de permisos en Windows:
```powershell
icacls "$env:USERPROFILE\.ssh\claves-ml.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

### 3. Ver qué contenedores están corriendo

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Con `restart: unless-stopped`, Hadoop y n8n suelen arrancar solos.  
Si falta alguno (normalmente `ml-env`, `neo4j`, `ai-service`), ve al paso 5.

### 4. Actualizar el código (git pull)

```bash
cd /home/ubuntu/app
git status
```

**Si hay conflictos o ficheros sin permisos** (el caso habitual con los checkpoints de Jupyter):

```bash
# Borrar el checkpoint que crea Jupyter como root (sin permiso para ubuntu)
sudo rm -rf notebooks/.ipynb_checkpoints/

# Descartar cualquier cambio local en tracked files
git reset --hard HEAD

# Limpiar ficheros no rastreados
git clean -fd

# Ahora sí, pull limpio
git pull
```

**Si el pull sigue fallando por `.env` modificado u otro fichero tracked:**

```bash
git checkout -- .env          # restaura solo el .env
git checkout -- <fichero>     # o cualquier otro fichero concreto
git pull
```

### 5. Arrancar los contenedores que falten

```bash
cd /home/ubuntu/app

# Red Docker (si no existe)
docker network create shared-ml-network 2>/dev/null || true

# Hadoop primero (necesita estar up antes que Spark)
cd infrastructure/hadoop
docker compose up -d
sleep 10

# API de predicción
cd ../api
docker compose up -d

# Jupyter + Neo4j (con env_file para que Neo4j reciba las variables)
cd ../ml-env
docker compose --env-file ../../.env up -d

# n8n
cd ../n8n
docker compose up -d

# Verificar
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Deberías ver 5 contenedores `Up`: `hadoop`, `ai-service`, `ml-env`, `neo4j`, `n8n`.

### 6. Recrear contenedores con config nueva (si has hecho pull de cambios)

Si el pull trajo cambios en algún `docker-compose.yml`, recrea solo el servicio afectado:

```bash
# Ejemplo: actualizar n8n y ml-env tras un cambio de compose
cd /home/ubuntu/app/infrastructure/n8n
docker compose down && docker compose up -d

cd ../ml-env
docker compose --env-file ../../.env down
docker compose --env-file ../../.env up -d
```

---

## URLs de los servicios

Sustituye `<IP>` por la IP pública actual de la EC2.

| Servicio | URL | Notas |
|---|---|---|
| FastAPI (Swagger) | `http://<IP>:8000/docs` | |
| FastAPI (health) | `http://<IP>:8000/health` | Debe devolver `{"status":"ok"}` |
| JupyterLab | `http://<IP>:8888` | Sin contraseña |
| Hadoop NameNode | `http://<IP>:9870` | Ver ficheros HDFS |
| YARN | `http://<IP>:8088` | Ver jobs Spark |
| Neo4j Browser | `http://<IP>:7474` | user: `neo4j` / pass: `password` |
| n8n | `http://<IP>:5678` | |

---

## Solución de problemas frecuentes

### n8n: "secure cookie" al abrir por HTTP

Ya está corregido en el compose (`N8N_SECURE_COOKIE=false`). Si persiste:
```bash
cd /home/ubuntu/app/infrastructure/n8n
docker compose down && docker compose up -d
```

### Neo4j: fallo de credenciales

El `.env` del proyecto raíz define `NEO4J_AUTH=neo4j/password`.  
Si Neo4j arrancó sin leerlo, recréalo:
```bash
cd /home/ubuntu/app/infrastructure/ml-env
docker compose --env-file ../../.env down
docker compose --env-file ../../.env up -d
```
Credenciales en el browser: usuario `neo4j`, contraseña `password`.

### Terraform: "No valid credential sources found"

Las credenciales de sesión AWS han caducado. Vuelve a AWS Academy → AWS Details y repega los `$env:` en el terminal de PowerShell.

### Key Pair desaparecido (lab reiniciado desde cero)

Si el laboratorio se reinició completamente, el Key Pair `claves-ml` ya no existe.  
1. AWS Console → EC2 → Key Pairs → **Create key pair** → nombre `claves-ml` → descarga el `.pem`  
2. Guarda el `.pem` en `C:\Users\Javi\.ssh\claves-ml.pem`  
3. Actualiza `terraform\terraform.tfvars` si cambiaste el nombre

### Contenedor caído / en bucle de reinicios

```bash
docker logs <nombre_contenedor> --tail 50
```

---

## Al terminar — apagar para no gastar crédito

```bash
# Desde dentro de la EC2, parar todos los contenedores limpiamente:
cd /home/ubuntu/app
docker compose -f infrastructure/hadoop/docker-compose.yml  stop
docker compose -f infrastructure/ml-env/docker-compose.yml  stop
docker compose -f infrastructure/api/docker-compose.yml     stop
docker compose -f infrastructure/n8n/docker-compose.yml     stop
```

O directamente desde PowerShell (con credenciales activas), parar la instancia:
```powershell
aws ec2 stop-instances --instance-ids <INSTANCE_ID>
```

Para terminarla definitivamente (borra todo):
```powershell
cd terraform
terraform destroy   # confirmar con "yes"
```
