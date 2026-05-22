variable "key_pair_name" {
  description = "Nombre del Key Pair creado en la consola AWS (EC2 → Key Pairs → Create key pair)"
  type        = string
  # No tiene default — Terraform lo preguntará al hacer apply si no lo pasas
}

variable "instance_type" {
  description = "Tipo de instancia. t3.large (8 GB RAM) es el mínimo recomendado para todo el stack"
  type        = string
  default     = "t3.large"
}

variable "allowed_ip" {
  description = "CIDR desde el que se permite acceso (SSH + servicios). Obtén tu IP con: curl ifconfig.me"
  type        = string
  default     = "0.0.0.0/0"   # Abierto para demo — en prod cambiar a "X.X.X.X/32"
}

variable "repo_url" {
  description = "URL pública del repositorio GitHub del proyecto"
  type        = string
  default     = "https://github.com/ZuhirDev/ml-fraud-detection.git"
  # IMPORTANTE: el repo debe ser público O usar un token en la URL:
  #   "https://TOKEN@github.com/TU_USUARIO/ml-fraud-detection.git"
}

variable "repo_branch" {
  description = "Rama de GitHub a clonar en la EC2"
  type        = string
  default     = "main"
}

variable "model_s3_path" {
  description = <<-EOT
    Ruta S3 del modelo .joblib si es demasiado grande para GitHub (>100 MB).
    Ejemplo: "s3://mi-bucket/models/modelo_fraude_rf_final.joblib"
    Dejar vacío si el modelo está en el repo de GitHub.
  EOT
  type        = string
  default     = ""
}
