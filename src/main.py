from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import joblib
import logging

# 1️⃣ Configuramos logging
logging.basicConfig(
    level=logging.INFO,  # Cambiar a DEBUG para más detalle
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 2️⃣ Inicializamos FastAPI
app = FastAPI(title="Fraud Detection API 🚀")

# 3️⃣ Definimos el modelo de datos con Pydantic
class Transaction(BaseModel):
    amount: float
    old_balance_orig: float
    new_balance_orig: float
    old_balance_dest: float
    new_balance_dest: float
    orig_out_degree: float
    orig_pagerank: float
    orig_community: float
    dest_in_degree: float
    dest_pagerank: float
    dest_community: float
    type_CASH_IN: float
    type_CASH_OUT: float
    type_DEBIT: float
    type_PAYMENT: float
    type_TRANSFER: float

# 4️⃣ Cargamos el modelo completo (modelo + scaler + features + umbral)
logger.info("🔹 Cargando modelo de fraude...")
datos_cargados = joblib.load("../models/modelo_fraude_rf_final.joblib")
modelo = datos_cargados['modelo']
scaler = datos_cargados['scaler']
features_esperadas = datos_cargados['features']
umbral = datos_cargados['umbral']
logger.info("✅ Modelo cargado correctamente")

# 5️⃣ Endpoint de health check
@app.get("/")
def health_check():
    logger.info("🔹 Health check en '/'")
    return {"message": "Welcome to the Fraud Detection API! 🚀"}

@app.get("/health")
def health_check_detail():
    logger.info("🔹 Health check en '/health'")
    return {"status": "ok", "message": "API is running ✅"}

# 6️⃣ Endpoint de predicción
@app.post("/predict")
async def predict(transaction: Transaction):
    logger.info(f"🔹 Recibida transacción: {transaction.dict()}")

    try:
        # Convertimos el input a DataFrame
        data = pd.DataFrame([transaction.dict()])
        logger.debug(f"🔹 DataFrame inicial:\n{data}")

        # Nos aseguramos del orden correcto de columnas
        data = data[features_esperadas]
        logger.debug(f"🔹 DataFrame ordenado:\n{data}")

        # Escalamos las features
        data_scaled = scaler.transform(data)
        logger.debug(f"🔹 DataFrame escalado:\n{data_scaled}")

        # Probabilidad de fraude
        prob = modelo.predict_proba(data_scaled)[0][1]
        logger.info(f"⚠️ Probabilidad de fraude calculada: {prob:.4f}")

        # Aplicamos el umbral guardado
        pred = int(prob >= umbral)
        status_emoji = "❌" if pred else "✅"
        logger.info(f"{status_emoji} Predicción final: {pred} usando umbral {umbral}")

        return {
            "fraud_probability": round(prob, 4),
            "fraud_prediction": pred,
            "threshold_used": umbral
        }

    except Exception as e:
        logger.error(f"🔥 Error al procesar la transacción: {e}", exc_info=True)
        return {"error": str(e)}