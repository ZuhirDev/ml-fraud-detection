import os
import time
import logging
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)
load_dotenv(find_dotenv())

def obtener_grados_realtime(driver, name_orig: str, name_dest: str) -> dict:
    query = """
    CALL () {
        MATCH (o:Account {id: $nameOrig})
        USING INDEX o:Account(id)
        RETURN toFloat(count{(o)-[:TRANSACTION]->()}) AS out_degree
    }
    CALL () {
        MATCH (d:Account {id: $nameDest})
        USING INDEX d:Account(id)
        RETURN toFloat(count{()<-[:TRANSACTION]-(d)}) AS in_degree
    }
    RETURN out_degree AS out_degree_hist, in_degree AS in_degree_hist
    """
    start_time = time.time()
    try:
        with driver.session() as session:
            result = session.run(query, nameOrig=name_orig, nameDest=name_dest)
            record = result.single()
            if record:
                return {
                    "out_degree_hist": record["out_degree_hist"],
                    "in_degree_hist": record["in_degree_hist"]
                }
            return {"out_degree_hist": 0.0, "in_degree_hist": 0.0}
    except Exception as e:
        logger.error(f"❌ Error al obtener grados de Neo4j en tiempo real: {e}")
        return {"out_degree_hist": 0.0, "in_degree_hist": 0.0}
    finally:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"⚡ Grados Neo4j obtenidos en {elapsed_ms:.2f} ms")

def obtener_pagerank_realtime(driver, name_orig: str, name_dest: str) -> dict:
    query = """
    OPTIONAL MATCH (o:Account {id: $nameOrig})
    USING INDEX o:Account(id)
    WITH o
    OPTIONAL MATCH (o)-[r_orig:TRANSACTION]-()
    WITH o, r_orig ORDER BY r_orig.step DESC LIMIT 1
    WITH coalesce(r_orig.orig_pagerank_hist, 1.0) AS orig_p
    
    OPTIONAL MATCH (d:Account {id: $nameDest})
    USING INDEX d:Account(id)
    WITH orig_p, d
    OPTIONAL MATCH (d)-[r_dest:TRANSACTION]-()
    WITH orig_p, r_dest ORDER BY r_dest.step DESC LIMIT 1
    WITH orig_p, coalesce(r_dest.dest_pagerank_hist, 1.0) AS dest_p
    
    RETURN toFloat(orig_p) AS orig_pagerank_hist, toFloat(dest_p) AS dest_pagerank_hist
    """
    start_time = time.time()
    try:
        with driver.session() as session:
            result = session.run(query, nameOrig=name_orig, nameDest=name_dest)
            record = result.single()
            if record:
                return {
                    "orig_pagerank_hist": record["orig_pagerank_hist"],
                    "dest_pagerank_hist": record["dest_pagerank_hist"]
                }
            return {"orig_pagerank_hist": 1.0, "dest_pagerank_hist": 1.0}
    except Exception as e:
        logger.error(f"❌ Error al obtener PageRank en tiempo real: {e}")
        return {"orig_pagerank_hist": 1.0, "dest_pagerank_hist": 1.0}
    finally:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"⚡ PageRank Neo4j obtenido en {elapsed_ms:.2f} ms")

def obtener_comunidad_realtime(driver, name_orig: str, name_dest: str) -> dict:
    query = """
    OPTIONAL MATCH (o:Account {id: $nameOrig})
    USING INDEX o:Account(id)
    MATCH (o)-[r:TRANSACTION]->(d:Account {id: $nameDest})
    USING INDEX d:Account(id)
    WITH r ORDER BY r.step DESC LIMIT 5
    WITH max(coalesce(r.same_louvain_community_hist, 0)) AS max_same_comm
    RETURN toFloat(max_same_comm) AS same_louvain_community_hist
    """
    start_time = time.time()
    try:
        with driver.session() as session:
            result = session.run(query, nameOrig=name_orig, nameDest=name_dest)
            record = result.single()
            if record:
                return {"same_louvain_community_hist": record["same_louvain_community_hist"]}
            return {"same_louvain_community_hist": 0.0}
    except Exception as e:
        logger.error(f"❌ Error al obtener comunidad Louvain en tiempo real: {e}")
        return {"same_louvain_community_hist": 0.0}
    finally:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"⚡ Louvain Neo4j obtenido en {elapsed_ms:.2f} ms")