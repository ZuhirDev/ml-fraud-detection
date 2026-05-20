import logging
import os
from pathlib import Path
import joblib
import pandas as pd
from dotenv import load_dotenv
from .schemas import Transaction

load_dotenv()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
MODEL_NAME = os.getenv("MODEL_NAME", "decision_tree_v1.joblib")
MODEL_PATH = BASE_DIR.parent / "models" / MODEL_NAME

MODEL_COLUMNS = [
    "amount",
    "old_balance_orig",
    "new_balance_orig",
    "old_balance_dest",
    "new_balance_dest",
    "in_degree_hist",
    "out_degree_hist",
    "orig_pagerank_hist",
    "dest_pagerank_hist",
    "type_CASH_IN",
    "type_CASH_OUT",
    "type_DEBIT",
    "type_PAYMENT",
    "type_TRANSFER",
]

TRANSACTION_TYPES = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]

def load_model(model_path: Path):
    try:
        logger.info("⏳ Cargando modelo desde %s...", model_path)
        model = joblib.load(model_path)
        logger.info("✅ Modelo cargado correctamente.")
        return model
    except Exception as error:
        logger.error("❌ Error al cargar el modelo: %s", error)
        return None

def build_prediction_dataframe(transaction: Transaction, grados: dict, pagerank: dict, comunidad: dict) -> pd.DataFrame:
    """
    Fusiona los datos de la petición (Pydantic) con las métricas extraídas en tiempo real 
    desde Neo4j y formatea las columnas de forma idéntica al entrenamiento.
    """
    # 1. Mapear datos operativos usando snake_case del esquema
    mapped_data = {
        "amount": transaction.amount,
        "old_balance_orig": transaction.old_balance_orig,
        "new_balance_orig": transaction.new_balance_orig,
        "old_balance_dest": transaction.old_balance_dest,
        "new_balance_dest": transaction.new_balance_dest,
    }
    
    # 2. Inyectar variables topológicas obtenidas dinámicamente
    mapped_data["in_degree_hist"] = grados["in_degree_hist"]
    mapped_data["out_degree_hist"] = grados["out_degree_hist"]
    mapped_data["orig_pagerank_hist"] = pagerank["orig_pagerank_hist"]
    mapped_data["dest_pagerank_hist"] = pagerank["dest_pagerank_hist"]
    # Nota: same_louvain_community_hist no se agrega al DataFrame final si tu 
    # lista de columnas esperadas del modelo (MODEL_COLUMNS) no lo requiere.

    # 3. One-Hot Encoding manual del tipo de transacción
    current_type = transaction.type.value.upper()
    for t_type in TRANSACTION_TYPES:
        mapped_data[f"type_{t_type}"] = 1.0 if current_type == t_type else 0.0

    # Retorna garantizando el orden matemático estricto exigido por el árbol de decisión
    return pd.DataFrame([mapped_data], columns=MODEL_COLUMNS)

def format_prediction_result(prediction: int, probability: float) -> dict:
    return {
        "status": "success",
        "is_fraud": prediction,
        "fraud_probability": round(probability, 4),
        "action": "BLOCK_TRANSACTION" if prediction == 1 else "ALLOW_TRANSACTION",
    }

modelo_fraude = load_model(MODEL_PATH)