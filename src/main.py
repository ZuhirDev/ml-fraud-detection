import os
import logging
from fastapi import FastAPI, HTTPException
from neo4j import GraphDatabase
from dotenv import load_dotenv

from .predict import build_prediction_dataframe, format_prediction_result, modelo_fraude
from .schemas import PredictionResponse, Transaction
from .queries import obtener_grados_realtime, obtener_pagerank_realtime, obtener_comunidad_realtime

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fraud Detection API 🚀")

# Inicialización y gestión del ciclo de vida del Driver de Neo4j
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
driver = None

@app.on_event("startup")
def startup_event():
    global driver
    logger.info("🔌 Inicializando pool de conexiones globales a Neo4j...")
    driver = GraphDatabase.driver(URI, auth=AUTH)
    logger.info("✅ Driver de Neo4j conectado y listo.")

@app.on_event("shutdown")
def shutdown_event():
    global driver
    if driver:
        logger.info("🔌 Cerrando conexiones activas de Neo4j...")
        driver.close()
        logger.info("🛑 Pool de grafos liberado limpiamente.")

@app.get("/", response_model=dict)
def root() -> dict:
    logger.info("🔹 Health check en '/'")
    return {"message": "Welcome to the Fraud Detection API! 🚀"}

@app.get("/health", response_model=dict)
def health_check() -> dict:
    logger.info("🔹 Health check en '/health'")
    return {"status": "ok", "message": "API and Graph driver are running smoothly ✅"}

@app.post("/predict", response_model=PredictionResponse)
async def predict(transaction: Transaction) -> dict:
    if modelo_fraude is None:
        logger.error("❌ Intento de predicción fallido: el modelo de ML no está cargado.")
        raise HTTPException(status_code=500, detail="El modelo no está disponible en el servidor.")

    try:
        logger.info("🔮 Recibiendo transacción: %s -> %s para evaluación estructural...", transaction.nameOrig, transaction.nameDest)
        
        # 1. Extracción paralela/milisegundos desde la DB de grafos
        grados = obtener_grados_realtime(driver, transaction.nameOrig, transaction.nameDest)
        pagerank = obtener_pagerank_realtime(driver, transaction.nameOrig, transaction.nameDest)
        comunidad = obtener_comunidad_realtime(driver, transaction.nameOrig, transaction.nameDest)
        
        # 2. Reconstrucción del DataFrame adaptado al modelo
        df_predict = build_prediction_dataframe(transaction, grados, pagerank, comunidad)

        # 3. Inferencia mediante el Árbol de Decisión
        prediction = int(modelo_fraude.predict(df_predict)[0])
        probability = float(modelo_fraude.predict_proba(df_predict)[0][1])

        logger.info(
            "✅ Predicción realizada con éxito. Resultado: %s, Probabilidad: %.4f",
            prediction,
            probability,
        )

        return format_prediction_result(prediction, probability)
        
    except Exception as error:
        logger.error("❌ Error durante la tubería de inferencia: %s", error)
        raise HTTPException(status_code=400, detail=f"Error al procesar los datos: {error}")