# Despliegue en AWS — Guía Completa con Terraform

> TFG: Sistema de Detección de Fraude Bancario  
> Cuenta: AWS Academy (laboratorio, región `us-east-1`)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│  EC2  t3.large  (2 vCPU · 8 GB RAM · 30 GB gp3)                │
│                                                                 │
│  shared-ml-network (Docker bridge)                             │
│  ├── ml-env      JupyterLab        :8888                        │
│  ├── ai-service  FastAPI /predict  :8000                        │
│  ├── neo4j       Graph DB          :7474 / :7687                │
│  ├── hadoop      HDFS + YARN       :9870 / :9000                │
│  └── n8n         Workflows         :5678                        │
└─────────────────────────────────────────────────────────────────┘
```

Todo el stack se levanta automáticamente al arrancar la EC2 vía `user_data`.  
El repo se clona en `/home/ubuntu/app`.

---

## Limitaciones de AWS Academy

| Limitación | Detalle |
|---|---|
| Solo `us-east-1` | Región fija, no se puede cambiar |
| No crear IAM users/roles | Se usa el rol `LabInstanceProfile` preexistente |
| Sesiones de ~4 h | Las credenciales AWS caducan; hay que renovarlas |
| $50 de crédito | Solo encender para demos y trabajo activo |
| Key Pair se pierde | Si el lab se reinicia desde cero, hay que recrearlo |

---

## 1. Instalar Terraform

Solo hay que hacerlo una vez en tu máquina.

**Windows (PowerShell con winget):**
```powershell
winget install HashiCorp.Terraform
# Reiniciar PowerShell, luego verificar:
terraform -v
```

**Windows (manual, si winget no funciona):**
1. Ir a https://developer.hashicorp.com/terraform/install
2. Descargar el ZIP para Windows AMD64
3. Extraer `terraform.exe` y moverlo a `C:\Windows\System32\` (o a cualquier carpeta en el PATH)
4. Verificar: `terraform -v`

**Linux/Debian (PC de clase):**
```bash
wget https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip
unzip terraform_*.zip
sudo mv terraform /usr/local/bin/
terraform -v
```

---

## 2. Pegar credenciales de AWS Academy

Cada vez que abras un terminal nuevo o caduquen las claves (~4 h):

1. **AWS Academy** → **AWS Details** → **Show**
2. Copia los tres valores y pégalos en PowerShell:

```powershell
$env:AWS_ACCESS_KEY_ID     = "ASIA..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_SESSION_TOKEN     = "..."
$env:AWS_DEFAULT_REGION    = "us-east-1"
```

> Las variables solo duran mientras el terminal está abierto. Si cierras PowerShell, hay que repetir este paso.

---

## 3. Crear el Key Pair (solo la primera vez o si el lab se reinició)

1. Consola AWS → **EC2** → **Key Pairs** → **Create key pair**
2. Nombre: `claves-ml` · Tipo: RSA · Formato: `.pem`
3. Se descarga automáticamente `claves-ml.pem`
4. Moverlo a `C:\Users\Javi\.ssh\claves-ml.pem`
5. En Linux/Mac: `chmod 600 ~/.ssh/claves-ml.pem`

> En Windows no hace falta el `chmod`. Si SSH da error de permisos:
> ```powershell
> icacls "$env:USERPROFILE\.ssh\claves-ml.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"
> ```

---

## 4. Primer despliegue (crear la EC2 desde cero)

```powershell
# Desde la raíz del proyecto
cd terraform

# Inicializar (descarga el provider de AWS)
terraform init

# Ver qué va a crear (sin ejecutar nada)
terraform plan -var="key_pair_name=claves-ml"

