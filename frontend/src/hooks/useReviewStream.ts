import { useEffect, useRef, useState, useCallback } from "react";
import { SSEEvent, Issue } from "@/types";

interface StreamState {
  isStreaming: boolean;
  activeNodes: Set<string>;
  nodeProgress: Record<string, { label: string; tokens: string; done: boolean; issueCount: number }>;
  streamedIssues: Issue[];
  error: string | null;
}

/**
 * useReviewStream — SSE hook for real-time agent progress
 *
 * Connects to GET /api/reviews/{id}/stream and exposes:
 *  - isStreaming: true while SSE is active
 *  - nodeProgress: per-node token buffer + done state
 *  - streamedIssues: issues as they arrive (before final WebSocket broadcast)
 *  - start() / stop() controls
 */
export function useReviewStream(reviewId: string, token: string | null) {
  const [state, setState] = useState<StreamState>({
    isStreaming: false,
    activeNodes: new Set(),
    nodeProgress: {},
    streamedIssues: [],
    error: null,
  });

  const esRef = useRef<EventSource | null>(null);

  const stop = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setState(s => ({ ...s, isStreaming: false }));
  }, []);

  const start = useCallback(() => {
    if (!token || !reviewId || esRef.current) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    // Pass JWT via query param since EventSource doesn't support headers
    const url = `${apiUrl}/api/reviews/${reviewId}/stream?token=${encodeURIComponent(token)}`;

    const es = new EventSource(url);
    esRef.current = es;

    setState(s => ({ ...s, isStreaming: true, error: null }));

    es.onmessage = (e) => {
      let event: SSEEvent;
      try {
        event = JSON.parse(e.data);
      } catch {
        return;
      }

      setState(s => {
        switch (event.type) {
          case "node_start": {
            const next = new Map(s.activeNodes);
            next.add(event.node);
            return {
              ...s,
              activeNodes: new Set(next),
              nodeProgress: {
                ...s.nodeProgress,
                [event.node]: { label: event.label, tokens: "", done: false, issueCount: 0 },
              },
            };
          }
          case "token": {
            const prev = s.nodeProgress[event.node];
            if (!prev) return s;
            return {
              ...s,
              nodeProgress: {
                ...s.nodeProgress,
                [event.node]: { ...prev, tokens: prev.tokens + event.text },
              },
            };
          }
          case "node_done": {
            const prev = s.nodeProgress[event.node];
            const nextNodes = new Set(s.activeNodes);
            nextNodes.delete(event.node);
            return {
              ...s,
              activeNodes: nextNodes,
              streamedIssues: [...s.streamedIssues, ...(event.issues || [])],
              nodeProgress: {
                ...s.nodeProgress,
                [event.node]: { ...(prev || { label: event.node, tokens: "" }), done: true, issueCount: event.issue_count },
              },
            };
          }
          case "complete": {
            es.close();
            return { ...s, isStreaming: false, activeNodes: new Set() };
          }
          case "error": {
            es.close();
            return { ...s, isStreaming: false, error: event.message };
          }
          default:
            return s;
        }
      });
    };

    es.onerror = () => {
      es.close();
      setState(s => ({ ...s, isStreaming: false }));
    };
  }, [reviewId, token]);

  // Clean up on unmount
  useEffect(() => () => { esRef.current?.close(); }, []);

  return { ...state, start, stop };
}
