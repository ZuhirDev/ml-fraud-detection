# Ubuntu 22.04 + Java 11 (repos apt vigentes, sin dependencias de CentOS EOL)
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HADOOP_VERSION=3.3.6
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
ENV HADOOP_HOME=/opt/hadoop
ENV HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop
ENV PATH=$PATH:/opt/hadoop/bin:/opt/hadoop/sbin

# Instalar Java 11 + utilidades básicas
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-11-jdk \
    curl wget openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Descargar e instalar Hadoop 3.3.6 desde el archivo oficial de Apache
RUN wget -q "https://archive.apache.org/dist/hadoop/common/hadoop-${HADOOP_VERSION}/hadoop-${HADOOP_VERSION}.tar.gz" \
         -O /tmp/hadoop.tar.gz \
    && tar -xzf /tmp/hadoop.tar.gz -C /opt/ \
    && mv /opt/hadoop-${HADOOP_VERSION} /opt/hadoop \
    && rm /tmp/hadoop.tar.gz

# Fijar JAVA_HOME en hadoop-env.sh para que los daemons lo encuentren
RUN echo "export JAVA_HOME=${JAVA_HOME}" >> $HADOOP_CONF_DIR/hadoop-env.sh

# Copiar configuraciones personalizadas
COPY conf/core-site.xml   $HADOOP_CONF_DIR/core-site.xml
COPY conf/hdfs-site.xml   $HADOOP_CONF_DIR/hdfs-site.xml
COPY conf/mapred-site.xml $HADOOP_CONF_DIR/mapred-site.xml
COPY conf/yarn-site.xml   $HADOOP_CONF_DIR/yarn-site.xml

# Script de arranque: formatea NameNode solo si es la primera vez
COPY scripts/start-hadoop.sh /start-hadoop.sh
RUN chmod +x /start-hadoop.sh

EXPOSE 9870 9000 8088 8042 19888

ENTRYPOINT ["/start-hadoop.sh"]