# Desplegar
terraform apply -var="key_pair_name=claves-ml"
# Escribe "yes" cuando lo pida
```

Terraform muestra al terminar (~2 min):
```
ec2_public_ip = "X.X.X.X"
ssh_command   = "ssh -i ~/.ssh/claves-ml.pem ubuntu@X.X.X.X"
services = {
  api_docs  = "http://X.X.X.X:8000/docs"
  jupyter   = "http://X.X.X.X:8888"
  n8n       = "http://X.X.X.X:5678"
  neo4j     = "http://X.X.X.X:7474"
  ...
}
```

Guarda la IP — cambia cada vez que destruyes y recreas la instancia.

---

## 5. Monitorizar el arranque automático

La EC2 instala Docker y levanta todos los contenedores automáticamente.  
El proceso tarda **~5-10 minutos** la primera vez.

```powershell
# Ver el log de arranque en tiempo real (sustituir IP):
ssh -i "$env:USERPROFILE\.ssh\claves-ml.pem" ubuntu@<IP> "sudo tail -f /var/log/user-data.log"
```

Cuando aparezca `DONE — Stack levantado correctamente`, todos los servicios están listos.

Verificar que los 5 contenedores están arriba:
```bash
# Desde dentro de la EC2:
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Resultado esperado:
```
NAMES        STATUS
hadoop       Up (healthy)
ai-service   Up
ml-env       Up
neo4j        Up
n8n          Up
```

---

## 6. Conectar por SSH

```powershell
# Windows PowerShell:
ssh -i "$env:USERPROFILE\.ssh\claves-ml.pem" ubuntu@<IP>

# Linux/Mac:
ssh -i ~/.ssh/claves-ml.pem ubuntu@<IP>
```

El proyecto está en `/home/ubuntu/app`.

---

## 7. Importar el workflow de n8n (primera vez)

Una vez dentro de la EC2 y con n8n arriba, desde tu navegador:

1. Abrir `http://<IP>:5678`
2. Menú superior → **Import from file**
3. Subir `workflows/informe_fraude_diario.json` (está en el repo)
4. Configurar las 3 credenciales (n8n te avisa cuáles faltan):
   - **Neo4j Basic Auth** → Header `Authorization: Basic bmVvNGo6cGFzc3dvcmQ=`
   - **Groq API Key** → Header `Authorization: Bearer gsk_...`
   - **SMTP Gmail** → Host `smtp.gmail.com`, Port `465`, SSL/TLS, App Password

> Las URLs internas (`neo4j:7474`, `ai-service:8000`) son iguales que en local — misma red Docker.

---

## 8. Relanzar instancia existente (lab reiniciado, EC2 parada)

Si la EC2 sigue existiendo pero estaba parada:

```powershell
# 1. Obtener la nueva IP (cambia cada vez que se para/inicia):
aws ec2 describe-instances `
  --filters "Name=tag:Name,Values=fraud-detection-server" `
  --query "Reservations[].Instances[].PublicIpAddress" `
  --output text

# 2. Iniciar la instancia si está parada:
aws ec2 start-instances --instance-ids <INSTANCE_ID>

# 3. Conectar por SSH (esperar ~1 min a que arranque):
ssh -i "$env:USERPROFILE\.ssh\claves-ml.pem" ubuntu@<IP>
```

Dentro de la EC2, los contenedores deberían haber arrancado solos (`restart: unless-stopped`).  
Si falta alguno:

```bash
cd /home/ubuntu/app

# Actualizar código:
git pull

# Levantar lo que falte:
docker network create shared-ml-network 2>/dev/null || true
docker compose -f infrastructure/hadoop/docker-compose.yml  up -d
docker compose -f infrastructure/api/docker-compose.yml     up -d
docker compose -f infrastructure/ml-env/docker-compose.yml  up -d
docker compose -f infrastructure/n8n/docker-compose.yml     up -d

