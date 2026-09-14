"""
PostgreSQL 영속화와 테넌트 경계.
원문은 기본적으로 저장하지 않고 마스킹된 이벤트만 보관한다. 증거 ZIP 자체는
다운로드 시점에 생성하며, DB에는 재현·감사용 해시와 메타데이터만 남긴다.
"""
import hashlib

import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .privacy import sanitize_event

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mobius.db")
RAW_RETENTION_DAYS = int(os.getenv("MOBIUS_RAW_RETENTION_DAYS", "0"))
MASKED_RETENTION_DAYS = int(os.getenv("MOBIUS_MASKED_RETENTION_DAYS", "90"))
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TenantRecord(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class UserRecord(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    external_subject: Mapped[str] = mapped_column(String(128), unique=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class RoleRecord(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str] = mapped_column(String(255))


class TargetRecord(Base):
    __tablename__ = "analysis_targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class EventRecord(Base):
    __tablename__ = "analysis_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_masked: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


# 기존 P0 컨테이너의 alerts 테이블과 호환되는 레거시 이력이다.
class AlertRecord(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TenantAlertRecord(Base):
    __tablename__ = "tenant_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(32), default="simulated")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class EvidenceRecord(Base):
    __tablename__ = "evidence_packages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    actor_subject: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class AuthIdentityRecord(Base):
    __tablename__ = "auth_identities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_subject: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class NotificationRecord(Base):
    __tablename__ = "notification_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ImageFingerprintRecord(Base):
    __tablename__ = "image_fingerprints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    perceptual_hash: Mapped[str] = mapped_column(String(32), index=True)
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class MonitoringRuleRecord(Base):
    __tablename__ = "monitoring_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    account_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


TENANT_SEEDS = (("victim-demo", "피해자 데모 조직"), ("b2b-demo", "B2B 데모 조직"), ("admin-demo", "관리자 데모 조직"))
ROLE_SEEDS = (("victim", "피해자 보호 화면"), ("b2b", "조직 운영 화면"), ("admin", "관리자 화면"))


def initialize() -> None:
    Base.metadata.create_all(engine)
    with Session.begin() as session:
        for slug, name in TENANT_SEEDS:
            if session.scalar(select(TenantRecord).where(TenantRecord.slug == slug)) is None:
                session.add(TenantRecord(slug=slug, name=name))
            if session.scalar(select(TargetRecord).where(TargetRecord.tenant_slug == slug, TargetRecord.target_id == "demo-target")) is None:
                session.add(TargetRecord(tenant_slug=slug, target_id="demo-target", display_name="공개 데모 분석 대상"))
            private_target = f"{slug}-private-target"
            if session.scalar(select(TargetRecord).where(TargetRecord.tenant_slug == slug, TargetRecord.target_id == private_target)) is None:
                session.add(TargetRecord(tenant_slug=slug, target_id=private_target, display_name="조직 전용 테스트 대상"))
            subject = f"{slug}-user"
            role = slug.split("-", 1)[0]
            if session.scalar(select(UserRecord).where(UserRecord.external_subject == subject)) is None:
                session.add(UserRecord(tenant_slug=slug, external_subject=subject, role=role))
        for name, description in ROLE_SEEDS:
            if session.scalar(select(RoleRecord).where(RoleRecord.name == name)) is None:
                session.add(RoleRecord(name=name, description=description))
    purge_expired()


def assert_target_access(tenant_slug: str, target_id: str) -> None:
    with Session() as session:
        target = session.scalar(select(TargetRecord).where(TargetRecord.tenant_slug == tenant_slug, TargetRecord.target_id == target_id))
    if target is None:
        raise PermissionError("해당 조직에 등록되지 않은 분석 대상입니다.")


def tenant_targets(tenant_slug: str) -> list[TargetRecord]:
    with Session() as session:
        return list(session.scalars(select(TargetRecord).where(TargetRecord.tenant_slug == tenant_slug).order_by(TargetRecord.target_id)))


def create_target(tenant_slug: str, target_id: str, display_name: str) -> TargetRecord:
    with Session.begin() as session:
        if session.scalar(select(TargetRecord).where(TargetRecord.tenant_slug == tenant_slug, TargetRecord.target_id == target_id)):
            raise ValueError("이미 등록된 분석 대상입니다.")
        item = TargetRecord(tenant_slug=tenant_slug, target_id=target_id, display_name=display_name)
        session.add(item); session.flush(); session.refresh(item); return item


def update_target(tenant_slug: str, target_id: str, display_name: str) -> TargetRecord:
    with Session.begin() as session:
        item = session.scalar(select(TargetRecord).where(TargetRecord.tenant_slug == tenant_slug, TargetRecord.target_id == target_id))
        if item is None: raise ValueError("분석 대상을 찾을 수 없습니다.")
        item.display_name = display_name; session.flush(); session.refresh(item); return item


def delete_target(tenant_slug: str, target_id: str) -> bool:
    if target_id == "demo-target": raise ValueError("데모 대상은 삭제할 수 없습니다.")
    with Session.begin() as session:
        item = session.scalar(select(TargetRecord).where(TargetRecord.tenant_slug == tenant_slug, TargetRecord.target_id == target_id))
        if item is None: return False
        session.delete(item); return True


def save_rule(tenant_slug: str, target_id: str, keywords: list[str], account_refs: list[str], hashtags: list[str]) -> MonitoringRuleRecord:
    with Session.begin() as session:
        item = session.scalar(select(MonitoringRuleRecord).where(MonitoringRuleRecord.tenant_slug == tenant_slug, MonitoringRuleRecord.target_id == target_id))
        if item is None:
            item = MonitoringRuleRecord(tenant_slug=tenant_slug, target_id=target_id); session.add(item)
        item.keywords_json, item.account_refs_json, item.hashtags_json, item.updated_at = json.dumps(keywords), json.dumps(account_refs), json.dumps(hashtags), datetime.now(UTC)
        session.flush(); session.refresh(item); return item


def get_rule(tenant_slug: str, target_id: str) -> dict:
    with Session() as session: item = session.scalar(select(MonitoringRuleRecord).where(MonitoringRuleRecord.tenant_slug == tenant_slug, MonitoringRuleRecord.target_id == target_id))
    return {"keywords": json.loads(item.keywords_json), "account_refs": json.loads(item.account_refs_json), "hashtags": json.loads(item.hashtags_json)} if item else {"keywords": [], "account_refs": [], "hashtags": []}


def ingest_event(tenant_slug: str, target_id: str, payload: dict) -> EventRecord:
    payload = sanitize_event(payload)
    expiry = datetime.now(UTC) + timedelta(days=MASKED_RETENTION_DAYS)
    with Session.begin() as session:
        records = session.scalars(select(EventRecord).where(EventRecord.tenant_slug == tenant_slug, EventRecord.target_id == target_id))
        event_id = payload.get("event_id")
        for existing in records:
            if json.loads(existing.payload_masked).get("event_id") == event_id:
                return existing
        item = EventRecord(tenant_slug=tenant_slug, target_id=target_id, payload_masked=json.dumps(payload, ensure_ascii=False), raw_payload=None, expires_at=expiry)
        session.add(item); session.flush(); session.refresh(item); return item


def ingested_events(tenant_slug: str, target_id: str) -> list[dict]:
    with Session() as session: records = list(session.scalars(select(EventRecord).where(EventRecord.tenant_slug == tenant_slug, EventRecord.target_id == target_id).order_by(EventRecord.created_at)))
    return [json.loads(item.payload_masked) for item in records]


def resolve_identity(provider: str, provider_subject: str, email: str) -> AuthIdentityRecord:
    """Google 계정마다 독립된 기본 조직과 피해자 역할을 자동 생성한다."""
    normalized_email = email.strip().lower()
    with Session.begin() as session:
        identity = session.scalar(select(AuthIdentityRecord).where(AuthIdentityRecord.provider_subject == provider_subject))
        if identity:
            return identity
        tenant_slug = f"google-{hashlib.sha256(provider_subject.encode()).hexdigest()[:16]}"
        if session.scalar(select(TenantRecord).where(TenantRecord.slug == tenant_slug)) is None:
            session.add(TenantRecord(slug=tenant_slug, name="Google 사용자 조직"))
        if session.scalar(select(UserRecord).where(UserRecord.external_subject == provider_subject)) is None:
            session.add(UserRecord(tenant_slug=tenant_slug, external_subject=provider_subject, role="victim"))
        identity = AuthIdentityRecord(tenant_slug=tenant_slug, provider=provider, provider_subject=provider_subject, email=normalized_email, role="victim")
        session.add(identity); session.flush(); session.refresh(identity)
        return identity


def record_notification(tenant_slug: str, target_id: str, channel: str, status: str, attempts: int, detail: str = "") -> NotificationRecord:
    with Session.begin() as session:
        item = NotificationRecord(tenant_slug=tenant_slug, target_id=target_id, channel=channel, status=status, attempts=attempts, detail=detail)
        session.add(item); session.flush(); session.refresh(item)
        return item


def notification_history(tenant_slug: str, target_id: str) -> list[NotificationRecord]:
    with Session() as session:
        return list(session.scalars(select(NotificationRecord).where(NotificationRecord.tenant_slug == tenant_slug, NotificationRecord.target_id == target_id).order_by(NotificationRecord.created_at.desc()).limit(100)))


def notification_allowed(tenant_slug: str, target_id: str, severity: str, cooldown_minutes: int = 30) -> bool:
    cooldown_minutes = int(os.getenv("MOBIUS_ALERT_COOLDOWN_MINUTES", str(cooldown_minutes)))
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=cooldown_minutes)
    with Session() as session:
        recent = session.scalar(select(TenantAlertRecord).where(TenantAlertRecord.tenant_slug == tenant_slug, TenantAlertRecord.target_id == target_id, TenantAlertRecord.severity == severity, TenantAlertRecord.created_at >= cutoff).limit(1))
    return recent is None


def save_image_fingerprint(tenant_slug: str, perceptual_hash: str, ocr_text: str) -> ImageFingerprintRecord:
    with Session.begin() as session:
        item = ImageFingerprintRecord(tenant_slug=tenant_slug, perceptual_hash=perceptual_hash, ocr_text=ocr_text)
        session.add(item); session.flush(); session.refresh(item)
        return item


def similar_image_fingerprints(tenant_slug: str, perceptual_hash: str, limit: int = 5) -> list[ImageFingerprintRecord]:
    with Session() as session:
        candidates = list(session.scalars(select(ImageFingerprintRecord).where(ImageFingerprintRecord.tenant_slug == tenant_slug).order_by(ImageFingerprintRecord.created_at.desc()).limit(100)))
    return sorted(candidates, key=lambda item: (int(item.perceptual_hash, 16) ^ int(perceptual_hash, 16)).bit_count())[:limit]


def record_alert(tenant_slug: str, target_id: str, severity: str, message: str, delivery_status: str = "simulated") -> TenantAlertRecord:
    with Session.begin() as session:
        item = TenantAlertRecord(tenant_slug=tenant_slug, target_id=target_id, severity=severity, message=message, delivery_status=delivery_status)
        session.add(item); session.flush(); session.refresh(item)
        return item


def alert_history(tenant_slug: str, target_id: str) -> list[TenantAlertRecord]:
    with Session() as session:
        return list(session.scalars(select(TenantAlertRecord).where(TenantAlertRecord.tenant_slug == tenant_slug, TenantAlertRecord.target_id == target_id).order_by(TenantAlertRecord.created_at.desc()).limit(50)))


def record_evidence(tenant_slug: str, target_id: str, sha256: str, byte_size: int, manifest_sha256: str) -> EvidenceRecord:
    with Session.begin() as session:
        item = EvidenceRecord(tenant_slug=tenant_slug, target_id=target_id, sha256=sha256, byte_size=byte_size, manifest_sha256=manifest_sha256)
        session.add(item); session.flush(); session.refresh(item)
        return item


def evidence_history(tenant_slug: str, target_id: str) -> list[EvidenceRecord]:
    with Session() as session:
        return list(session.scalars(select(EvidenceRecord).where(EvidenceRecord.tenant_slug == tenant_slug, EvidenceRecord.target_id == target_id).order_by(EvidenceRecord.created_at.desc()).limit(50)))


def audit(tenant_slug: str, actor_subject: str, action: str, resource: str) -> None:
    with Session.begin() as session:
        session.add(AuditLogRecord(tenant_slug=tenant_slug, actor_subject=actor_subject, action=action, resource=resource))


def audit_history(tenant_slug: str, limit: int = 100) -> list[AuditLogRecord]:
    with Session() as session:
        return list(session.scalars(select(AuditLogRecord).where(AuditLogRecord.tenant_slug == tenant_slug).order_by(AuditLogRecord.created_at.desc()).limit(limit)))


def purge_expired() -> int:
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session.begin() as session:
        stale = list(session.scalars(select(EventRecord).where(EventRecord.expires_at < now)))
        for item in stale:
            session.delete(item)
        return len(stale)


def retention_policy() -> dict[str, int | str]:
    return {"raw_payload": "not_stored_by_default", "raw_retention_days": RAW_RETENTION_DAYS, "masked_retention_days": MASKED_RETENTION_DAYS}
