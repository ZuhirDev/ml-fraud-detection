import os
import logging
from fastapi import FastAPI, HTTPException, status
from neo4j import GraphDatabase
from dotenv import load_dotenv

from .predict import build_prediction_dataframe, format_prediction_result, modelo_fraude
from .schemas import PredictionResponse, Transaction
from .queries import obtener_grados_realtime, obtener_pagerank_realtime

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fraud Detection API 🚀")

URI = os.getenv("NEO4J_URI")
AUTH = (os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
driver = None

@app.on_event("startup")
def startup_event():
    global driver
    logger.info("🔌 Inicializando pool de conexiones globales a Neo4j...")
    try:
        driver = GraphDatabase.driver(URI, auth=AUTH)
        driver.verify_connectivity()
        logger.info("✅ Driver de Neo4j conectado y verificado con éxito.")
    except Exception as e:
        logger.critical("❌ No se pudo conectar a Neo4j al iniciar la API: %s", e)

@app.on_event("shutdown")
def shutdown_event():
    global driver
    if driver:
        logger.info("🔌 Cerrando conexiones activas de Neo4j...")
        driver.close()
        logger.info("🛑 Pool de grafos liberado limpiamente.")

@app.get("/", response_model=dict, tags=["Health"])
def root() -> dict:
    logger.info("🔹 Health check en '/'")
    return {"message": "Welcome to the Fraud Detection API! 🚀"}

@app.get("/health", response_model=dict, tags=["Health"])
def health_check() -> dict:
    logger.info("🔹 Health check en '/health'")
    return {"status": "ok", "message": "API and Graph driver are running smoothly ✅"}

@app.post("/predict", response_model=PredictionResponse, status_code=status.HTTP_200_OK, tags=["Inference"])
async def predict(transaction: Transaction) -> dict:
    if modelo_fraude is None:
        logger.error("❌ Intento de predicción fallido: el modelo de ML no está cargado.")
        raise HTTPException(status_code=500, detail="El modelo no está disponible en el servidor.")

    print("Transaccion recibida completa: ", transaction.dict())
    try:
        logger.info("🔮 Evaluando transacción estructural: %s -> %s", transaction.nameOrig, transaction.nameDest)
        
        grados = obtener_grados_realtime(driver, transaction.nameOrig, transaction.nameDest)
        pagerank = obtener_pagerank_realtime(driver, transaction.nameOrig, transaction.nameDest)
             
        df_predict = build_prediction_dataframe(transaction, grados, pagerank)

        prediction = int(modelo_fraude.predict(df_predict)[0])
        probability = float(modelo_fraude.predict_proba(df_predict)[0][1])

        logger.info(
            "✅ Inferencia completada. Resultado: %s | Probabilidad de Fraude: %.4f",
            "FRAUDE DETECTADO" if prediction == 1 else "LEGÍTIMA",
            probability,
        )

        return format_prediction_result(prediction, probability)
        
    except Exception as error:
        logger.error("❌ Error en el pipeline de inferencia en tiempo real: %s", error)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail=f"Error al procesar la predicción: {str(error)}"
        )