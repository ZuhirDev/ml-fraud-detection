# Despliegue en AWS — Plan con Terraform

> TFG: Sistema de Detección de Fraude Bancario  
> Cuenta: AWS Academy (laboratorio $50, región `us-east-1`)

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
