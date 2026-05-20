# Bucket S3 para el Terraform state remoto
# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANTE: Este bucket debe crearse ANTES de hacer terraform init con el
# backend S3. Hazlo manualmente una vez:
#
#   aws s3 mb s3://fraud-tfg-state-XXXX --region us-east-1
#
# Luego sustituye el nombre en main.tf → backend "s3" → bucket = "fraud-tfg-state-XXXX"
# y descomenta el bloque backend.
#
# Si usas state local (Opción A en main.tf) no necesitas este fichero para nada,
# pero el bucket se crea de todas formas para tenerlo disponible.
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "terraform_state" {
  bucket = "fraud-tfg-state-${random_id.suffix.hex}"

  tags = {
    Name    = "fraud-tfg-terraform-state"
    Project = "TFG"
  }

  # Previene destrucción accidental del state
  lifecycle {
    prevent_destroy = true
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket_versioning" "state_versioning" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Bloquear acceso público al bucket del state
resource "aws_s3_bucket_public_access_block" "state_block" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
