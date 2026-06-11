"use client";
import { useEffect, useRef, useCallback } from "react";
import { WSEvent, Issue, Comment } from "@/types";
import { useReviewStore } from "@/store";
import { useAuthStore } from "@/store";
import toast from "react-hot-toast";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function useReviewSocket(reviewId: string | null) {
  const ws = useRef<WebSocket | null>(null);
  const { token } = useAuthStore();
  const { appendIssues, setActiveUsers, addCommentLocal, setReviewStatus } = useReviewStore();
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    if (!reviewId || !token) return;

    const url = `${WS_URL}/ws/review/${reviewId}?token=${token}`;
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => {
      console.log("[WS] Connected to review room:", reviewId);
      // Heartbeat
      const ping = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "ping" }));
        }
      }, 25000);
      socket.onclose = () => clearInterval(ping);
    };

    socket.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data);
        handleEvent(event);
      } catch {}
    };

    socket.onerror = () => {
      console.warn("[WS] Error — will reconnect");
    };

    socket.onclose = () => {
      // Auto-reconnect after 3 seconds
      reconnectTimer.current = setTimeout(connect, 3000);
    };
  }, [reviewId, token]);

  const handleEvent = (event: WSEvent) => {
    switch (event.type) {
      case "user_joined":
        setActiveUsers(event.active_users);
        toast(`${event.username} joined the review`, { icon: "👋" });
        break;

      case "user_left":
        setActiveUsers(event.active_users);
        toast(`${event.username} left`, { icon: "🚪" });
        break;

      case "review_complete":
        setReviewStatus("complete");
        appendIssues(event.issues as Issue[]);
        toast.success(`Review complete — ${event.issue_count} issue${event.issue_count !== 1 ? "s" : ""} found`);
        break;

      case "review_error":
        setReviewStatus("error");
        toast.error("Review failed: " + event.error);
        break;

      case "new_comment":
        addCommentLocal({
          id: event.comment_id,
          review_id: reviewId!,
          user_id: event.user_id,
          issue_id: event.issue_id,
          content: event.content,
          line_number: event.line_number,
          created_at: new Date().toISOString(),
          username: event.username,
        } as Comment);
        break;

      case "cursor_move":
        // Could highlight the line in the editor — left as extension
        break;
    }
  };

  const sendCursorMove = useCallback((line: number) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: "cursor_move", line }));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  return { sendCursorMove };
}
