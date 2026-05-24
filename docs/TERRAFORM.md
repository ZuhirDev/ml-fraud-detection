# Terraform — Infraestructura como Código en AWS

> TFG: Sistema de Detección de Fraude Bancario  
> Tecnologías: Terraform · AWS EC2 · AWS S3 · AWS Academy

---

## 1. ¿Qué es Terraform y qué es IaC?

**Infraestructura como Código (IaC)** es la práctica de gestionar y provisionar infraestructura (servidores, redes, bases de datos, etc.) mediante ficheros de configuración legibles por máquina, en lugar de configurarlos manualmente a través de una consola web o comandos ad-hoc.

**Terraform** es la herramienta IaC más extendida de la industria, desarrollada por HashiCorp. Usa un lenguaje declarativo llamado **HCL** (HashiCorp Configuration Language) en el que describes el estado deseado de tu infraestructura, y Terraform se encarga de calcular qué cambios hay que hacer para llegar a ese estado.

### ¿Por qué Terraform en este proyecto?

Sin Terraform, desplegar el sistema en AWS requeriría:
1. Entrar a la consola web de AWS
2. Ir a EC2, seleccionar AMI, tipo de instancia, configurar red, security group, etc.
3. Cada vez que se destruye el laboratorio y se vuelve a crear, repetir todos esos pasos a mano

Con Terraform:
1. Ejecutar `terraform apply` en el terminal
2. En ~2 minutos la EC2 está creada, configurada y con todos los contenedores corriendo

**Ventaja adicional:** el estado de la infraestructura está en código, versionado en Git. Cualquier persona puede reproducir exactamente el mismo entorno con los mismos ficheros.

---

## 2. Conceptos clave de Terraform

### Provider
Plugin que conecta Terraform con un proveedor cloud. En este proyecto se usa el provider oficial de AWS:
```hcl
provider "aws" {
  region = "us-east-1"
}
```

### Resource
Cada pieza de infraestructura que Terraform gestiona. Una EC2, un Security Group, un bucket S3... son resources:
```hcl
resource "aws_instance" "fraud_server" {
  ami           = "ami-xxxx"
  instance_type = "t3.large"
}
```

### State (estado)
Terraform guarda un fichero `terraform.tfstate` que registra qué recursos ha creado y cuál es su estado actual. Lo usa para saber qué ha cambiado entre ejecuciones. Por defecto es local, pero puede guardarse en S3 para compartirlo entre máquinas.

### Plan vs Apply
- `terraform plan` — calcula qué cambios haría, sin ejecutarlos. Útil para revisar antes de desplegar
- `terraform apply` — ejecuta los cambios después de pedir confirmación

### Variables
Parámetros configurables que se pasan al ejecutar Terraform, para no hardcodear valores en el código:
```hcl
variable "key_pair_name" {
  type = string
}
```

### Outputs
Valores que Terraform imprime al terminar el `apply`. En este proyecto muestra la IP, el comando SSH y las URLs de todos los servicios.

---

## 3. Instalación de Terraform

### Windows (recomendado: winget)

```powershell
winget install HashiCorp.Terraform
```

Cerrar y reabrir PowerShell, luego verificar:
```powershell
terraform -v
# Terraform v1.x.x
```

### Windows (manual, si winget no está disponible)

