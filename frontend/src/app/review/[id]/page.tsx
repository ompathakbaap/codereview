"use client";
import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, Bug, Shield, Palette, Zap, Users, MessageSquare,
  Loader2, CheckCircle, AlertCircle, Send, SlidersHorizontal, Activity, Sparkles,
} from "lucide-react";
import { useAuthStore, useReviewStore } from "@/store";
import { useReviewSocket } from "@/hooks/useReviewSocket";
import { useReviewStream } from "@/hooks/useReviewStream";
import IssueCard from "@/components/review/IssueCard";
import { Issue, Category } from "@/types";
import toast from "react-hot-toast";

const CodeMirrorEditor = dynamic(() => import("@/components/editor/CodeEditor"), { ssr: false });

const CATEGORY_FILTERS: { key: Category | "all"; icon: React.ReactNode; label: string }[] = [
  { key: "all",         icon: <SlidersHorizontal className="w-3.5 h-3.5" />, label: "All" },
  { key: "bug",         icon: <Bug className="w-3.5 h-3.5" />,    label: "Bugs" },
  { key: "security",    icon: <Shield className="w-3.5 h-3.5" />, label: "Security" },
  { key: "style",       icon: <Palette className="w-3.5 h-3.5" />,label: "Style" },
  { key: "performance", icon: <Zap className="w-3.5 h-3.5" />,    label: "Perf" },
];

const NODE_ORDER = ["analyze_structure", "bug_check", "security_check", "style_check", "performance_check"];

// ── Streaming Progress Panel ───────────────────────────────────────────────────

