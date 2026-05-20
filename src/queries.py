import os
import time
import logging
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)
load_dotenv(find_dotenv())

def obtener_grados_realtime(driver, name_orig: str, name_dest: str) -> dict:
    """
    Calcula in_degree_hist y out_degree_hist en tiempo real basándose 
    en el estado actual del grafo de Neo4j.
    """
    query = """
    // 1. Encontrar la cuenta de origen y contar todas sus transacciones salientes históricas
    OPTIONAL MATCH (o:Account {id: $nameOrig})-[t_out:TRANSACTION]->()
    WITH count(t_out) AS out_degree_hist
    
    // 2. Encontrar la cuenta de destino y contar todas sus transacciones entrantes históricas
    OPTIONAL MATCH (d:Account {id: $nameDest})<-[t_in:TRANSACTION]-()
    
    // 3. Devolver los resultados consolidados convertidos a flotante para el modelo de ML
    RETURN 
        toFloat(out_degree_hist) AS out_degree_hist, 
        toFloat(count(t_in)) AS in_degree_hist
    """
    start_time = time.time()
    try:
        with driver.session() as session:
            result = session.run(query, nameOrig=name_orig, nameDest=name_dest)
            record = result.single()
            if record:
                grados = {
                    "out_degree_hist": record["out_degree_hist"],
                    "in_degree_hist": record["in_degree_hist"]
                }
            else:
                grados = {"out_degree_hist": 0.0, "in_degree_hist": 0.0}
                
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"⚡ Grados Neo4j obtenidos en {elapsed_ms:.2f} ms")
            return grados
    except Exception as e:
        logger.error(f"❌ Error al obtener grados de Neo4j en tiempo real: {e}")
        return {"out_degree_hist": 0.0, "in_degree_hist": 0.0}


def obtener_pagerank_realtime(driver, name_orig: str, name_dest: str) -> dict:
    """
    Recupera el último PageRank histórico registrado en las transacciones previas
    para el nodo origen y el nodo destino de forma ultra rápida.
    """
    query = """
    // 1. Obtener el PageRank más reciente del origen (buscando en sus transacciones pasadas)
    OPTIONAL MATCH (o:Account {id: $nameOrig})-[r_orig:TRANSACTION]-()
    WITH r_orig ORDER BY r_orig.step DESC LIMIT 1
    WITH coalesce(r_orig.orig_pagerank_hist, 1.0) AS orig_pagerank_hist
    
    // 2. Obtener el PageRank más reciente del destino (buscando en sus transacciones pasadas)
    OPTIONAL MATCH (d:Account {id: $nameDest})-[r_dest:TRANSACTION]-()
    WITH orig_pagerank_hist, r_dest ORDER BY r_dest.step DESC LIMIT 1
    WITH orig_pagerank_hist, coalesce(r_dest.dest_pagerank_hist, 1.0) AS dest_pagerank_hist
    
    // 3. Retornar ambos valores estructurados como flotantes
    RETURN 
        toFloat(orig_pagerank_hist) AS orig_pagerank_hist,
        toFloat(dest_pagerank_hist) AS dest_pagerank_hist
    """
    start_time = time.time()
    try:
        with driver.session() as session:
            result = session.run(query, nameOrig=name_orig, nameDest=name_dest)
            record = result.single()
            if record:
                valores = dict(record)
            else:
                valores = {"orig_pagerank_hist": 1.0, "dest_pagerank_hist": 1.0}
                
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"⚡ PageRank Neo4j obtenido en {elapsed_ms:.2f} ms")
            return valores
    except Exception as e:
        logger.error(f"❌ Error al obtener PageRank en tiempo real: {e}")
        return {"orig_pagerank_hist": 1.0, "dest_pagerank_hist": 1.0}


def obtener_comunidad_realtime(driver, name_orig: str, name_dest: str) -> dict:
    """
    Evalúa si el origen y el destino ya compartían comunidad Louvain en 
    sus interacciones históricas registradas en el grafo.
    """
    query = """
    // 1. Buscar transacciones previas directas entre este origen y este destino
    OPTIONAL MATCH (o:Account {id: $nameOrig})-[r:TRANSACTION]->(d:Account {id: $nameDest})
    WITH r ORDER BY r.step DESC LIMIT 5
    
    // 2. Agregar si en alguna de ellas compartían comunidad
    WITH max(coalesce(r.same_louvain_community_hist, 0)) AS max_same_comm
    
    // 3. Retornar el valor final como flotante
    RETURN toFloat(max_same_comm) AS same_louvain_community_hist
    """
    start_time = time.time()
    try:
        with driver.session() as session:
            result = session.run(query, nameOrig=name_orig, nameDest=name_dest)
            record = result.single()
            if record:
                valores = dict(record)
            else:
                valores = {"same_louvain_community_hist": 0.0}
                
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"⚡ Louvain Neo4j obtenido en {elapsed_ms:.2f} ms")
            return valores
    except Exception as e:
        logger.error(f"❌ Error al obtener comunidad Louvain en tiempo real: {e}")
        return {"same_louvain_community_hist": 0.0}