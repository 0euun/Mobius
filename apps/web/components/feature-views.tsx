"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiRequest, download } from "../lib/api";
import type { Graph, HistoryItem, Risk, Target } from "../lib/types";

const featureLabels: Record<string, string> = {
  mention_growth: "언급량 증가 추세",
  cross_platform_spread: "플랫폼 확산 정도",
  toxicity_severity: "유해성 수준",
  coordination_signal: "조직적 활동 의심도",
};

const stageLabels: Record<string, string> = {
  pre_ignition: "사전 관찰",
  ignition: "확산 경고",
  cascade: "확산 진행",
  aftermath: "사후 대응",
};

const stageColors: Record<string, string> = {
  pre_ignition: "#16a34a",
  ignition: "#f97316",
  cascade: "#dc2626",
};

const toxicitySourceLabels: Record<string, string> = {
  rule_fallback: "키워드 기반 분석",
  klue_roberta_v0: "AI 언어모델 분석",
};

const attackTypeLabels: Record<string, string> = {
  origin_discrimination: "출신 차별",
  physical_discrimination: "신체·외모 차별",
  political_discrimination: "정치 성향 차별",
  profanity: "욕설·개인 공격",
  age_discrimination: "연령 차별",
  gender_discrimination: "성별 차별",
  racial_discrimination: "인종 차별",
  religious_discrimination: "종교 차별",
};

const persistenceLabels: Record<string, string> = {
  neo4j_incremental: "그래프 DB에 저장됨",
  neo4j_not_configured: "그래프 DB 미연결",
  neo4j_unavailable: "그래프 DB 연결 실패",
};

const nodeTypeStyle: Record<string, { color: string; radius: number }> = {
  target: { color: "#1e3a8a", radius: 11 },
  account: { color: "#2563eb", radius: 6 },
  hashtag: { color: "#0d9488", radius: 5 },
};

type GraphPoint = { x: number; y: number };

function layoutGraph(graph: Graph, width: number, height: number): Record<string, GraphPoint> {
  const positions: Record<string, GraphPoint> = {};
  const nodes = graph.nodes;
  if (nodes.length === 0) return positions;
  const cx = width / 2, cy = height / 2, radius = Math.min(width, height) / 2.6;
  nodes.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / nodes.length;
    positions[node.id] = { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
  });
  const edges = graph.edges.filter(edge => positions[edge.source] && positions[edge.target]);
  const k = Math.sqrt((width * height) / nodes.length);
  for (let iteration = 0; iteration < 200; iteration++) {
    const displacement: Record<string, GraphPoint> = {};
    nodes.forEach(node => { displacement[node.id] = { x: 0, y: 0 }; });
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i].id, b = nodes[j].id;
        const dx = positions[a].x - positions[b].x, dy = positions[a].y - positions[b].y;
        const dist = Math.max(Math.hypot(dx, dy), 0.01);
        const force = (k * k) / dist;
        displacement[a].x += (dx / dist) * force; displacement[a].y += (dy / dist) * force;
        displacement[b].x -= (dx / dist) * force; displacement[b].y -= (dy / dist) * force;
      }
    }
    edges.forEach(edge => {
      const dx = positions[edge.source].x - positions[edge.target].x, dy = positions[edge.source].y - positions[edge.target].y;
      const dist = Math.max(Math.hypot(dx, dy), 0.01);
      const force = (dist * dist) / k;
      displacement[edge.source].x -= (dx / dist) * force; displacement[edge.source].y -= (dy / dist) * force;
      displacement[edge.target].x += (dx / dist) * force; displacement[edge.target].y += (dy / dist) * force;
    });
    const temperature = Math.max(width, height) * 0.06 * (1 - iteration / 200);
    nodes.forEach(node => {
      const d = displacement[node.id];
      const dist = Math.max(Math.hypot(d.x, d.y), 0.01);
      let x = positions[node.id].x + (d.x / dist) * Math.min(dist, temperature);
      let y = positions[node.id].y + (d.y / dist) * Math.min(dist, temperature);
      x += (cx - x) * 0.01; y += (cy - y) * 0.01;
      positions[node.id] = { x: Math.max(18, Math.min(width - 18, x)), y: Math.max(18, Math.min(height - 18, y)) };
    });
  }
  return positions;
}

