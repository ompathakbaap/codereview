"use client";
import { useState, useCallback, useRef } from "react";

export interface FixPlanItem {
  issue_id: string;
  fix_summary: string;
  priority: string;
}

export interface LineChanges {
  added: number[];
  removed: number[];
  total_added: number;
  total_removed: number;
}

export type FixPhase =
  | "idle"
  | "planning"
  | "generating"
  | "explaining"
  | "complete"
  | "error";

export interface FixState {
  phase: FixPhase;
  plan: FixPlanItem[];
  fixTokens: string;         // accumulated raw tokens during generation
  fixedCode: string;         // final fixed code
  diff: string;              // unified diff string
  lineChanges: LineChanges | null;
  explanations: Record<string, string>;  // issue_id → explanation text
  activeExplainId: string | null;        // which issue is streaming its explanation now
  explainTokens: Record<string, string>; // live token accumulation per issue
  issueCount: number;
  error: string | null;
}

const INITIAL_STATE: FixState = {
  phase: "idle",
  plan: [],
  fixTokens: "",
  fixedCode: "",
  diff: "",
  lineChanges: null,
  explanations: {},
  activeExplainId: null,
  explainTokens: {},
  issueCount: 0,
  error: null,
};

export function useFixStream(reviewId: string, token: string | null) {
  const [state, setState] = useState<FixState>(INITIAL_STATE);
  const esRef = useRef<EventSource | null>(null);

  const start = useCallback(() => {
    if (!token || !reviewId) return;
    if (esRef.current) esRef.current.close();

    setState({ ...INITIAL_STATE, phase: "planning" });

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const url = `${apiBase}/api/fix/${reviewId}/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);

        switch (event.type) {
          case "fix_start":
            setState((s) => ({ ...s, phase: "planning", issueCount: event.issue_count }));
            break;

          case "plan_done":
            setState((s) => ({ ...s, phase: "generating", plan: event.plan }));
            break;

          case "fix_token":
            setState((s) => ({ ...s, fixTokens: s.fixTokens + event.text }));
            break;

          case "fix_code_done":
            setState((s) => ({
              ...s,
              phase: "explaining",
              fixedCode: event.fixed_code,
              diff: event.diff,
              lineChanges: event.line_changes,
              fixTokens: event.fixed_code, // finalize
            }));
            break;

          case "explain_start":
            setState((s) => ({
              ...s,
              activeExplainId: event.issue_id,
              explainTokens: { ...s.explainTokens, [event.issue_id]: "" },
            }));
            break;

          case "explain_token":
            setState((s) => ({
              ...s,
              explainTokens: {
                ...s.explainTokens,
                [event.issue_id]: (s.explainTokens[event.issue_id] || "") + event.text,
              },
            }));
            break;

          case "explain_done":
            setState((s) => ({
              ...s,
              explanations: { ...s.explanations, [event.issue_id]: event.explanation },
            }));
            break;

          case "complete":
            setState((s) => ({
              ...s,
              phase: "complete",
              fixedCode: event.fixed_code,
              diff: event.diff,
              lineChanges: event.line_changes,
              explanations: event.explanations,
              activeExplainId: null,
            }));
            es.close();
            break;

          case "error":
            setState((s) => ({ ...s, phase: "error", error: event.message }));
            es.close();
            break;
        }
      } catch {}
    };

    es.onerror = () => {
      setState((s) =>
        s.phase !== "complete"
          ? { ...s, phase: "error", error: "Connection lost. Please try again." }
          : s
      );
      es.close();
    };
  }, [reviewId, token]);

  const reset = useCallback(() => {
    esRef.current?.close();
    setState(INITIAL_STATE);
  }, []);

  return { ...state, start, reset };
}