# Verificar:
docker ps --format "table {{.Names}}\t{{.Status}}"
```

---

## 9. Apagar para no gastar crédito

**Opción A — Parar la instancia (conserva datos, cobra EBS ~$0.08/día):**
```powershell
aws ec2 stop-instances --instance-ids <INSTANCE_ID>
```

**Opción B — Destruir todo (no cobra nada, pero hay que desplegar de nuevo):**
```powershell
cd terraform
terraform destroy -var="key_pair_name=claves-ml"
# Escribe "yes"
```

> Con $50 de crédito y `t3.large` a $0.083/h tienes ~600 horas. Más que suficiente para el TFG.

---

## Estructura Terraform

```
terraform/
├── main.tf          # Provider AWS + backend S3 opcional
├── variables.tf     # key_pair_name, instance_type, repo_url...
├── ec2.tf           # EC2 + Security Group + user_data
├── s3.tf            # Bucket S3 para Terraform state
├── outputs.tf       # IP, URLs, comando SSH
└── userdata.sh.tpl  # Script de inicio: instala Docker, clona repo, levanta stack
```

El `user_data` hace automáticamente:
1. Instala Docker + Git
2. Clona el repo en `/home/ubuntu/app`
3. Crea el `.env` con `MODEL_NAME=modelo_arbol_optimizado.pkl`
4. Crea la red `shared-ml-network`
5. Levanta hadoop → api → ml-env → n8n

---

## Solución de problemas

### "No valid credential sources found"
Las credenciales AWS han caducado. Vuelve a AWS Academy → AWS Details y repega los `$env:`.

### Key Pair desaparecido (lab reiniciado desde cero)
El lab se reinició completamente. Crea un nuevo Key Pair en la consola AWS (ver paso 3) y haz `terraform destroy` + `terraform apply` para recrear la EC2 con el nuevo key pair.

### Contenedor caído
```bash
docker logs <nombre_contenedor> --tail 50
docker compose -f infrastructure/<servicio>/docker-compose.yml up -d
```

### n8n: "secure cookie" al abrir por HTTP
Ya está corregido en el compose (`N8N_SECURE_COOKIE=false`). Si persiste:
```bash
cd /home/ubuntu/app/infrastructure/n8n
docker compose down && docker compose up -d
```

### Neo4j: fallo de credenciales
```bash
cd /home/ubuntu/app/infrastructure/ml-env
docker compose --env-file ../../.env down
docker compose --env-file ../../.env up -d
```

> TFG: Sistema de Detección de Fraude Bancario  
> Cuenta: AWS Academy (laboratorio $50, región `us-east-1`)

---

## Instancia activa — `54.91.126.202`

> EC2 `t3.large` · Ubuntu 22.04 · Key Pair: `claves-ml`

| Servicio | URL |
|---|---|
| FastAPI (Swagger) | http://54.91.126.202:8000/docs |
| FastAPI (health) | http://54.91.126.202:8000/health |
| JupyterLab | http://54.91.126.202:8888 |
| Hadoop NameNode UI | http://54.91.126.202:9870 |
| YARN ResourceManager | http://54.91.126.202:8088 |
| Neo4j Browser | http://54.91.126.202:7474 (user: `neo4j` / pass: `password`) |
| n8n | http://54.91.126.202:5678 |

SSH:
```bash
ssh -i ~/.ssh/claves-ml.pem ubuntu@54.91.126.202
# Windows PowerShell:
ssh -i "$env:USERPROFILE\.ssh\claves-ml.pem" ubuntu@54.91.126.202
```

Ver logs de arranque:
```bash
ssh -i ~/.ssh/claves-ml.pem ubuntu@54.91.126.202 "sudo tail -50 /var/log/user-data.log"
```

---

## Arquitectura objetivo

```
┌─────────────────────────────────────────────────────────────────┐
│  AWS  (us-east-1)                                               │
│                                                                 │
│  ┌─────────────────────────────────┐   ┌─────────────────────┐  │
│  │  EC2  t3.large                  │   │  S3 Bucket          │  │
│  │  ─────────────────────────────  │   │  fraud-data-tfg     │  │
│  │  Docker Compose (mismo que      │   │  ├── raw/           │  │
│  │  local):                        │──>│  ├── processed/     │  │
│  │  • ml-env  (JupyterLab :8888)   │   │  └── fraud-results/ │  │
│  │  • ai-service (FastAPI :8000)   │   │       (espejo HDFS) │  │
│  │  • neo4j   (:7474/:7687)        │   └─────────────────────┘  │
│  │  • hadoop  (HDFS :9870/:9000)   │                            │
│  │  • n8n     (:5678)              │   ┌─────────────────────┐  │
│  │                                 │   │  SageMaker          │  │
│  └─────────────────────────────────┘   │  Endpoint de        │  │
│                                        │  inferencia fraude  │  │
│  ┌─────────────────────────────────┐   │  (sklearn container)│  │
│  │  ECR                            │   └─────────────────────┘  │
│  │  • ml-env:latest                │                            │
│  │  • ai-service:latest            │                            │
│  └─────────────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