1. Ir a https://developer.hashicorp.com/terraform/install
2. Descargar el ZIP para **Windows AMD64**
3. Extraer `terraform.exe`
4. Moverlo a `C:\Windows\System32\` (ya está en el PATH) o crear una carpeta `C:\terraform\` y añadirla al PATH manualmente:
   - Buscar "Variables de entorno" en el menú inicio
   - Variables del sistema → Path → Editar → Nueva → `C:\terraform`
5. Verificar: abrir nuevo PowerShell → `terraform -v`

### Linux / Debian (PC de clase)

```bash
# Descargar la versión estable
wget https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip
unzip terraform_1.9.8_linux_amd64.zip
sudo mv terraform /usr/local/bin/
terraform -v
```

---

## 4. Credenciales de AWS Academy

AWS Academy usa credenciales de sesión temporales que **caducan cada ~4 horas**. No se pueden guardar de forma permanente; hay que renovarlas al inicio de cada sesión de trabajo.

### Obtener las credenciales

1. Ir a **AWS Academy** → panel del laboratorio → **AWS Details**
2. Clic en **Show** junto a "AWS CLI"
3. Copiar los tres valores

### Pegarlas en PowerShell (Windows)

```powershell
$env:AWS_ACCESS_KEY_ID     = "ASIA..."
$env:AWS_SECRET_ACCESS_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
$env:AWS_SESSION_TOKEN     = "IQoJb3JpZ2luX2VjE..."   # cadena muy larga
$env:AWS_DEFAULT_REGION    = "us-east-1"
```

### Pegarlas en bash (Linux/Mac)

```bash
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="xxxx"
export AWS_SESSION_TOKEN="IQoJb3..."
export AWS_DEFAULT_REGION="us-east-1"
```

> **Importante:** estas variables solo existen mientras el terminal está abierto. Si cierras la ventana hay que repetir el paso. Nunca las guardes en un fichero que suba a Git.

### Verificar que funcionan

```powershell
aws sts get-caller-identity
# Debe devolver el Account ID del laboratorio
```

---

## 5. Preparativos antes del primer deploy

### Crear el Key Pair en AWS

El Key Pair es el par de claves SSH que permite conectarse a la EC2. Se crea **en la consola de AWS** (no con Terraform, porque la clave privada solo se descarga en el momento de creación).

1. Consola AWS → **EC2** → menú lateral → **Key Pairs**
2. **Create key pair**
   - Name: `claves-ml` (o el nombre que prefieras)
   - Key pair type: RSA
   - Private key file format: `.pem`
3. Se descarga automáticamente `claves-ml.pem`
4. Moverlo a `C:\Users\<tu-usuario>\.ssh\claves-ml.pem`

> Si el laboratorio se reinicia desde cero, el Key Pair desaparece y hay que crear uno nuevo.

### Clonar el repositorio

```powershell
git clone https://github.com/ZuhirDev/ml-fraud-detection.git
cd ml-fraud-detection\terraform
```

Los ficheros `.tf` están en la carpeta `terraform/`. Terraform usa todos los `.tf` de la carpeta actual, por lo que hay que estar dentro de esa carpeta al ejecutar los comandos.

---

## 6. Estructura de los ficheros Terraform

```
terraform/
├── main.tf              # Provider AWS + backend S3 (opcional)
├── variables.tf         # Parámetros configurables
├── ec2.tf               # Instancia EC2 + Security Group
├── s3.tf                # Bucket S3 para el Terraform state
├── outputs.tf           # IP, URLs, comando SSH
└── userdata.sh.tpl      # Script bash de inicialización de la EC2
```

### `main.tf` — Provider y backend

Define el provider de AWS y la versión. También contiene la configuración del backend S3 (comentada por defecto; si se activa, el `terraform.tfstate` se guarda en S3 en lugar de localmente).

```hcl
terraform {
  required_version = ">= 1.3"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  # backend "s3" {           ← descomentar para estado remoto en S3
  #   bucket = "fraud-tfg-state-XXXX"
  #   key    = "terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = "us-east-1"   # AWS Academy solo permite esta región
}
```

### `variables.tf` — Parámetros

```hcl
variable "key_pair_name" {
  description = "Nombre del Key Pair creado en EC2 → Key Pairs"
  type        = string
  # Sin default: Terraform lo pedirá al hacer apply si no se pasa con -var
}

variable "instance_type" {
  default = "t3.large"     # 2 vCPU, 8 GB RAM — mínimo para el stack completo
}

variable "allowed_ip" {
  default = "0.0.0.0/0"   # Abierto para demos; en prod cambiar a tu IP
}

variable "repo_url" {
  default = "https://github.com/ZuhirDev/ml-fraud-detection.git"
}

