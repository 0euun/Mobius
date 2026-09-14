from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class RiskStage(str, Enum):
    PRE_IGNITION = "pre_ignition"
    IGNITION = "ignition"
    CASCADE = "cascade"
    AFTERMATH = "aftermath"


class Engagement(BaseModel):
    likes: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)


class EventResponse(BaseModel):
    event_id: str
    occurred_at: datetime
    platform: str
    author_ref: str
    target_ref: str
    text: str
    hashtags: list[str]
    engagement: Engagement


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class RiskFeature(BaseModel):
    name: str
    value: float = Field(ge=0, le=1)
    explanation: str


class RiskSummary(BaseModel):
    target_id: str
    score: float = Field(ge=0, le=1)
    stage: RiskStage
    confidence: float = Field(ge=0, le=1)
    toxicity_source: str
    prediction_window_minutes: int
    rationale: list[str]
    features: list[RiskFeature]
    recommended_actions: list[str]


class DashboardResponse(BaseModel):
    analysis: RiskSummary
    recent_events: list[EventResponse]


class GraphNode(BaseModel):
    id: str
    type: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    coordination_score: float = Field(ge=0, le=1)
    clusters: list[list[str]]
    centrality: dict[str, float] = Field(default_factory=dict)
    repeated_phrase_score: float = 0.0
    cross_platform_concurrency: float = 0.0
    persistence: str = "memory"


class EvidenceItem(BaseModel):
    event_id: str
    collected_at: datetime
    sha256: str
    source_url: str | None = None


class EvidenceManifest(BaseModel):
    target_id: str
    generated_at: datetime
    package_sha256: str
    integrity_notice: str
    items: list[EvidenceItem]


class TargetCreateRequest(BaseModel):
    target_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,128}$")
    display_name: str = Field(min_length=1, max_length=255)


class TargetUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class MonitoringRuleRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=50)
    account_refs: list[str] = Field(default_factory=list, max_length=50)
    hashtags: list[str] = Field(default_factory=list, max_length=50)


class IngestEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    platform: str = Field(min_length=1, max_length=64)
    author_ref: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=10000)
    hashtags: list[str] = Field(default_factory=list, max_length=50)
    likes: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)


class YouTubeSyncRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    max_videos: int = Field(default=3, ge=1, le=5)
    max_comments_per_video: int = Field(default=30, ge=1, le=50)


class NaverSyncRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    sources: list[str] = Field(default_factory=lambda: ["news", "blog", "cafearticle"], min_length=1, max_length=4)
    display: int = Field(default=20, ge=1, le=50)
