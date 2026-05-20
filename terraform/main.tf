terraform {
  required_version = ">= 1.3"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # ─────────────────────────────────────────────────────────────────────────────
  # OPCIÓN A (por defecto): state LOCAL
  #   Funciona sin configuración adicional. Inconveniente: si cierras la sesión
  #   de AWS Academy sin hacer terraform destroy, el state se queda en tu máquina
  #   y necesitas guardarlo tú.
  #
  # OPCIÓN B: state en S3 (recomendado para sesiones de 4h de AWS Academy)
  #   Pasos previos:
  #     1. Crear manualmente el bucket en la consola AWS:
  #          aws s3 mb s3://fraud-tfg-state-XXXX --region us-east-1
  #     2. Sustituir "fraud-tfg-state-XXXX" por el nombre real del bucket
  #     3. Descomentar el bloque backend y comentar el bloque de arriba
  # ─────────────────────────────────────────────────────────────────────────────
  # backend "s3" {
  #   bucket = "fraud-tfg-state-XXXX"
  #   key    = "terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = "us-east-1"   # AWS Academy solo permite us-east-1
}
