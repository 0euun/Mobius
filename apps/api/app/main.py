import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from urllib.parse import urlencode
import os

from .analysis import analyze_events, build_evidence_manifest, load_events
from .auth import authorization_url, issue_token, oauth_profile, provider_status
from .evidence import build_evidence_zip
from .graph_service import enrich_graph
from .model_runtime import MODEL_DIR, classifier
from .multimodal import analyze_image
from .naver_connector import collect as collect_naver, status as naver_status
from .video import analyze_video_stub
from .youtube_connector import collect as collect_youtube, status as youtube_status
from .multilabel_runtime import multilabel_classifier
from .security import PRINCIPALS, Principal, require_principal, require_role
from .storage import (
    alert_history,
    assert_target_access,
    audit,
    audit_history,
    create_target,
    delete_target,
    evidence_history,
    initialize,
    ingest_event,
    ingested_events,
    notification_allowed,
    notification_history,
    record_alert,
    record_evidence,
    record_notification,
    retention_policy,
    resolve_identity,
    get_rule,
    save_rule,
    save_image_fingerprint,
    similar_image_fingerprints,
    tenant_targets,
    update_target,
)
from .notifications import dispatch
from .schemas import DashboardResponse, EvidenceManifest, EventResponse, GraphResponse, HealthResponse, IngestEventRequest, MonitoringRuleRequest, NaverSyncRequest, RiskSummary, TargetCreateRequest, TargetUpdateRequest, YouTubeSyncRequest

app = FastAPI(title="Mobius API", version="0.2.0", description="집단 온라인 공격 조기경보 서비스 API")
cors_origins = [origin.strip().rstrip("/") for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])
DATA_PATH = Path(__file__).parent / "data" / "demo_events.jsonl"

@app.on_event("startup")
def startup() -> None: initialize()


def target_events(target_id: str, tenant_slug: str | None = None) -> list[EventResponse]:
    events = [event for event in load_events(DATA_PATH) if event.target_ref == target_id]
    if tenant_slug:
        stored = [EventResponse(event_id=row["event_id"], occurred_at=row["occurred_at"], platform=row["platform"], author_ref=row["author_ref"], target_ref=target_id, text=row["text"], hashtags=row.get("hashtags", []), engagement={"likes": row.get("likes", 0), "shares": row.get("shares", 0), "comments": row.get("comments", 0)}) for row in ingested_events(tenant_slug, target_id)]
        by_id = {event.event_id: event for event in [*events, *stored]}
        events = sorted(by_id.values(), key=lambda event: event.occurred_at)
    if not events:
        raise HTTPException(status_code=404, detail="분석 대상을 찾을 수 없습니다.")
    return events


def authorize_target(principal: Principal, target_id: str) -> None:
    try:
        assert_target_access(principal.tenant_slug, target_id)
    except PermissionError as error:
        raise HTTPException(status_code=404, detail="분석 대상을 찾을 수 없습니다.") from error


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(UTC))


@app.get("/v1/model-status", tags=["system"])
def model_status() -> dict[str, str]:
    return {"status": classifier.status, "model_path": str(MODEL_DIR), "error": classifier.error or ""}