**Decisión clave**: mantenemos Hadoop HDFS en la EC2 (igual que local) y además
replicamos los resultados a S3. Así demostramos ambas tecnologías en el TFG.

---

## Limitaciones de AWS Academy (cuenta estudiante)

| Limitación | Impacto | Solución |
|---|---|---|
| Solo `us-east-1` | Hay que fijar la región | `provider "aws" { region = "us-east-1" }` |
| No crear IAM roles/users | Terraform no puede usar `aws_iam_role` | Usar el rol `LabRole` preexistente |
| Sesiones expiran (~4h) | Terraform state se pierde si es local | Guardar state en S3 |
| $50 de crédito | No podemos tener todo 24/7 | Solo encender para demos/TFG |
| No instancias grandes | `t3.xlarge` máximo recomendado | `t3.large` es suficiente |

---

## Estructura Terraform

```
terraform/
├── main.tf           # Provider + backend S3 para el state
├── variables.tf      # Variables configurables
├── outputs.tf        # IP pública, URLs de acceso
├── ec2.tf            # EC2 + Security Group + user_data (Docker install)
├── s3.tf             # Bucket de datos + permisos
├── ecr.tf            # Repositorios de imágenes Docker
└── sagemaker.tf      # Endpoint de inferencia (modelo de fraude)
```

### `main.tf`
```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }

  # State remoto en S3 para sobrevivir reinicios de sesión
  backend "s3" {
    bucket = "fraud-tfg-terraform-state"
    key    = "terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = "us-east-1"
}
```

### `variables.tf`
```hcl
variable "key_pair_name" {
  description = "Nombre del key pair de EC2 creado en la consola AWS"
  type        = string
}

variable "allowed_ip" {
  description = "Tu IP para el security group (curl ifconfig.me)"
  type        = string
  default     = "0.0.0.0/0"   # Cambiar a tu IP real en producción
}
```