function SpreadGraph({ graph }: { graph: Graph }) {
  const width = 560, height = 320;
  const positions = useMemo(() => layoutGraph(graph, width, height), [graph]);
  return <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="확산 관계 그래프">
    {graph.edges.map((edge, index) => {
      const source = positions[edge.source], target = positions[edge.target];
      if (!source || !target) return null;
      return <line key={index} x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke="#d7e0ef" strokeWidth={1.4} />;
    })}
    {graph.nodes.map(node => {
      const point = positions[node.id];
      if (!point) return null;
      const style = nodeTypeStyle[node.type] ?? nodeTypeStyle.account;
      return <g key={node.id}>
        <circle cx={point.x} cy={point.y} r={style.radius} fill={style.color}><title>{node.label}</title></circle>
        {node.type === "target" && <text x={point.x} y={point.y - style.radius - 6} textAnchor="middle" fontSize="11" fontWeight={700} fill="#1e3a8a">{node.label}</text>}
      </g>;
    })}
  </svg>;
}

function barColor(value: number): string {
  if (value <= 0.15) return "#2563eb";
  if (value <= 0.45) return "#16a34a";
  if (value <= 0.75) return "#f97316";
  return "#dc2626";
}

export function Dashboard({ risk }: { risk: Risk | null }) {
  if (!risk) return <section className="panel">분석 결과를 불러오는 중입니다.</section>;
  const stageKey = risk.stage.toLowerCase();
  return <><div className="cards"><Metric label="위험 점수" value={risk.score.toFixed(2)} note="0~1 검토 우선순위" /><Metric label="현재 단계" value={stageLabels[stageKey] ?? risk.stage} note="신호 변화에 따라 갱신" color={stageColors[stageKey]} /><Metric label="신뢰도" value={`${Math.round(risk.confidence * 100)}%`} note={toxicitySourceLabels[risk.toxicity_source] ?? risk.toxicity_source} /></div><section className="panel"><h2>판단 근거</h2>{risk.features.map(feature => <div className="feature" key={feature.name}><span className="feature-label">{featureLabels[feature.name] ?? feature.name}</span><span className="bar"><span style={{ width: `${Math.round(feature.value * 100)}%`, background: barColor(feature.value) }} /></span><b>{feature.value.toFixed(2)}</b><small>{feature.explanation}</small></div>)}</section><section className="panel"><h2>권장 조치</h2><ul>{risk.recommended_actions.map(item => <li key={item}>{item}</li>)}</ul></section></>;
}

function Metric({ label, value, note, color }: { label: string; value: string; note: string; color?: string }) { return <article><span>{label}</span><strong style={color ? { color } : undefined}>{value}</strong><small>{note}</small></article>; }

export function Targets({ token, targets, refresh, select }: { token: string; targets: Target[]; refresh: () => Promise<void>; select: (id: string) => void }) {
  const [id, setId] = useState(""); const [name, setName] = useState(""); const [error, setError] = useState("");
  async function create(event: FormEvent) { event.preventDefault(); setError(""); try { await apiRequest("/v1/targets", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target_id: id, display_name: name }) }); await refresh(); select(id); setId(""); setName(""); } catch (cause) { setError((cause as Error).message); } }
  async function remove(item: Target) { if (!confirm(`${item.display_name} 대상을 삭제할까요?`)) return; try { await apiRequest(`/v1/targets/${item.target_id}`, token, { method: "DELETE" }); await refresh(); } catch (cause) { setError((cause as Error).message); } }
  return <section className="panel"><h2>분석 대상 관리</h2><div className="list"><div className="list-head"><span>표시 이름</span><span>대상 ID</span><span /></div>{targets.map(item => <div key={item.target_id}><button className="text" onClick={() => select(item.target_id)}>{item.display_name}</button><code>{item.target_id}</code><button className="danger" onClick={() => remove(item)}>삭제</button></div>)}</div><form className="target-form" onSubmit={create}><label>표시 이름<input value={name} onChange={event => setName(event.target.value)} required /></label><label>대상 ID<input value={id} onChange={event => setId(event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))} minLength={3} required /></label><button className="blue">등록</button></form>{error && <p className="error">{error}</p>}</section>;
}