function StreamingPanel({ nodeProgress, activeNodes }: {
  nodeProgress: Record<string, { label: string; tokens: string; done: boolean; issueCount: number }>;
  activeNodes: Set<string>;
}) {
  const nodes = NODE_ORDER.filter(n => nodeProgress[n]);
  if (nodes.length === 0) return null;

  return (
    <div className="px-3 py-3 border-b border-border space-y-2">
      <div className="flex items-center gap-1.5 text-xs text-accent font-mono mb-2">
        <Activity className="w-3 h-3 animate-pulse" />
        Agent streaming...
      </div>
      {nodes.map(node => {
        const p = nodeProgress[node];
        return (
          <div key={node} className="bg-bg border border-border rounded-lg p-2.5">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-300">{p.label}</span>
              {p.done ? (
                <span className="text-xs text-green-400 font-mono">
                  ✓ {p.issueCount} issue{p.issueCount !== 1 ? "s" : ""}
                </span>
              ) : activeNodes.has(node) ? (
                <Loader2 className="w-3 h-3 text-accent animate-spin" />
              ) : null}
            </div>
            {!p.done && p.tokens && (
              <p className="text-xs text-gray-600 font-mono truncate">{p.tokens.slice(-80)}</p>
            )}
            {p.done && (
              <div className="h-0.5 bg-green-500/30 rounded-full mt-1">
                <div className="h-full bg-green-500/60 rounded-full w-full transition-all duration-500" />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { token, user, hydrate } = useAuthStore();
  const {
    activeReview, issues, comments, activeUsers,
    fetchReview, fetchComments, addComment, isLoading, appendIssues, setReviewStatus,
  } = useReviewStore();

  const [filter, setFilter] = useState<Category | "all">("all");
  const [commentText, setCommentText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [tab, setTab] = useState<"issues" | "comments">("issues");
  const [streamStarted, setStreamStarted] = useState(false);
  const commentEndRef = useRef<HTMLDivElement>(null);

  // WebSocket for collaboration
  useReviewSocket(id);

  // SSE stream for live agent output
  const { isStreaming, nodeProgress, activeNodes, streamedIssues, start: startStream } = useReviewStream(id, token);

  useEffect(() => { hydrate(); }, []);

  useEffect(() => {
    if (!token) { router.push("/auth"); return; }
    if (id) {
      fetchReview(id).then(() => {});
      fetchComments(id);
    }
  }, [token, id]);

  // Auto-start SSE stream when review is running
  useEffect(() => {
    if (activeReview?.status === "running" && !streamStarted && token) {
      setStreamStarted(true);
      startStream();
    }
  }, [activeReview?.status, streamStarted, token]);

  // When SSE surfaces issues before WebSocket fires, show them immediately
  useEffect(() => {
    if (streamedIssues.length > 0 && issues.length === 0) {
      appendIssues(streamedIssues);
    }
  }, [streamedIssues]);

  useEffect(() => {
    commentEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [comments]);

  const allIssues = issues.length > 0 ? issues : streamedIssues;
  const filteredIssues = filter === "all" ? allIssues : allIssues.filter(i => i.category === filter);

  const issueCounts = CATEGORY_FILTERS.reduce((acc, f) => {
    acc[f.key] = f.key === "all" ? allIssues.length : allIssues.filter(i => i.category === f.key).length;
    return acc;
  }, {} as Record<string, number>);

  const handleComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    setSubmitting(true);
    try {
      await addComment(id, { content: commentText });
      setCommentText("");
    } catch {
      toast.error("Failed to post comment");
    } finally {
      setSubmitting(false);
    }
  };

  const status = activeReview?.status;

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      {/* Top bar */}
      <header className="border-b border-border bg-surface/50 backdrop-blur sticky top-0 z-10">
        <div className="px-4 h-14 flex items-center gap-4">
          <button onClick={() => router.push("/dashboard")}
            className="text-gray-500 hover:text-white transition-colors flex items-center gap-1.5 text-sm">
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Dashboard</span>
          </button>

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-medium text-white truncate">{activeReview?.title ?? "Loading..."}</h1>
            <div className="flex items-center gap-2">
              {(status === "running" || isStreaming) && (
                <span className="text-xs text-accent font-mono flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {isStreaming ? "Streaming analysis..." : "AI reviewing..."}
                </span>
              )}
              {status === "complete" && !isStreaming && (
                <span className="text-xs text-green-400 font-mono flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />{allIssues.length} issue{allIssues.length !== 1 ? "s" : ""}
                </span>
              )}
              {status === "error" && (
                <span className="text-xs text-red-400 font-mono flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />Review failed
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <Users className="w-3.5 h-3.5" />
            <span className="font-mono">{Math.max(1, activeUsers.length)}</span>
          </div>

          {status === "complete" && !isStreaming && allIssues.length > 0 && (
            <button
              onClick={() => router.push(`/fix/${id}`)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent text-xs font-semibold transition-all glow-accent"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Fix-It
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left — Code */}
        <div className="flex-1 overflow-auto border-r border-border">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-6 h-6 text-accent animate-spin" />
            </div>
          ) : activeReview ? (
            <CodeMirrorEditor code={activeReview.code} language={activeReview.language} issues={allIssues} />
          ) : null}
        </div>

        {/* Right panel */}
        <div className="w-full max-w-sm xl:max-w-md flex flex-col bg-surface">
          {/* Tab bar */}
          <div className="flex border-b border-border">
            <button onClick={() => setTab("issues")}
              className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${tab === "issues" ? "text-accent border-b-2 border-accent" : "text-gray-500 hover:text-gray-300"}`}>
              <Bug className="w-4 h-4" />Issues
              {allIssues.length > 0 && (
                <span className="text-xs bg-accent/10 text-accent border border-accent/20 px-1.5 py-0.5 rounded-full font-mono">{allIssues.length}</span>
              )}
            </button>
            <button onClick={() => setTab("comments")}
              className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${tab === "comments" ? "text-accent border-b-2 border-accent" : "text-gray-500 hover:text-gray-300"}`}>
              <MessageSquare className="w-4 h-4" />Discussion
              {comments.length > 0 && (
                <span className="text-xs bg-surface text-gray-400 border border-border px-1.5 py-0.5 rounded-full font-mono">{comments.length}</span>
              )}
            </button>
          </div>

          <AnimatePresence mode="wait">
            {tab === "issues" ? (
              <motion.div key="issues" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col flex-1 overflow-hidden">

                {/* SSE streaming progress */}
                {isStreaming && (
                  <StreamingPanel nodeProgress={nodeProgress} activeNodes={activeNodes} />
                )}

                {/* Category filters */}
                <div className="flex gap-1.5 p-3 border-b border-border overflow-x-auto">
                  {CATEGORY_FILTERS.map(f => (
                    <button key={f.key} onClick={() => setFilter(f.key)}
                      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${filter === f.key ? "bg-accent/10 text-accent border border-accent/30" : "text-gray-500 hover:text-gray-300 border border-transparent"}`}>
                      {f.icon}{f.label}
                      {issueCounts[f.key] > 0 && <span className="font-mono opacity-70">{issueCounts[f.key]}</span>}
                    </button>
                  ))}
                </div>

                {/* Issues list */}
                <div className="flex-1 overflow-y-auto p-3 space-y-2">
                  {(status === "running" || isStreaming) && allIssues.length === 0 && (
                    <div className="text-center py-12">
                      <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin mx-auto mb-3" />
                      <p className="text-sm text-gray-400">Agent is analyzing your code...</p>
                      <p className="text-xs text-gray-600 mt-1 font-mono">LangGraph · 4 parallel checks · Groq</p>
                    </div>
                  )}
                  {filteredIssues.length === 0 && status === "complete" && !isStreaming && (
                    <div className="text-center py-12">
                      <CheckCircle className="w-10 h-10 text-green-500 mx-auto mb-3 opacity-60" />
                      <p className="text-sm text-gray-400">
                        {filter === "all" ? "No issues found!" : `No ${filter} issues`}
                      </p>
                    </div>
                  )}
                  {filteredIssues.map(issue => (
                    <IssueCard key={issue.id} issue={issue} />
                  ))}
                </div>
              </motion.div>
            ) : (
              <motion.div key="comments" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col flex-1 overflow-hidden">
                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  {comments.length === 0 && (
                    <div className="text-center py-12">
                      <MessageSquare className="w-8 h-8 text-gray-700 mx-auto mb-3" />
                      <p className="text-sm text-gray-500">No discussion yet. Start the conversation.</p>
                    </div>
                  )}
                  {comments.map(c => (
                    <div key={c.id} className="bg-bg border border-border rounded-xl p-3">
                      <div className="flex items-center gap-2 mb-1.5">
                        <div className="w-6 h-6 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center text-xs font-bold text-accent">
                          {(c.username || "?")[0].toUpperCase()}
                        </div>
                        <span className="text-xs font-mono text-accent">{c.username}</span>
                        <span className="text-xs text-gray-600">
                          {new Date(c.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                      <p className="text-sm text-gray-300">{c.content}</p>
                    </div>
                  ))}
                  <div ref={commentEndRef} />
                </div>

                <div className="p-3 border-t border-border">
                  <form onSubmit={handleComment} className="flex gap-2">
                    <input value={commentText} onChange={e => setCommentText(e.target.value)}
                      placeholder="Add a comment..."
                      className="flex-1 bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-colors" />
                    <button type="submit" disabled={submitting || !commentText.trim()}
                      className="p-2 rounded-lg bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent disabled:opacity-40 transition-all">
                      {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                  </form>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