### `ec2.tf`
```hcl
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical (Ubuntu)
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-*-22.04-amd64-server-*"]
  }
}

resource "aws_instance" "fraud_server" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.large"       # 2 vCPU, 8GB RAM
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.fraud_sg.id]
  iam_instance_profile   = "LabInstanceProfile"   # Rol preexistente en Academy

  root_block_device {
    volume_size = 30    # GB — suficiente para Docker images + datos
    volume_type = "gp3"
  }

  user_data = <<-EOF
    #!/bin/bash
    set -e

    # Docker
    apt-get update && apt-get install -y docker.io git
    curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
        -o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose
    usermod -aG docker ubuntu
    systemctl enable docker && systemctl start docker

    # Clonar repo
    cd /home/ubuntu
    git clone https://github.com/<usuario>/ml-fraud-detection.git
    cd ml-fraud-detection

    # Variables de entorno (ajustar con las reales)
    cat > .env <<ENVFILE
    MODEL_NAME=modelo_fraude_rf_final.joblib
    NEO4J_AUTH=neo4j/password
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=password
    ENVFILE

    # Arrancar stack completo
    docker network create shared-ml-network
    docker compose -f infrastructure/ml-env/docker-compose.yml  up -d
    docker compose -f infrastructure/api/docker-compose.yml     up -d
    docker compose -f infrastructure/hadoop/docker-compose.yml  up -d
    docker compose -f infrastructure/n8n/docker-compose.yml     up -d
  EOF

  tags = { Name = "fraud-detection-server" }
}

resource "aws_security_group" "fraud_sg" {
  name        = "fraud-detection-sg"
  description = "Puertos de los servicios del TFG"

  # SSH
  ingress { from_port = 22,   to_port = 22,   protocol = "tcp", cidr_blocks = [var.allowed_ip] }
  # FastAPI
  ingress { from_port = 8000, to_port = 8000, protocol = "tcp", cidr_blocks = [var.allowed_ip] }
  # JupyterLab
  ingress { from_port = 8888, to_port = 8888, protocol = "tcp", cidr_blocks = [var.allowed_ip] }
  # Neo4j Browser
  ingress { from_port = 7474, to_port = 7474, protocol = "tcp", cidr_blocks = [var.allowed_ip] }
  # Neo4j Bolt
  ingress { from_port = 7687, to_port = 7687, protocol = "tcp", cidr_blocks = [var.allowed_ip] }
  # Hadoop NameNode UI
  ingress { from_port = 9870, to_port = 9870, protocol = "tcp", cidr_blocks = [var.allowed_ip] }
  # YARN UI
  ingress { from_port = 8088, to_port = 8088, protocol = "tcp", cidr_blocks = [var.allowed_ip] }
  # n8n
  ingress { from_port = 5678, to_port = 5678, protocol = "tcp", cidr_blocks = [var.allowed_ip] }

  egress { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}
```

### `s3.tf`
```hcl
resource "aws_s3_bucket" "fraud_data" {
  bucket = "fraud-detection-tfg-data"
  tags   = { Name = "fraud-data", Project = "TFG" }
}

resource "aws_s3_bucket_versioning" "fraud_data" {
  bucket = aws_s3_bucket.fraud_data.id
  versioning_configuration { status = "Enabled" }
}

# Estructura de "carpetas" equivalente a HDFS
resource "aws_s3_object" "raw_prefix" {
  bucket  = aws_s3_bucket.fraud_data.id
  key     = "raw/"
  content = ""
}
resource "aws_s3_object" "processed_prefix" {
  bucket  = aws_s3_bucket.fraud_data.id
  key     = "processed/"
  content = ""
}
resource "aws_s3_object" "results_prefix" {
  bucket  = aws_s3_bucket.fraud_data.id
  key     = "fraud-results/"
  content = ""
}
```

### `sagemaker.tf`
```hcl
# Subir el modelo al bucket S3
resource "aws_s3_object" "model_artifact" {
  bucket = aws_s3_bucket.fraud_data.id
  key    = "models/model.tar.gz"
  source = "../models/modelo_fraude_rf_final.joblib"  # empaquetar como tar.gz antes
}

# Modelo en SageMaker (container sklearn gestionado por AWS)
resource "aws_sagemaker_model" "fraud_model" {
  name               = "fraud-detection-rf"
  execution_role_arn = "arn:aws:iam::<account-id>:role/LabRole"

  primary_container {
    image          = "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3"
    model_data_url = "s3://${aws_s3_bucket.fraud_data.bucket}/models/model.tar.gz"
  }
}

# Configuración del endpoint (instancia pequeña para demo)
resource "aws_sagemaker_endpoint_configuration" "fraud_config" {
  name = "fraud-detection-config"
  production_variants {
    variant_name           = "default"
    model_name             = aws_sagemaker_model.fraud_model.name
    initial_instance_count = 1
    instance_type          = "ml.t2.medium"   # la más barata
  }
}

# Endpoint desplegado (coste ~$0.065/h — apagar cuando no se use)
resource "aws_sagemaker_endpoint" "fraud_endpoint" {
  name                 = "fraud-detection-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.fraud_config.name
}
```

