"use client";

import { FormEvent, useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type Target = { target_id: string; display_name: string };
type Risk = { score: number; stage: string; confidence: number };
type View = "dashboard" | "targets" | "collect" | "evidence";

export default function Home() {
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [targets, setTargets] = useState<Target[]>([]);
  const [target, setTarget] = useState("");
  const [risk, setRisk] = useState<Risk | null>(null);
  const [view, setView] = useState<View>("dashboard");
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const query = new URLSearchParams(location.search);
    const nextToken = query.get("token") || localStorage.getItem("mobius_token") || "";
    const nextRole = query.get("role") || localStorage.getItem("mobius_role") || "";
    if (query.get("token")) {
      localStorage.setItem("mobius_token", nextToken);
      localStorage.setItem("mobius_role", nextRole);
      history.replaceState({}, "", "/");
    }
    setToken(nextToken); setRole(nextRole);
  }, []);

  async function loadTargets(accessToken = token) {
    const response = await fetch(`${api}/v1/targets`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (!response.ok) throw Error("분석 대상을 불러오지 못했습니다.");
    const items = await response.json(); setTargets(items); setTarget(items[0]?.target_id ?? "");
  }
  useEffect(() => { if (token) loadTargets().catch((error) => setMessage(error.message)); }, [token]);
  useEffect(() => {
    if (!token || !target) return;
    fetch(`${api}/v1/targets/${target}/risk`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => response.ok ? response.json() : null).then(setRisk);
  }, [token, target]);

  async function demo(kind: "victim" | "business") {
    const response = await fetch(`${api}/v1/auth/demo-login`, { method: "POST", headers: { "X-API-Key": kind === "victim" ? "mobius-victim-demo" : "mobius-b2b-demo" } });
    if (!response.ok) return setMessage("데모 로그인을 시작하지 못했습니다.");
    const session = await response.json();
    localStorage.setItem("mobius_token", session.access_token); localStorage.setItem("mobius_role", session.role);
    setToken(session.access_token); setRole(session.role);
  }
  async function google() {
    const response = await fetch(`${api}/v1/auth/login/google`);
    if (!response.ok) return setMessage("Google 로그인을 시작하지 못했습니다. OAuth 설정을 확인해 주세요.");
    location.href = (await response.json()).authorization_url;
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    const response = await fetch(`${api}/v1/targets`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ target_id: id, display_name: name }) });
    if (!response.ok) return setMessage("대상 ID는 영문·숫자·하이픈·밑줄로 3자 이상 입력해 주세요.");
    const item = await response.json();
    setTargets([...targets, item]); setTarget(item.target_id); setName(""); setId(""); setView("dashboard");
  }
  function logout() { localStorage.clear(); setToken(""); setTargets([]); setRisk(null); }

  if (!token) return <Landing google={google} demo={demo} message={message} />;
  return <Workspace role={role} targets={targets} target={target} setTarget={setTarget} risk={risk} view={view} setView={setView} create={create} name={name} setName={setName} id={id} setId={setId} logout={logout} message={message} />;
}

function Landing({ google, demo, message }: { google: () => void; demo: (kind: "victim" | "business") => void; message: string }) {
  return <><header className="public-nav"><a className="brand" href="#top">MOBIUS</a><nav><a href="#how">서비스 소개</a><a href="#platform">분석 범위</a><a href="#privacy">데이터 원칙</a></nav><div className="nav-actions"><button className="text" onClick={google}>로그인</button><button className="blue small-button" onClick={google}>시작하기</button></div></header>
    <main id="top" className="landing"><section className="intro"><div><p className="eyebrow">ONLINE SAFETY, MADE CLEAR</p><h1>온라인 공격의 <em>초기 신호</em>를<br />놓치지 마세요.</h1><p className="lead">Mobius는 공개·허가 데이터에서 반복되는 공격 신호를 찾아 위험도, 근거, 그리고 다음에 할 일을 한눈에 보여줍니다.</p><div className="cta"><button className="blue" onClick={google}>Google로 시작하기</button><button className="outline" onClick={() => demo("victim")}>데모 둘러보기</button></div>{message && <p className="error">{message}</p>}<small>Google 계정으로 바로 시작할 수 있습니다.</small></div><aside className="preview"><p>오늘의 보호 현황</p><strong>초기 경보 감지</strong><div className="signal"><i /><i /><i /><i /></div><span>반복 문구 · 다중 플랫폼 · 확산 속도</span></aside></section>
      <section id="how" className="steps"><p className="eyebrow">HOW IT WORKS</p><h2>복잡한 분석을 세 단계로</h2><div><article><b>01</b><h3>대상을 등록해요</h3><p>나, 브랜드, 기관 등 보호할 대상을 정합니다.</p></article><article><b>02</b><h3>공개 신호를 모아요</h3><p>YouTube와 NAVER 공식 API 데이터만 사용합니다.</p></article><article><b>03</b><h3>우선순위를 알려줘요</h3><p>위험도와 근거를 바탕으로 다음 행동을 안내합니다.</p></article></div></section>
      <section id="platform" className="trust"><div><p className="eyebrow">OFFICIAL DATA ONLY</p><h2>허가된 범위에서만<br />분석합니다</h2></div><div><p><b>YouTube</b><br />공개 영상과 댓글</p><p><b>NAVER Search</b><br />뉴스 · 블로그 · 카페 검색 결과</p></div></section>
      <section id="privacy" className="privacy"><h2>감시가 아니라, 보호를 위한 분석</h2><p>비공개 계정이나 허가되지 않은 커뮤니티를 수집하지 않습니다. 이벤트는 마스킹해 저장하고, 증거 패키지는 SHA-256 무결성 검증을 지원합니다.</p></section></main></>;
}

