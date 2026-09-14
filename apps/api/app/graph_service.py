# 시간 그래프 계산과 선택적 Neo4j HTTP 증분 저장

import json, os
from collections import Counter
from urllib.request import Request, urlopen


def enrich_graph(events, nodes, edges, target_id: str) -> dict:
    degree = Counter()
    for edge in edges: degree[edge["source"]] += 1; degree[edge["target"]] += 1
    maximum = max(degree.values(), default=1)
    centrality = {node: round(value / maximum, 3) for node, value in degree.items()}
    normalized = [" ".join(event.text.lower().split()) for event in events]
    repeated = 1 - len(set(normalized)) / max(len(normalized), 1)
    times = [event.occurred_at for event in events]
    window_platforms = len({event.platform for event in events if (max(times) - event.occurred_at).total_seconds() <= 900}) if times else 0
    concurrency = min(1.0, window_platforms / 3)
    persistence = persist_incremental(target_id, nodes, edges)
    return {"centrality": centrality, "repeated_phrase_score": round(repeated, 3), "cross_platform_concurrency": round(concurrency, 3), "persistence": persistence}


def persist_incremental(target_id: str, nodes: list[dict], edges: list[dict]) -> str:
    base = os.getenv("NEO4J_HTTP_URL", "")
    if not base: return "neo4j_not_configured"
    try:
        statements = []
        for node in nodes:
            statements.append({"statement": "MERGE (n:MobiusNode {id:$id}) SET n.type=$type,n.label=$label,n.updated_at=datetime()", "parameters": node})
        for edge in edges:
            statements.append({"statement": "MATCH (a:MobiusNode {id:$source}),(b:MobiusNode {id:$target}) MERGE (a)-[r:RELATES {kind:$kind}]->(b) SET r.last_seen=datetime()", "parameters": edge})
        request = Request(f"{base}/db/neo4j/tx/commit", data=json.dumps({"statements": statements}).encode(), headers={"Content-Type": "application/json", "Authorization": "Basic " + os.getenv("NEO4J_BASIC_AUTH", "")})
        with urlopen(request, timeout=3): pass
        return "neo4j_incremental"
    except Exception:
        return "neo4j_unavailable"