variable "repo_branch" {
  default = "main"
}
```

### `ec2.tf` — La instancia y el Security Group

Crea la EC2 con Ubuntu 22.04 y abre los puertos necesarios. Lo más importante es el bloque `user_data`, que apunta al script `userdata.sh.tpl`. Este script se ejecuta automáticamente una sola vez cuando la instancia arranca por primera vez.

```hcl
resource "aws_instance" "fraud_server" {
  ami                    = data.aws_ami.ubuntu_22.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.fraud_sg.id]
  iam_instance_profile   = "LabInstanceProfile"   # rol IAM preexistente en Academy

  root_block_device {
    volume_size = 30     # 30 GB gp3 para imágenes Docker y datos
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/userdata.sh.tpl", {
    repo_url    = var.repo_url
    repo_branch = var.repo_branch
    model_s3_path = var.model_s3_path
  })
}
```

### `userdata.sh.tpl` — Script de inicialización automática

Este script es lo que diferencia un deploy manual de un deploy automatizado. Se ejecuta como `root` al arrancar la EC2 y hace todo el setup:

```bash
# [1/6] Instala Docker + Git
apt-get update && curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu

# [2/6] Clona el repositorio
git clone --branch main https://github.com/ZuhirDev/ml-fraud-detection.git /home/ubuntu/app

# [3/6] Crea el fichero .env
echo "MODEL_NAME=modelo_arbol_optimizado.pkl" > /home/ubuntu/app/.env
echo "NEO4J_AUTH=neo4j/password" >> /home/ubuntu/app/.env

# [4/6] Descarga modelo desde S3 (si se especificó una ruta S3)
aws s3 cp s3://bucket/modelo.pkl /home/ubuntu/app/models/

# [5/6] Crea la red Docker
docker network create shared-ml-network

# [6/6] Levanta el stack
cd /home/ubuntu/app
docker compose -f infrastructure/hadoop/docker-compose.yml up -d
docker compose -f infrastructure/api/docker-compose.yml    up -d
docker compose -f infrastructure/ml-env/docker-compose.yml up -d
docker compose -f infrastructure/n8n/docker-compose.yml    up -d

echo "DONE — Stack levantado correctamente"
```

El progreso es visible en: `sudo tail -f /var/log/user-data.log`

### `outputs.tf` — Resultados del deploy

Al terminar `terraform apply`, se imprimen automáticamente:

```hcl
output "ec2_public_ip"  { value = aws_instance.fraud_server.public_ip }
output "ssh_command"    { value = "ssh -i ~/.ssh/${var.key_pair_name}.pem ubuntu@${...}" }
output "services"       { value = { jupyter = "http://IP:8888", n8n = "http://IP:5678", ... } }
```

---

## 7. Flujo completo de despliegue

```
[1] Instalar Terraform
        │
        ▼
[2] Pegar credenciales AWS ($env:AWS_ACCESS_KEY_ID...)
        │
        ▼
[3] Crear Key Pair en consola AWS → descargar .pem → mover a ~/.ssh/
        │
        ▼
[4] cd terraform/
    terraform init          ← descarga el provider de AWS (~30 seg)
        │
        ▼
[5] terraform plan -var="key_pair_name=claves-ml"
                            ← muestra qué va a crear (sin ejecutar)
        │
        ▼
[6] terraform apply -var="key_pair_name=claves-ml"
    → escribe "yes"         ← crea EC2 + Security Group + S3 bucket (~2 min)
        │
        ▼
[7] Terraform imprime: IP, SSH command, URLs de servicios
        │
        ▼
[8] ssh -i ~/.ssh/claves-ml.pem ubuntu@<IP>
    sudo tail -f /var/log/user-data.log
                            ← esperar "DONE" (~5-10 min primera vez)
        │
        ▼
[9] docker ps               ← verificar 5 contenedores Up
        │
        ▼
[10] Importar workflow en http://<IP>:5678 → finalizado
```

### Comandos paso a paso

```powershell
# 1. Ir a la carpeta terraform
cd C:\Users\Javi\Desktop\Programación\ml-fraud-detection\terraform

