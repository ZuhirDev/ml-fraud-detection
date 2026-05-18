#!/bin/bash
set -e

export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HOME=/opt/hadoop
export PATH=$PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin

NAMENODE_DIR=/opt/hadoop/data/nameNode

echo "========================================"
echo " Iniciando Hadoop Single-Node"
echo "========================================"

# Formatear NameNode solo si no existe ya
if [ ! -d "$NAMENODE_DIR/current" ]; then
    echo "[INFO] Primera ejecución: formateando NameNode..."
    hdfs namenode -format -force -nonInteractive
    echo "[INFO] NameNode formateado correctamente."
else
    echo "[INFO] NameNode ya formateado, omitiendo formato."
fi

# Arrancar HDFS
echo "[INFO] Arrancando NameNode..."
hdfs namenode &
NAMENODE_PID=$!

echo "[INFO] Arrancando DataNode..."
hdfs datanode &
DATANODE_PID=$!

# Esperar a que el NameNode esté listo (hasta 60s)
echo "[INFO] Esperando a que HDFS esté disponible..."
for i in $(seq 1 12); do
    if hdfs dfs -ls / > /dev/null 2>&1; then
        echo "[INFO] HDFS listo."
        break
    fi
    echo "[INFO] Intento $i/12 — esperando HDFS..."
    sleep 5
done

# Crear directorios base en HDFS
echo "[INFO] Creando estructura de directorios en HDFS..."
hdfs dfs -mkdir -p /user/hadoop
hdfs dfs -mkdir -p /data/raw
hdfs dfs -mkdir -p /data/processed
hdfs dfs -mkdir -p /data/fraud-results
hdfs dfs -chmod -R 777 /data
hdfs dfs -chmod -R 777 /user
echo "[INFO] Directorios HDFS creados: /data/raw, /data/processed, /data/fraud-results"

# Arrancar YARN
echo "[INFO] Arrancando YARN ResourceManager..."
yarn resourcemanager &
RM_PID=$!

echo "[INFO] Arrancando YARN NodeManager..."
yarn nodemanager &
NM_PID=$!

echo "========================================"
echo " Hadoop arrancado correctamente"
echo "  NameNode UI  -> http://localhost:9870"
echo "  YARN UI      -> http://localhost:8088"
echo "  HDFS RPC     -> hdfs://hadoop:9000"
echo "========================================"

# Mantener el contenedor vivo (esperar a cualquier proceso hijo)
wait