function Workspace(props: any) {
  const guidance = props.role === "victim"
    ? ["관련 게시물의 URL과 작성 시각을 저장하세요.", "반복되거나 위협적인 내용은 증거 패키지로 보관하세요.", "도움이 필요하면 신뢰할 수 있는 기관이나 주변에 지원을 요청하세요."]
    : ["위험 이벤트의 확산 경로를 우선 확인하세요.", "담당자에게 증거 패키지를 전달하고 대응 이력을 남기세요.", "오탐 가능성과 문구를 함께 확인하세요."];
  const labels: Record<View, string> = { dashboard: "위험 신호", targets: "분석 대상", collect: "데이터 수집", evidence: "증거 보관" };
  return <main className="app"><aside className="side"><b className="brand">MOBIUS</b>{(Object.keys(labels) as View[]).map((key) => <button key={key} className={props.view === key ? "active" : ""} onClick={() => props.setView(key)}>{labels[key]}</button>)}<div className="account"><span>{props.role === "victim" ? "개인 보호" : "기관 담당자"}</span><button className="text" onClick={props.logout}>로그아웃</button></div></aside>
    <section className="workspace"><header><div><p className="eyebrow">{props.view.toUpperCase()}</p><h1>{labels[props.view as View]}</h1></div></header>
      {props.view === "dashboard" && <><div className="target-tabs">{props.targets.map((item: Target) => <button key={item.target_id} className={props.target === item.target_id ? "active" : ""} onClick={() => props.setTarget(item.target_id)}>{item.display_name}</button>)}</div><div className="cards"><article><span>위험 점수</span><strong>{props.risk?.score?.toFixed(2) ?? "-"}</strong><small>0~1 사이의 검토 우선순위</small></article><article><span>현재 단계</span><strong>{props.risk?.stage ?? "분석 중"}</strong><small>신호 변화에 따라 갱신</small></article><article><span>신뢰도</span><strong>{props.risk ? `${Math.round(props.risk.confidence * 100)}%` : "-"}</strong><small>확정 판정이 아닌 보조 지표</small></article></div><section className="panel"><p className="eyebrow">NEXT STEP</p><h2>{props.role === "victim" ? "지금 확인할 보호 조치" : "지금 확인할 운영 항목"}</h2><ul>{guidance.map((item: string) => <li key={item}>{item}</li>)}</ul></section></>}
      {props.view === "targets" && <section className="panel"><h2>새 분석 대상</h2><p>등록한 이름은 YouTube·NAVER 검색어와 연결되어 공개 신호를 수집할 때 사용됩니다.</p><form onSubmit={props.create}><label>표시 이름<input value={props.name} onChange={(event) => props.setName(event.target.value)} placeholder="예: Mobius 브랜드" required /></label><label>대상 ID<input value={props.id} onChange={(event) => props.setId(event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))} placeholder="mobius-brand" required /></label><button className="blue">분석 대상 등록</button></form></section>}
      {props.view === "collect" && <section className="two-cards"><article><b>YouTube</b><h2>공개 영상과 댓글</h2><p>검색어를 기준으로 공개 영상·댓글 표본을 수집해 위험 신호를 분석합니다.</p></article><article><b>NAVER Search</b><h2>뉴스 · 블로그 · 카페</h2><p>NAVER API HUB의 공식 검색 결과만 가져와 분석합니다.</p></article></section>}
      {props.view === "evidence" && <section className="panel"><h2>증거를 신뢰할 수 있게</h2><p>수집 시각과 SHA-256 해시를 포함한 증거 패키지를 만들면, 이후에도 파일이 변경됐는지 확인할 수 있습니다.</p></section>}
      {props.message && <p className="error">{props.message}</p>}</section></main>;
}
