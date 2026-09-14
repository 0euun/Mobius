export type Target = { target_id: string; display_name: string };
export type Risk = { score: number; stage: string; confidence: number; toxicity_source: string; features: { name: string; value: number; explanation: string }[]; recommended_actions: string[] };
export type Graph = { nodes: { id: string; type: string; label: string }[]; edges: { source: string; target: string; kind: string }[]; coordination_score: number; repeated_phrase_score: number; cross_platform_concurrency: number; persistence: string };
export type HistoryItem = { id: number; created_at: string; [key: string]: unknown };
export type View = "dashboard" | "targets" | "collect" | "analysis" | "evidence" | "alerts";