export function Collect({ token, target }: { token: string; target: string }) {
  const [query, setQuery] = useState(""); const [message, setMessage] = useState("");
  async function sync(provider: "youtube" | "naver-search") { setMessage("수집 중입니다."); const body = provider === "youtube" ? { query, max_videos: 3, max_comments_per_video: 30 } : { query, sources: ["news", "blog", "cafearticle"], display: 20 }; try { const result = await apiRequest<{ stored: number }>(`/v1/targets/${target}/connectors/${provider}/sync`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); setMessage(`${result.stored}건을 저장했습니다.`); } catch (cause) { setMessage((cause as Error).message); } }
  return <section className="panel"><h2>공식 API 데이터 수집</h2><label>검색어<input value={query} onChange={event => setQuery(event.target.value)} placeholder="브랜드 또는 인물명" /></label><div className="actions"><button className="blue" disabled={!target || !query} onClick={() => sync("youtube")}>YouTube 동기화</button><button className="outline" disabled={!target || !query} onClick={() => sync("naver-search")}>NAVER 동기화</button></div>{message && <p>{message}</p>}</section>;
}

export function Analysis({ token, target }: { token: string; target: string }) {
  const [graph, setGraph] = useState<Graph | null>(null); const [types, setTypes] = useState<Record<string, number>>({}); const [typeSource, setTypeSource] = useState(""); const [image, setImage] = useState<object | null>(null); const [error, setError] = useState("");
  useEffect(() => { if (!target) return; Promise.all([apiRequest<Graph>(`/v1/targets/${target}/graph`, token), apiRequest<{ source: string; scores: Record<string, number> }>(`/v1/targets/${target}/attack-types`, token)]).then(([nextGraph, nextTypes]) => { setGraph(nextGraph); setTypes(nextTypes.scores); setTypeSource(nextTypes.source); }).catch(cause => setError(cause.message)); }, [token, target]);
  async function upload(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const input = event.currentTarget.elements.namedItem("image") as HTMLInputElement; if (!input.files?.[0]) return; const body = new FormData(); body.append("file", input.files[0]); try { setImage(await apiRequest("/v1/analyze-image", token, { method: "POST", body })); } catch (cause) { setError((cause as Error).message); } }
  return <div className="two-cards"><section className="panel"><h2>공격 유형</h2>{typeSource === "demo_rule_fallback" && <p><small>멀티라벨 AI 모델 분석 결과</small></p>}{Object.entries(types).length ? Object.entries(types).sort((a,b) => b[1]-a[1]).map(([label, value]) => <div className="score" key={label}><span>{attackTypeLabels[label] ?? label}</span><b>{Math.round(value * 100)}%</b></div>) : <p>분석할 데이터가 없습니다.</p>}</section><section className="panel"><h2>확산 그래프</h2>{graph && <><p>노드 {graph.nodes.length}개 · 연결 {graph.edges.length}개</p><SpreadGraph graph={graph} /><div className="graph-legend"><span><i style={{ background: nodeTypeStyle.target.color }} />분석 대상</span><span><i style={{ background: nodeTypeStyle.account.color }} />계정</span><span><i style={{ background: nodeTypeStyle.hashtag.color }} />해시태그</span></div><small>협조 {graph.coordination_score.toFixed(2)} · 반복 {graph.repeated_phrase_score.toFixed(2)} · 동시성 {graph.cross_platform_concurrency.toFixed(2)} · {persistenceLabels[graph.persistence] ?? graph.persistence}</small></>}</section><section className="panel wide"><h2>이미지 OCR·재유포 분석</h2><form className="upload-form" onSubmit={upload}><input name="image" type="file" accept="image/*" required /><button className="blue">분석</button></form>{image && <pre>{JSON.stringify(image, null, 2)}</pre>}{error && <p className="error">{error}</p>}</section></div>;
}

