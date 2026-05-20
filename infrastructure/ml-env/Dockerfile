FROM python:3.10-slim

# Evitar archivos .pyc y buffering en logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV JUPYTER_ENABLE_LAB=yes

# Java necesario para PySpark (JAVA_HOME se fija después de instalar)
WORKDIR /app

# Java (PySpark) + libgomp1 (LightGBM) + procps (ps que usan scripts de PySpark)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    procps \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf "$(dirname $(dirname $(readlink -f $(which java))))" /opt/java

ENV JAVA_HOME=/opt/java
ENV PYSPARK_PYTHON=python3

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Configuración de JupyterLab (mantenemos tu excelente configuración)
RUN jupyter lab --generate-config && \
    echo "c.ServerApp.ip = '0.0.0.0'" >> /root/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.port = 8888" >> /root/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.open_browser = False" >> /root/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.allow_root = True" >> /root/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.token = ''" >> /root/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.password = ''" >> /root/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.root_dir = '/app'" >> /root/.jupyter/jupyter_lab_config.py

EXPOSE 8888

CMD ["jupyter", "lab", "--config=/root/.jupyter/jupyter_lab_config.py"]