### `outputs.tf`
```hcl
output "ec2_public_ip" {
  value       = aws_instance.fraud_server.public_ip
  description = "IP pública de la EC2 — acceder por SSH y a los servicios"
}

output "services" {
  value = {
    jupyter   = "http://${aws_instance.fraud_server.public_ip}:8888"
    api       = "http://${aws_instance.fraud_server.public_ip}:8000/docs"
    neo4j     = "http://${aws_instance.fraud_server.public_ip}:7474"
    hadoop_ui = "http://${aws_instance.fraud_server.public_ip}:9870"
    n8n       = "http://${aws_instance.fraud_server.public_ip}:5678"
  }
}

output "s3_bucket" {
  value = aws_s3_bucket.fraud_data.bucket
}

output "sagemaker_endpoint" {
  value = aws_sagemaker_endpoint.fraud_endpoint.name
}
```

---

## Integración HDFS ↔ S3 (espejo de datos)

Para demostrar ambas tecnologías en el TFG, añadir esta celda al notebook PySpark
**después** de procesar en HDFS, para copiar resultados a S3:

```python
import boto3

# Exportar resultados de HDFS a S3 (solo en entorno AWS)
S3_BUCKET = "fraud-detection-tfg-data"

def hdfs_to_s3(hdfs_path: str, s3_prefix: str):
    """Lee parquet de HDFS y lo sube a S3."""
    sdf = spark.read.parquet(hdfs_path)
    s3_path = f"s3a://{S3_BUCKET}/{s3_prefix}/"
    sdf.write.mode("overwrite").parquet(s3_path)
    print(f"[OK] {hdfs_path} → s3://{S3_BUCKET}/{s3_prefix}/")

# Espejo de resultados en S3
hdfs_to_s3(f"{HDFS_URI}/data/processed/transactions_clean.parquet", "processed")
hdfs_to_s3(f"{HDFS_URI}/data/fraud-results/batch_predictions.parquet", "fraud-results")
```

> Para que `s3a://` funcione desde Spark/Hadoop se necesita añadir a `core-site.xml`:
> `fs.s3a.aws.credentials.provider = com.amazonaws.auth.InstanceProfileCredentialsProvider`
> (usa el rol IAM de la EC2, sin credenciales hardcodeadas)

---

## SageMaker — Llamar al endpoint desde Python

Una vez desplegado, el endpoint de SageMaker reemplaza o complementa al FastAPI:

```python
import boto3, json

runtime = boto3.client("sagemaker-runtime", region_name="us-east-1")

payload = {
    "amount": 500, "old_balance_orig": 10000, "new_balance_orig": 9500,
    "old_balance_dest": 0, "new_balance_dest": 500,
    "orig_out_degree": 5, "orig_pagerank": 0.01, "orig_community": 1,
    "dest_in_degree": 3, "dest_pagerank": 0.005, "dest_community": 2,
    "type_CASH_IN": 0, "type_CASH_OUT": 1, "type_DEBIT": 0,
    "type_PAYMENT": 0, "type_TRANSFER": 0
}

response = runtime.invoke_endpoint(
    EndpointName="fraud-detection-endpoint",
    ContentType="application/json",
    Body=json.dumps(payload)
)

result = json.loads(response["Body"].read())
print(f"Probabilidad de fraude: {result}")
```

---

## Pasos de despliegue