# 2. Pegar credenciales AWS (copiarlas de AWS Academy → AWS Details → Show)
$env:AWS_ACCESS_KEY_ID     = "ASIA..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_SESSION_TOKEN     = "..."
$env:AWS_DEFAULT_REGION    = "us-east-1"

# 3. Inicializar (solo necesario la primera vez o si cambias el provider)
terraform init

# 4. Revisar el plan
terraform plan -var="key_pair_name=claves-ml"

# 5. Desplegar
terraform apply -var="key_pair_name=claves-ml"
# → escribe "yes" cuando lo pida

# 6. Conectar por SSH (la IP la da el output de apply)
ssh -i "$env:USERPROFILE\.ssh\claves-ml.pem" ubuntu@<IP>

# 7. Ver el progreso del arranque automático
sudo tail -f /var/log/user-data.log

# 8. Verificar contenedores (una vez aparezca "DONE")
docker ps
```

---

## 8. Recursos que crea Terraform

| Recurso | Tipo AWS | Descripción |
|---|---|---|
| `fraud_server` | `aws_instance` | EC2 t3.large · Ubuntu 22.04 · 30GB gp3 |
| `fraud_sg` | `aws_security_group` | Abre puertos 22, 7474, 7687, 8000, 8088, 8888, 9870, 5678 |
| `ubuntu_22` | `data.aws_ami` | Busca la AMI más reciente de Ubuntu 22.04 de Canonical |
| `terraform_state` | `aws_s3_bucket` | Bucket para guardar el tfstate (con nombre aleatorio) |

---

## 9. Gestión del ciclo de vida

### Ver el estado actual de los recursos

```powershell
terraform show          # descripción completa de todos los recursos
terraform state list    # lista de recursos gestionados
```

### Aplicar cambios incrementales

Si modificas algún `.tf` (ej: añadir un puerto al Security Group), basta con ejecutar `terraform apply` de nuevo. Terraform calcula el diff y solo cambia lo necesario, sin recrear todo.

### Parar la instancia sin destruirla (ahorra crédito)

```powershell
# Parar la instancia (conserva disco y configuración, cobra ~$0.08/día por el EBS)
aws ec2 stop-instances --instance-ids <INSTANCE_ID>

# Volver a iniciarla (nueva IP pública cada vez)
aws ec2 start-instances --instance-ids <INSTANCE_ID>
```

### Destruir todo

```powershell
terraform destroy -var="key_pair_name=claves-ml"
# → escribe "yes"
```

Esto elimina la EC2, el Security Group y el bucket S3. **No se cobra nada** después de destruir.

> ⚠️ `terraform destroy` borra también el bucket S3 que guarda el Terraform state. Si tienes el state en ese bucket, guarda una copia antes.

---

## 10. Troubleshooting

### "No valid credential sources found"
Las credenciales AWS han caducado (~4 h en AWS Academy). Volver a AWS Academy → AWS Details → Show y pegar de nuevo los `$env:`.

### "Error: key pair not found"
El Key Pair `claves-ml` no existe en la cuenta AWS actual. Puede que el laboratorio se reiniciara desde cero. Crear un nuevo Key Pair en la consola AWS (ver sección 5) y repetir el `apply`.

### "Error acquiring the state lock"
Terraform dejó un lock en el state file. Ocurre si el proceso se interrumpió a la mitad:
```powershell
terraform force-unlock <LOCK_ID>
```

### La EC2 se crea pero los contenedores no arrancan
El `user_data` falló. Ver el log:
```bash
ssh -i ~/.ssh/claves-ml.pem ubuntu@<IP>
sudo cat /var/log/user-data.log
```
Buscar el paso donde falló y ejecutarlo manualmente.

### "Error: timeout while waiting for instance to become running"
La EC2 tardó más de lo esperado. No es un error real; la instancia probablemente siga arrancando. Esperar y volver a ejecutar `terraform apply` (no destruye nada, solo actualiza el state).
