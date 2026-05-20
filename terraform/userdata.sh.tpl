#!/bin/bash
# =============================================================================
# Script de inicialización EC2 — TFG Detección de Fraude
# Progreso: sudo tail -f /var/log/user-data.log
# =============================================================================
set -e
exec > /var/log/user-data.log 2>&1

echo "========================================"
echo " [1/6] Instalando Docker Engine"
echo "========================================"
apt-get update -y
apt-get install -y ca-certificates curl gnupg git awscli

# Instalar Docker via script oficial (incluye docker compose plugin)
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker

echo "========================================"
echo " [2/6] Clonando repositorio"
echo "========================================"
cd /home/ubuntu
git clone --branch "${repo_branch}" --single-branch "${repo_url}" app
chown -R ubuntu:ubuntu app
cd app

echo "========================================"
echo " [3/6] Configurando .env"
echo "========================================"
cat > /home/ubuntu/app/.env << 'ENVEOF'
MODEL_NAME=modelo_fraude_rf_final.joblib
NEO4J_AUTH=neo4j/password
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_URI=bolt://neo4j:7687
ENVEOF

echo "========================================"
echo " [4/6] Descargando modelo desde S3 (si aplica)"
echo "========================================"
%{ if model_s3_path != "" }
echo "Descargando modelo desde ${model_s3_path} ..."
aws s3 cp "${model_s3_path}" /home/ubuntu/app/models/modelo_fraude_rf_final.joblib
chown ubuntu:ubuntu /home/ubuntu/app/models/modelo_fraude_rf_final.joblib
echo "[OK] Modelo descargado"
%{ else }
echo "[INFO] Modelo incluido en el repositorio, no se descarga de S3"
%{ endif }

echo "========================================"
echo " [5/6] Creando red Docker compartida"
echo "========================================"
docker network create shared-ml-network || echo "[INFO] Red ya existia"

echo "========================================"
echo " [6/6] Levantando servicios Docker"
echo "========================================"
cd /home/ubuntu/app

# Hadoop primero (tarda más en inicializar)
docker compose -f infrastructure/hadoop/docker-compose.yml up -d
sleep 10

# Resto de servicios
docker compose -f infrastructure/api/docker-compose.yml    up -d
docker compose -f infrastructure/ml-env/docker-compose.yml up -d
docker compose -f infrastructure/n8n/docker-compose.yml    up -d

echo "========================================"
echo " DONE — Stack levantado correctamente"
echo " Ver estado: docker ps"
echo "========================================"
