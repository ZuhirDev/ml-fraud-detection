from enum import Enum
from pydantic import BaseModel, Field

class TransactionType(str, Enum):
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"
    DEBIT = "DEBIT"
    PAYMENT = "PAYMENT"
    TRANSFER = "TRANSFER"

class Transaction(BaseModel):
    # Identificadores indispensables para las queries de Neo4j
    nameOrig: str = Field(..., example="C1305486145")
    nameDest: str = Field(..., example="C553264065")
    
    # Datos operativos
    amount: float
    old_balance_orig: float
    new_balance_orig: float
    old_balance_dest: float
    new_balance_dest: float
    type: TransactionType

class PredictionResponse(BaseModel):
    status: str
    is_fraud: int
    fraud_probability: float
    action: str