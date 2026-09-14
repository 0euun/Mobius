"use client";

import { useCallback, useEffect, useState } from "react";
import { Alerts, Analysis, Collect, Dashboard, Evidence, Targets } from "../components/feature-views";
import { apiRequest } from "../lib/api";
import type { Risk, Target, View } from "../lib/types";

const labels: Record<View, string> = { dashboard: "위험 신호", targets: "분석 대상", collect: "데이터 수집", analysis: "상세 분석", evidence: "증거 보관", alerts: "알림" };

export default function Home() {
  const [token, setToken] = useState(""); const [role, setRole] = useState("");
  const [googleConfigured, setGoogleConfigured] = useState(false);
  const [targets, setTargets] = useState<Target[]>([]); const [target, setTarget] = useState("");
  const [risk, setRisk] = useState<Risk | null>(null); const [view, setView] = useState<View>("dashboard"); const [message, setMessage] = useState("");

  useEffect(() => {
    const query = new URLSearchParams(location.search);
    const nextToken = query.get("token") || localStorage.getItem("mobius_token") || "";
    const nextRole = query.get("role") || localStorage.getItem("mobius_role") || "";
    if (query.get("token")) { localStorage.setItem("mobius_token", nextToken); localStorage.setItem("mobius_role", nextRole); history.replaceState({}, "", "/"); }
    setToken(nextToken); setRole(nextRole);
    apiRequest<{ oauth: { google: { configured: boolean } } }>("/v1/auth/providers")
      .then(result => setGoogleConfigured(result.oauth.google.configured))
      .catch(() => setMessage("API 서버 연결을 확인해 주세요."));
  }, []);

  const loadTargets = useCallback(async () => {
    if (!token) return;
    const items = await apiRequest<Target[]>("/v1/targets", token); setTargets(items);
    setTarget(current => items.some(item => item.target_id === current) ? current : items[0]?.target_id ?? "");
  }, [token]);
  useEffect(() => { loadTargets().catch(cause => setMessage(cause.message)); }, [loadTargets]);
  useEffect(() => { if (token && target) apiRequest<Risk>(`/v1/targets/${target}/risk`, token).then(setRisk).catch(cause => setMessage(cause.message)); }, [token, target]);

  async function demo(kind: "victim" | "business") {
    try {
      const key = kind === "victim" ? "mobius-victim-demo" : "mobius-b2b-demo";
      const session = await apiRequest<{ access_token: string; role: string }>("/v1/auth/demo-login", "", { method: "POST", headers: { "X-API-Key": key } });
      localStorage.setItem("mobius_token", session.access_token); localStorage.setItem("mobius_role", session.role);
      setToken(session.access_token); setRole(session.role);
    } catch (cause) { setMessage((cause as Error).message); }
  }
  async function google() {
    if (!googleConfigured) { setMessage("Google OAuth가 설정되지 않았습니다. 로컬에서는 개인 또는 기관 데모를 이용해 주세요."); return; }
    try { const result = await apiRequest<{ authorization_url: string }>("/v1/auth/login/google"); location.href = result.authorization_url; } catch (cause) { setMessage((cause as Error).message); }
  }
  function logout() { localStorage.removeItem("mobius_token"); localStorage.removeItem("mobius_role"); setToken(""); setTargets([]); setRisk(null); }

  if (!token) return <Landing google={google} googleConfigured={googleConfigured} demo={demo} message={message} />;
  const content = {
    dashboard: <Dashboard risk={risk} />, targets: <Targets token={token} targets={targets} refresh={loadTargets} select={setTarget} />,
    collect: <Collect token={token} target={target} />, analysis: <Analysis token={token} target={target} />,
    evidence: <Evidence token={token} target={target} />, alerts: <Alerts token={token} target={target} />,
  }[view];
  return <main className="app"><aside className="side"><button className="brand" onClick={() => setView("dashboard")}>MOBIUS</button>{(Object.keys(labels) as View[]).map(key => <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>{labels[key]}</button>)}<div className="account"><span>{role === "victim" ? "개인 보호" : "기관 담당자"}</span><button className="text" onClick={logout}>로그아웃</button></div></aside><section className="workspace"><header><div><p className="eyebrow">{view.toUpperCase()}</p><h1>{labels[view]}</h1></div><select value={target} onChange={event => setTarget(event.target.value)}>{targets.map(item => <option key={item.target_id} value={item.target_id}>{item.display_name}</option>)}</select></header>{content}{message && <p className="error">{message}</p>}</section></main>;
}

function Landing({ google, googleConfigured, demo, message }: { google: () => void; googleConfigured: boolean; demo: (kind: "victim" | "business") => void; message: string }) {
  const googleLabel = googleConfigured ? "Google로 시작하기" : "Google 로그인 미설정";
  return <><header className="public-nav"><b className="brand">MOBIUS</b><div className="nav-actions"><button className="text" disabled={!googleConfigured} onClick={google}>Google 로그인</button></div></header><main className="landing"><section className="intro"><div><p className="eyebrow">ONLINE SAFETY, MADE CLEAR</p><h1>온라인 공격의 <em>초기 신호</em>를 놓치지 마세요.</h1><p className="lead">공개·허가 데이터에서 반복되는 공격 신호를 찾아 위험도, 근거, 다음 행동을 보여줍니다.</p><div className="cta"><button className="blue" disabled={!googleConfigured} onClick={google}>{googleLabel}</button><button className="outline" onClick={() => demo("victim")}>개인 데모</button><button className="outline" onClick={() => demo("business")}>기관 데모</button></div>{!googleConfigured && <p className="notice">로컬에서는 데모 로그인으로 모든 기능을 확인할 수 있습니다.</p>}{message && <p className="error">{message}</p>}</div><aside className="preview"><p>공식 API 기반 보호 분석</p><strong>초기 경보 감지</strong><span>YouTube · NAVER · 허가 데이터</span></aside></section></main></>;
}