export function Evidence({ token, target }: { token: string; target: string }) {
  const [items, setItems] = useState<HistoryItem[]>([]); const [message, setMessage] = useState(""); const refresh = () => apiRequest<HistoryItem[]>(`/v1/targets/${target}/evidence/history`, token).then(setItems);
  useEffect(() => { if (target) refresh().catch(() => undefined); }, [token, target]);
  async function create() { try { await download(`/v1/targets/${target}/evidence-package`, token, `mobius-evidence-${target}.zip`); await refresh(); } catch (cause) { setMessage((cause as Error).message); } }
  const latest = [...items].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 1);
  return <section className="panel"><h2>증거 패키지</h2><p>PDF와 무결성 JSON을 하나의 ZIP으로 생성합니다.</p><button className="blue" disabled={!target} onClick={create}>증거 ZIP 생성·다운로드</button><History items={latest} fields={["sha256", "byte_size"]} />{message && <p className="error">{message}</p>}</section>;
}

export function Alerts({ token, target }: { token: string; target: string }) {
  const [items, setItems] = useState<HistoryItem[]>([]); const [message, setMessage] = useState(""); const refresh = () => apiRequest<HistoryItem[]>(`/v1/targets/${target}/alerts/history`, token).then(setItems);
  useEffect(() => { if (target) refresh().catch(() => undefined); }, [token, target]);
  async function send() { try { const result = await apiRequest<{ status?: string; delivery?: { status: string } }>(`/v1/targets/${target}/alerts:dispatch`, token, { method: "POST" }); setMessage(result.status ?? result.delivery?.status ?? "처리됨"); await refresh(); } catch (cause) { setMessage((cause as Error).message); } }
  return <section className="panel"><h2>위험 알림</h2><p>같은 위험 단계는 기본 30분 동안 묶음 처리됩니다.</p><button className="blue" disabled={!target} onClick={send}>현재 위험 알림 보내기</button>{message && <p>{message}</p>}<History items={items} fields={["severity", "delivery_status", "message"]} /></section>;
}

const historyFieldLabels: Record<string, string> = {
  sha256: "무결성 해시(SHA-256)",
  byte_size: "파일 크기",
  severity: "현재 단계",
  delivery_status: "전송 상태",
  message: "메시지",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}바이트`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function HashValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const short = value.length > 20 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
  return <details className="hash">
    <summary>{short}</summary>
    <code>{value}</code>
    <button type="button" className="text small-button" onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? "복사됨" : "복사"}</button>
  </details>;
}

function historyFieldValue(field: string, raw: string) {
  if (field === "sha256") return <HashValue value={raw} />;
  if (field === "byte_size") { const bytes = Number(raw); return Number.isFinite(bytes) ? formatBytes(bytes) : raw; }
  if (field === "severity") return stageLabels[raw] ?? raw;
  return raw;
}

function History({ items, fields }: { items: HistoryItem[]; fields: string[] }) { return <div className="history">{items.map(item => <article key={item.id}><small>{new Date(item.created_at).toLocaleString()}</small>{fields.map(field => <span key={field}>{historyFieldLabels[field] ?? field}: {historyFieldValue(field, String(item[field] ?? ""))}</span>)}</article>)}</div>; }