```bash
# 1. Instalar Terraform (si no está)
winget install HashiCorp.Terraform

# 2. Crear el bucket de estado ANTES (manual, solo la primera vez)
aws s3 mb s3://fraud-tfg-terraform-state --region us-east-1

# 3. Inicializar Terraform
cd terraform/
terraform init

# 4. Revisar el plan
terraform plan -var="key_pair_name=vockey"  # 'vockey' es el key pair de Academy

# 5. Desplegar
terraform apply -var="key_pair_name=vockey" -auto-approve

# 6. Conectar por SSH cuando la EC2 esté lista (~3 min para Docker + stack)
ssh -i ~/.ssh/labsuser.pem ubuntu@<EC2_IP>

# 7. Verificar servicios
docker ps
curl http://localhost:8000/health

# 8. Al terminar la sesión — APAGAR para no gastar crédito
terraform destroy -var="key_pair_name=vockey" -auto-approve
# O solo parar la EC2:
aws ec2 stop-instances --instance-ids <ID>
```

---

## Despliegue desde cero (cualquier máquina)

### Requisitos previos
- Terraform instalado (`terraform -v`)
- Fichero `.pem` del Key Pair en `~/.ssh/claves-ml.pem` (chmod 600 en Linux/Mac)
- Credenciales AWS Academy activas

### Pasos

**1. Instalar Terraform** (si no está)
```bash
# Linux/Debian (PC de clase):
wget https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip
unzip terraform_*.zip && sudo mv terraform /usr/local/bin/

# Windows:
winget install HashiCorp.Terraform
```

**2. Clonar el repo y crear terraform.tfvars**
```bash
git clone https://github.com/ZuhirDev/ml-fraud-detection.git
cd ml-fraud-detection/terraform

cat > terraform.tfvars <<EOF
key_pair_name = "claves-ml"
repo_url      = "https://github.com/ZuhirDev/ml-fraud-detection.git"
EOF
```

**3. Pegar credenciales del laboratorio AWS**
```bash
# Linux/Mac:
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_DEFAULT_REGION="us-east-1"

# Windows PowerShell:
$env:AWS_ACCESS_KEY_ID     = "ASIA..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_SESSION_TOKEN     = "..."
$env:AWS_DEFAULT_REGION    = "us-east-1"
```

**4. Inicializar y desplegar**
```bash
terraform init
terraform apply    # confirmar con "yes"
```
Terraform muestra la IP y todas las URLs al terminar (~2 min para EC2, ~20 min para build de imágenes Docker).

**5. Monitorizar el arranque**
```bash
# Sustituir IP por la que aparece en el output de terraform apply
ssh -i ~/.ssh/claves-ml.pem ubuntu@<IP> "sudo tail -f /var/log/user-data.log"
# Cuando veas "DONE — Stack levantado", todos los servicios están disponibles
```

**6. Al terminar — apagar para no gastar crédito**
```bash
terraform destroy   # borra todo
# O solo parar la EC2 (conserva IP elástica si tienes):
aws ec2 stop-instances --instance-ids <ID>
```

> **Credenciales AWS Academy**: caducan cada ~4h. Si `terraform apply` falla con
> "No valid credential sources", vuelve a AWS Academy → AWS Details → Show y repega las variables.

> **Key Pair en nueva sesión de lab**: si el laboratorio se reinició desde cero, el Key Pair
> `claves-ml` habrá desaparecido. Créalo de nuevo en EC2 → Key Pairs → Create, descarga
> el `.pem` y actualiza `terraform.tfvars`.

---

## Estimación de costes ($50 de crédito)

| Recurso | Precio/hora | 8h demo | Semana (solo demos) |
|---|---|---|---|
| EC2 t3.large | $0.083 | $0.66 | ~$3 |
| SageMaker ml.t2.medium | $0.065 | $0.52 | ~$2.50 |
| S3 (10GB) | ~$0 | ~$0 | ~$0.08 |
| ECR (2GB imágenes) | $0.10/GB/mes | ~$0 | ~$0.20 |
| **Total estimado** | | **~$1.20** | **~$5.80** |

Con $50 de crédito tenéis margen más que suficiente para el TFG.

> **Consejo**: apagar la instancia EC2 y el endpoint SageMaker cuando no los uséis.
> Solo por tener la EC2 parada (no terminada) se cobra el EBS: ~$2.40/mes para 30GB gp3.