@app.get("/v1/me", tags=["auth"])
def me(principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict[str, str]:
    return {"role": principal.role, "tenant_id": principal.tenant_slug, "subject": principal.subject}


@app.get("/v1/targets/{target_id}/alerts", tags=["alerts"])
def alerts(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    """현재 알림 상태를 조회한다. 이 GET 요청은 외부 발송을 만들지 않는다."""
    authorize_target(principal, target_id)
    risk = analyze_events(target_events(target_id, principal.tenant_slug))
    return {
        "target_id": target_id,
        "severity": risk.stage.value,
        "eligible": notification_allowed(principal.tenant_slug, target_id, risk.stage.value),
        "cooldown_minutes": int(os.getenv("MOBIUS_ALERT_COOLDOWN_MINUTES", "30")),
    }


@app.post("/v1/targets/{target_id}/alerts:dispatch", tags=["alerts"])
def dispatch_alert(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    authorize_target(principal, target_id)
    risk = analyze_events(target_events(target_id, principal.tenant_slug))
    message = risk.rationale[0] if risk.rationale else "위험 신호가 없습니다."
    if not notification_allowed(principal.tenant_slug, target_id, risk.stage.value):
        audit(principal.tenant_slug, principal.subject, "alert.bundled", f"target:{target_id}")
        return {"target_id": target_id, "tenant_id": principal.tenant_slug, "severity": risk.stage.value, "status": "bundled", "message": "동일 위험 단계의 알림 쿨다운(30분)이 적용되어 묶음 처리했습니다."}
    delivery = dispatch(message)
    item = record_alert(principal.tenant_slug, target_id, risk.stage.value, message, delivery.get("status", "simulated"))
    for result in delivery["deliveries"]:
        record_notification(principal.tenant_slug, target_id, result["channel"], result["status"], result["attempts"], result["detail"])
    audit(principal.tenant_slug, principal.subject, "alert.created", f"target:{target_id}/alert:{item.id}")
    return {"id": item.id, "target_id": target_id, "tenant_id": principal.tenant_slug, "role": principal.role, "severity": risk.stage.value, "channels": ["dashboard", "email"], "message": message, "delivery": delivery}

@app.get("/v1/auth/providers", tags=["auth"])
def auth_providers() -> dict:
    return {"oauth": provider_status(), "demo_login": {"enabled": True, "note": "외부 OAuth 설정 전 데모 전용"}}


@app.post("/v1/auth/demo-login", tags=["auth"])
def demo_login(x_api_key: str | None = Header(default=None)) -> dict:
    principal = PRINCIPALS.get(x_api_key or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="유효한 데모 API Key가 필요합니다.")
    return {"access_token": issue_token(principal.subject, principal.role, principal.tenant_slug), "token_type": "bearer", "role": principal.role, "tenant_id": principal.tenant_slug, "expires_in": 3600}


@app.get("/v1/auth/login/{provider}", tags=["auth"])
def oauth_login(provider: str) -> dict:
    return {"provider": provider, "authorization_url": authorization_url(provider)}


@app.get("/v1/auth/callback/{provider}", tags=["auth"])
def oauth_callback(provider: str, code: str) -> dict:
    statuses = provider_status()
    if provider not in statuses or not statuses[provider]["configured"]:
        raise HTTPException(status_code=503, detail="OAuth 공급자 설정이 필요합니다.")
    subject, email = oauth_profile(provider, code)
    identity = resolve_identity(provider, f"{provider}:{subject}", email)
    token = issue_token(identity.provider_subject, identity.role, identity.tenant_slug)
    audit(identity.tenant_slug, identity.provider_subject, "auth.oauth_login", f"provider:{provider}")
    web_url = os.getenv("WEB_APP_URL", "http://localhost:3000")
    return RedirectResponse(f"{web_url}/?{urlencode({'token': token, 'role': identity.role, 'tenant': identity.tenant_slug})}")


@app.get("/v1/targets/{target_id}/alerts/history", tags=["alerts"])
def alerts_history(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> list[dict]:
    authorize_target(principal, target_id)
    return [{"id": item.id, "severity": item.severity, "message": item.message, "delivery_status": item.delivery_status, "created_at": item.created_at} for item in alert_history(principal.tenant_slug, target_id)]


@app.get("/v1/targets/{target_id}/notifications/history", tags=["alerts"])
def get_notification_history(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> list[dict]:
    authorize_target(principal, target_id)
    return [{"id": item.id, "channel": item.channel, "status": item.status, "attempts": item.attempts, "detail": item.detail, "created_at": item.created_at} for item in notification_history(principal.tenant_slug, target_id)]


@app.get("/v1/retention-policy", tags=["privacy"])
def get_retention_policy(principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    return {"tenant_id": principal.tenant_slug, **retention_policy()}


@app.get("/v1/targets", tags=["targets"])
def get_targets(principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> list[dict]:
    return [{"target_id": item.target_id, "display_name": item.display_name} for item in tenant_targets(principal.tenant_slug)]


@app.get("/v1/connectors/youtube/status", tags=["connectors"])
def youtube_connector_status(principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    return youtube_status()


@app.get("/v1/connectors/naver-search/status", tags=["connectors"])
def naver_connector_status(principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    return naver_status()


@app.post("/v1/targets/{target_id}/connectors/youtube/sync", tags=["connectors"])
def sync_youtube(target_id: str, payload: YouTubeSyncRequest, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    authorize_target(principal, target_id)
    if not youtube_status()["configured"]:
        raise HTTPException(status_code=503, detail="YOUTUBE_API_KEY 설정이 필요합니다.")
    try:
        events = collect_youtube(payload.query, target_id, payload.max_videos, payload.max_comments_per_video)
    except Exception as error:
        raise HTTPException(status_code=502, detail="YouTube API 동기화에 실패했습니다.") from error
    stored = 0
    for event in events:
        ingest_event(principal.tenant_slug, target_id, event); stored += 1
    audit(principal.tenant_slug, principal.subject, "connector.youtube_sync", f"target:{target_id}/events:{stored}")
    return {"provider": "youtube", "target_id": target_id, "query": payload.query, "received": len(events), "stored": stored, "storage": "masked_only"}


@app.post("/v1/targets/{target_id}/connectors/naver-search/sync", tags=["connectors"])
def sync_naver(target_id: str, payload: NaverSyncRequest, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    authorize_target(principal, target_id)
    if not naver_status()["configured"]: raise HTTPException(status_code=503, detail="NAVER_CLIENT_ID/SECRET 설정이 필요합니다.")
    try: events = collect_naver(payload.query, payload.sources, payload.display, target_id)
    except ValueError as error: raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error: raise HTTPException(status_code=502, detail="NAVER Search API 동기화에 실패했습니다.") from error
    for event in events: ingest_event(principal.tenant_slug, target_id, event)
    audit(principal.tenant_slug, principal.subject, "connector.naver_search_sync", f"target:{target_id}/events:{len(events)}")
    return {"provider": "naver_search", "target_id": target_id, "query": payload.query, "sources": payload.sources, "received": len(events), "stored": len(events), "storage": "masked_only"}


@app.post("/v1/targets", tags=["targets"])
def post_target(payload: TargetCreateRequest, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    try: item = create_target(principal.tenant_slug, payload.target_id, payload.display_name)
    except ValueError as error: raise HTTPException(status_code=409, detail=str(error)) from error
    audit(principal.tenant_slug, principal.subject, "target.created", f"target:{item.target_id}")
    return {"target_id": item.target_id, "display_name": item.display_name}


@app.patch("/v1/targets/{target_id}", tags=["targets"])
def patch_target(target_id: str, payload: TargetUpdateRequest, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    try: item = update_target(principal.tenant_slug, target_id, payload.display_name)
    except ValueError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    audit(principal.tenant_slug, principal.subject, "target.updated", f"target:{target_id}")
    return {"target_id": item.target_id, "display_name": item.display_name}


@app.delete("/v1/targets/{target_id}", status_code=204, tags=["targets"])
def remove_target(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> None:
    try: deleted = delete_target(principal.tenant_slug, target_id)
    except ValueError as error: raise HTTPException(status_code=400, detail=str(error)) from error
    if not deleted: raise HTTPException(status_code=404, detail="분석 대상을 찾을 수 없습니다.")
    audit(principal.tenant_slug, principal.subject, "target.deleted", f"target:{target_id}")


@app.put("/v1/targets/{target_id}/monitoring-rule", tags=["targets"])
def put_monitoring_rule(target_id: str, payload: MonitoringRuleRequest, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    authorize_target(principal, target_id)
    rule = save_rule(principal.tenant_slug, target_id, payload.keywords, payload.account_refs, payload.hashtags)
    audit(principal.tenant_slug, principal.subject, "target.rule_updated", f"target:{target_id}")
    return {"target_id": target_id, **get_rule(principal.tenant_slug, target_id), "updated_at": rule.updated_at}


@app.get("/v1/targets/{target_id}/monitoring-rule", tags=["targets"])
def monitoring_rule(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    authorize_target(principal, target_id)
    return {"target_id": target_id, **get_rule(principal.tenant_slug, target_id)}


@app.post("/v1/targets/{target_id}/events:ingest", tags=["events"])
def post_event(target_id: str, payload: IngestEventRequest, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    authorize_target(principal, target_id)
    item = ingest_event(principal.tenant_slug, target_id, {**payload.model_dump(mode="json"), "target_ref": target_id})
    audit(principal.tenant_slug, principal.subject, "event.ingested", f"target:{target_id}/event:{item.id}")
    return {"id": item.id, "target_id": target_id, "stored": "masked_only", "expires_at": item.expires_at}


@app.get("/v1/targets/{target_id}/events/ingested", tags=["events"])
def get_ingested_events(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> list[dict]:
    authorize_target(principal, target_id)
    return ingested_events(principal.tenant_slug, target_id)


@app.get("/v1/audit-logs", tags=["audit"])
def get_audit_logs(principal: Principal = Depends(require_principal("admin"))) -> list[dict]:
    return [{"id": item.id, "actor_subject": item.actor_subject, "action": item.action, "resource": item.resource, "created_at": item.created_at} for item in audit_history(principal.tenant_slug)]


@app.get("/v1/dashboard", response_model=DashboardResponse, tags=["dashboard"])
def dashboard(principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> DashboardResponse:
    targets = tenant_targets(principal.tenant_slug)
    if not targets:
        raise HTTPException(status_code=404, detail="등록된 분석 대상이 없습니다.")
    events = target_events(targets[0].target_id, principal.tenant_slug)
    return DashboardResponse(analysis=analyze_events(events), recent_events=events[-5:])


@app.get("/v1/targets/{target_id}/risk", response_model=RiskSummary, tags=["risk"])
def get_risk(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> RiskSummary:
    authorize_target(principal, target_id)
    return analyze_events(target_events(target_id, principal.tenant_slug))


@app.get("/v1/targets/{target_id}/attack-types", tags=["risk"])
def attack_types(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    authorize_target(principal, target_id)
    events = target_events(target_id, principal.tenant_slug)
    scores = multilabel_classifier.predict([event.text for event in events])
    return {"target_id": target_id, "source": "kmhas_multilabel_v1" if scores else "unavailable", "scores": scores, "error": multilabel_classifier.error or ""}


@app.get("/v1/targets/{target_id}/events", response_model=list[EventResponse], tags=["events"])
def get_events(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> list[EventResponse]:
    authorize_target(principal, target_id)
    return target_events(target_id, principal.tenant_slug)


@app.get("/v1/targets/{target_id}/graph", response_model=GraphResponse, tags=["graph"])
def get_graph(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> GraphResponse:
    authorize_target(principal, target_id)
    events = target_events(target_id, principal.tenant_slug)
    nodes = [{"id": target_id, "type": "target", "label": "데모 대상"}]
    edges = []
    known_nodes = {target_id}
    for event in events:
        if event.author_ref not in known_nodes:
            nodes.append({"id": event.author_ref, "type": "account", "label": event.author_ref}); known_nodes.add(event.author_ref)
        edges.append({"source": event.author_ref, "target": target_id, "kind": "mention"})
        for hashtag in event.hashtags:
            tag_id = f"tag:{hashtag}"
            if tag_id not in known_nodes:
                nodes.append({"id": tag_id, "type": "hashtag", "label": hashtag}); known_nodes.add(tag_id)
            edges.append({"source": event.author_ref, "target": tag_id, "kind": "uses_hashtag"})
    tag_accounts: dict[str, list[str]] = {}
    for event in events:
        for hashtag in event.hashtags:
            tag_accounts.setdefault(hashtag, []).append(event.author_ref)
    clusters = [sorted(set(accounts)) for accounts in tag_accounts.values() if len(set(accounts)) >= 2]
    coordination_score = min(1.0, sum(len(cluster) for cluster in clusters) / max(len(events), 1))
    return GraphResponse(nodes=nodes, edges=edges, coordination_score=coordination_score, clusters=clusters, **enrich_graph(events, nodes, edges, target_id))


@app.get("/v1/targets/{target_id}/evidence-manifest", response_model=EvidenceManifest, tags=["evidence"])
def evidence_manifest(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> EvidenceManifest:
    authorize_target(principal, target_id)
    return build_evidence_manifest(target_events(target_id, principal.tenant_slug))


@app.get("/v1/targets/{target_id}/evidence-package", tags=["evidence"])
def evidence_package(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> StreamingResponse:
    """PDF와 JSON 매니페스트를 포함하는 ZIP 파일을 반환한다."""
    from io import BytesIO

    authorize_target(principal, target_id)
    events = target_events(target_id, principal.tenant_slug)
    package = build_evidence_zip(events)
    manifest = build_evidence_manifest(events).model_dump(mode="json")
    item = record_evidence(principal.tenant_slug, target_id, hashlib.sha256(package).hexdigest(), len(package), hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest())
    audit(principal.tenant_slug, principal.subject, "evidence.downloaded", f"target:{target_id}/evidence:{item.id}")
    return StreamingResponse(
        BytesIO(package),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="mobius-evidence-{target_id}.zip"'},
    )


@app.get("/v1/targets/{target_id}/evidence/history", tags=["evidence"])
def get_evidence_history(target_id: str, principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> list[dict]:
    authorize_target(principal, target_id)
    return [{"id": item.id, "sha256": item.sha256, "byte_size": item.byte_size, "manifest_sha256": item.manifest_sha256, "created_at": item.created_at} for item in evidence_history(principal.tenant_slug, target_id)]


@app.post("/v1/analyze-image", tags=["multimodal"])
async def analyze_uploaded_image(file: UploadFile = File(...), principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    """업로드 이미지의 OCR 텍스트와 재유포 추적용 지문을 반환한다."""
    result = analyze_image(await file.read())
    previous = similar_image_fingerprints(principal.tenant_slug, result["perceptual_hash"])
    result["similar_images"] = [{"id": item.id, "similarity": round(1 - (int(item.perceptual_hash, 16) ^ int(result["perceptual_hash"], 16)).bit_count() / 64, 3)} for item in previous]
    item = save_image_fingerprint(principal.tenant_slug, result["perceptual_hash"], result["ocr_text"])
    result["id"] = item.id
    result["attack_types"] = multilabel_classifier.predict([result["ocr_text"]]) if result["ocr_text"] else {}
    return result


@app.post("/v1/analyze-video", tags=["multimodal"])
def analyze_video(principal: Principal = Depends(require_principal("victim", "b2b", "admin"))) -> dict:
    return analyze_video_stub()
