"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, Sparkles, GitCompare, Loader2, CheckCircle,
  AlertCircle, Copy, Check, Play, RotateCcw, Bug, Shield,
  Palette, Zap, ChevronRight, FileCode, Download,
} from "lucide-react";
import { useAuthStore } from "@/store";
import { useFixStream } from "@/hooks/useFixStream";
import DiffViewer from "@/components/fix/DiffViewer";
import IssueFixCard from "@/components/fix/IssueFixCard";
import api from "@/lib/api";
import toast from "react-hot-toast";
import { motion, AnimatePresence } from "framer-motion";

// ── Types ───────────────────────────────────────────────────────────────────

interface ReviewInfo {
  id: string;
  title: string;
  code: string;
  language: string;
  status: string;
  issue_count: number;
  issues: Array<{
    id: string;
    category: string;
    severity: string;
    title: string;
    description: string;
    suggestion?: string | null;
    line_start?: string | null;
    line_end?: string | null;
  }>;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function getFileExt(language?: string): string {
  const map: Record<string, string> = {
    python: "py",
    javascript: "js",
    typescript: "ts",
    go: "go",
    java: "java",
    rust: "rs",
    cpp: "cpp",
    c: "c",
    csharp: "cs",
    ruby: "rb",
    php: "php",
  };
  return map[language ?? ""] ?? "txt";
}

function downloadFile(content: string, language?: string) {
  const ext = getFileExt(language);
  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `fixed.${ext}`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Phase stepper ────────────────────────────────────────────────────────────

const PHASES = [
  { key: "planning", label: "Planning fixes", icon: Sparkles },
  { key: "generating", label: "Writing fixed code", icon: FileCode },
  { key: "explaining", label: "Explaining changes", icon: GitCompare },
  { key: "complete", label: "Done", icon: CheckCircle },
];

function PhaseStepper({ phase }: { phase: string }) {
  const phaseIndex = PHASES.findIndex((p) => p.key === phase);
  return (
    <div className="flex items-center gap-0 overflow-x-auto py-1">
      {PHASES.map((p, i) => {
        const Icon = p.icon;
        const done = i < phaseIndex;
        const active = i === phaseIndex;
        return (
          <div key={p.key} className="flex items-center">
            <div
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono whitespace-nowrap transition-all duration-500 ${
                done
                  ? "text-green-400 bg-green-500/10 border border-green-500/20"
                  : active
                  ? "text-accent bg-accent/10 border border-accent/30"
                  : "text-gray-600 border border-transparent"
              }`}
            >
              {done ? (
                <CheckCircle className="w-3 h-3" />
              ) : active ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Icon className="w-3 h-3" />
              )}
              {p.label}
            </div>
            {i < PHASES.length - 1 && (
              <ChevronRight className={`w-3 h-3 mx-1 flex-shrink-0 ${done ? "text-green-500/40" : "text-gray-700"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Stats bar ────────────────────────────────────────────────────────────────

function StatsBar({ lineChanges, issueCount }: {
  lineChanges: { total_added: number; total_removed: number } | null;
  issueCount: number;
}) {
  if (!lineChanges) return null;
  return (
    <div className="flex items-center gap-4 text-xs font-mono">
      <span className="text-green-400">+{lineChanges.total_added} added</span>
      <span className="text-red-400">−{lineChanges.total_removed} removed</span>
      <span className="text-gray-500">{issueCount} issues fixed</span>
    </div>
  );
}

// ── Copy button ──────────────────────────────────────────────────────────────

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono text-gray-400 hover:text-white border border-border hover:border-gray-600 transition-all"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? "Copied!" : label}
    </button>
  );
}

// ── Code panel ───────────────────────────────────────────────────────────────

function CodePanel({ title, code, language, badge }: {
  title: string;
  code: string;
  language: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface/80">
        <div className="flex items-center gap-2">
          <FileCode className="w-3.5 h-3.5 text-gray-500" />
          <span className="text-xs font-mono text-gray-400">{title}</span>
          {badge}
        </div>
        <CopyButton text={code} />
      </div>
      <div className="flex-1 overflow-auto bg-[#090b10]">
        <pre className="p-4 text-xs font-mono text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
          {code}
        </pre>
      </div>
    </div>
  );
}

// ── Confirm Modal ────────────────────────────────────────────────────────────

function ConfirmModal({
  issueCount,
  onConfirm,
  onCancel,
}: {
  issueCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-surface border border-border rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl"
      >
        <div className="w-12 h-12 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center mx-auto mb-4">
          <Sparkles className="w-6 h-6 text-accent" />
        </div>
        <h3 className="text-base font-semibold text-white text-center mb-2">Run Fix-It?</h3>
        <p className="text-sm text-gray-400 text-center mb-1">
          This will use{" "}
          <span className="text-white font-medium">1 of your 50 daily requests</span> to generate
          fixes for{" "}
          <span className="text-white font-medium">{issueCount} issue{issueCount !== 1 ? "s" : ""}</span>.
        </p>
        <p className="text-xs text-gray-600 text-center mb-6">
          Powered by Groq · usually takes 10–20 seconds
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2.5 rounded-xl border border-border text-sm text-gray-400 hover:text-white hover:border-gray-600 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2.5 rounded-xl bg-accent text-bg text-sm font-semibold hover:bg-accent/90 transition-all glow-accent"
          >
            Run Fix-It
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function FixItPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { token, hydrate } = useAuthStore();

  const [reviewInfo, setReviewInfo] = useState<ReviewInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"diff" | "side-by-side" | "fixed">("diff");
  const [started, setStarted] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const {
    phase, plan, fixTokens, fixedCode, diff, lineChanges,
    explanations, activeExplainId, explainTokens, issueCount,
    error, start, reset,
  } = useFixStream(id, token);

  useEffect(() => { hydrate(); }, []);

  useEffect(() => {
    if (!token) { router.push("/auth"); return; }
    api.get<ReviewInfo>(`/api/fix/${id}`)
      .then(({ data }) => setReviewInfo(data))
      .catch(() => toast.error("Failed to load review"))
      .finally(() => setLoading(false));
  }, [token, id]);

  const handleStart = () => {
    setShowConfirm(false);
    setStarted(true);
    start();
  };

  const handleReset = () => {
    reset();
    setStarted(false);
  };

  const isRunning = ["planning", "generating", "explaining"].includes(phase);
  const isDone = phase === "complete";
  const isError = phase === "error";

  const planMap = Object.fromEntries(plan.map((p) => [p.issue_id, p]));
  const displayCode = fixedCode || fixTokens;
  const fileExt = getFileExt(reviewInfo?.language);
  const originalFilename = `original.${fileExt}`;
  const fixedFilename = `fixed.${fileExt}`;

  return (
    <div className="min-h-screen bg-bg flex flex-col">

      {/* ── Top bar ──────────────────────────────────────────────────────────── */}
      <header className="border-b border-border bg-surface/50 backdrop-blur sticky top-0 z-20">
        <div className="px-4 h-14 flex items-center gap-4">
          <button
            onClick={() => router.push(`/review/${id}`)}
            className="text-gray-500 hover:text-white transition-colors flex items-center gap-1.5 text-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Back to review</span>
          </button>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className="w-5 h-5 rounded-md bg-accent/10 border border-accent/30 flex items-center justify-center">
                <Sparkles className="w-3 h-3 text-accent" />
              </div>
              <h1 className="text-sm font-semibold text-white truncate">
                Fix-It Mode
                {reviewInfo && (
                  <span className="text-gray-500 font-normal ml-2">— {reviewInfo.title}</span>
                )}
              </h1>
            </div>
          </div>

          {isDone && (
            <StatsBar lineChanges={lineChanges} issueCount={issueCount} />
          )}

          <div className="flex items-center gap-2">
            {!started && !isRunning && !isDone && !isError && (
              <button
                onClick={() => setShowConfirm(true)}
                disabled={loading || reviewInfo?.status !== "complete"}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-bg text-sm font-semibold hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all glow-accent"
              >
                <Play className="w-3.5 h-3.5" />
                Run Fix-It
              </button>
            )}
            {isRunning && (
              <span className="flex items-center gap-1.5 text-xs text-accent font-mono">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Working...
              </span>
            )}
            {(isDone || isError) && (
              <button
                onClick={handleReset}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm text-gray-400 hover:text-white hover:border-gray-600 transition-all"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Re-run
              </button>
            )}
            {isDone && (
              <div className="flex items-center gap-2">
                <CopyButton text={fixedCode} label="Copy" />
                <button
                  onClick={() => downloadFile(fixedCode, reviewInfo?.language)}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono text-gray-400 hover:text-white border border-border hover:border-gray-600 transition-all"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download {fixedFilename}
                </button>
              </div>
            )}
          </div>
        </div>

        {(isRunning || isDone) && (
          <div className="px-4 pb-2.5 border-t border-border/50 pt-2">
            <PhaseStepper phase={phase} />
          </div>
        )}
      </header>

      {/* ── Content ──────────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="flex items-center justify-center flex-1">
          <Loader2 className="w-6 h-6 text-accent animate-spin" />
        </div>
      ) : isError ? (
        <div className="flex items-center justify-center flex-1">
          <div className="text-center max-w-sm">
            <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-3 opacity-70" />
            <p className="text-sm text-gray-300 mb-1">Fix-It failed</p>
            <p className="text-xs text-gray-500 mb-4">{error}</p>
            <button onClick={handleReset} className="text-sm text-accent hover:underline">Try again</button>
          </div>
        </div>
      ) : !started ? (
        /* ── Landing / pre-run state ─────────────────────────────────────────── */
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="max-w-lg w-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center mx-auto mb-6">
              <Sparkles className="w-8 h-8 text-accent" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">Fix-It Mode</h2>
            <p className="text-gray-400 mb-2 leading-relaxed">
              The AI will read every issue found in your review and generate a{" "}
              <span className="text-white">fully corrected version</span> of your code — then stream a live
              explanation for each fix, so you understand exactly what changed and why.
            </p>
            <p className="text-gray-600 text-sm mb-8">
              Powered by Groq · {reviewInfo?.issues?.length ?? 0} issues to address
            </p>

            {reviewInfo && reviewInfo.issues.length > 0 && (
              <div className="mb-8 text-left space-y-2 max-h-48 overflow-y-auto">
                {reviewInfo.issues.map((issue) => {
                  const icons: Record<string, React.ReactNode> = {
                    bug: <Bug className="w-3.5 h-3.5 text-red-400" />,
                    security: <Shield className="w-3.5 h-3.5 text-orange-400" />,
                    style: <Palette className="w-3.5 h-3.5 text-purple-400" />,
                    performance: <Zap className="w-3.5 h-3.5 text-yellow-400" />,
                  };
                  return (
                    <div key={issue.id} className="flex items-center gap-2 bg-surface border border-border rounded-lg px-3 py-2">
                      {icons[issue.category] || icons.bug}
                      <span className="text-xs text-gray-300 truncate">{issue.title}</span>
                      <span className="ml-auto text-xs text-gray-600 font-mono">{issue.severity}</span>
                    </div>
                  );
                })}
              </div>
            )}

            {reviewInfo?.status !== "complete" ? (
              <div className="flex items-center gap-2 justify-center text-sm text-yellow-400">
                <AlertCircle className="w-4 h-4" />
                Review must finish before running Fix-It
              </div>
            ) : (
              <button
                onClick={() => setShowConfirm(true)}
                className="flex items-center gap-2 px-8 py-3 rounded-2xl bg-accent text-bg text-base font-bold hover:bg-accent/90 transition-all mx-auto glow-accent"
              >
                <Play className="w-4 h-4" />
                Run Fix-It
              </button>
            )}
          </div>
        </div>
      ) : (
        /* ── Active / done state ─────────────────────────────────────────────── */
        <div className="flex flex-1 overflow-hidden">

          {/* Left: code / diff area */}
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

            {(displayCode || diff) && (
              <div className="flex items-center gap-1 px-4 py-2 border-b border-border bg-surface/30">
                {[
                  { key: "diff", label: "Diff", icon: GitCompare },
                  { key: "side-by-side", label: "Side by side", icon: GitCompare },
                  { key: "fixed", label: "Fixed code", icon: FileCode },
                ].map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    onClick={() => setView(key as typeof view)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-all ${
                      view === key
                        ? "bg-accent/10 text-accent border border-accent/30"
                        : "text-gray-500 hover:text-gray-300 border border-transparent"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {label}
                  </button>
                ))}

                <div className="ml-auto">
                  {isDone && lineChanges && (
                    <StatsBar lineChanges={lineChanges} issueCount={issueCount} />
                  )}
                </div>
              </div>
            )}

            <div className="flex-1 overflow-hidden">
              <AnimatePresence mode="wait">
                {view === "diff" ? (
                  <motion.div key="diff" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-full overflow-auto p-4">
                    {diff ? (
                      <DiffViewer diff={diff} />
                    ) : phase === "planning" ? (
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                          <Sparkles className="w-8 h-8 text-accent mx-auto mb-3 opacity-60 animate-pulse" />
                          <p className="text-sm text-gray-400">Planning fixes across {reviewInfo?.issues?.length} issues...</p>
                        </div>
                      </div>
                    ) : phase === "generating" ? (
                      <div className="p-4">
                        <p className="text-xs text-gray-500 font-mono mb-3">Generating fixed code...</p>
                        <pre className="text-xs font-mono text-gray-300 leading-relaxed whitespace-pre-wrap break-words opacity-80">
                          {fixTokens}
                          <span className="inline-block w-1.5 h-4 bg-accent/70 ml-0.5 animate-pulse rounded-sm" />
                        </pre>
                      </div>
                    ) : null}
                  </motion.div>
                ) : view === "side-by-side" ? (
                  <motion.div key="side" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-full grid grid-cols-2 divide-x divide-border">
                    <CodePanel
                      title={originalFilename}
                      code={reviewInfo?.code ?? ""}
                      language={reviewInfo?.language ?? ""}
                      badge={<span className="text-xs text-gray-600 font-mono ml-1">original</span>}
                    />
                    <CodePanel
                      title={fixedFilename}
                      code={displayCode}
                      language={reviewInfo?.language ?? ""}
                      badge={
                        isDone
                          ? <span className="text-xs text-green-400 font-mono ml-1">fixed ✓</span>
                          : <span className="text-xs text-accent font-mono ml-1 animate-pulse">writing...</span>
                      }
                    />
                  </motion.div>
                ) : (
                  <motion.div key="fixed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-full flex flex-col">
                    <CodePanel
                      title={fixedFilename}
                      code={displayCode}
                      language={reviewInfo?.language ?? ""}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Right panel: issues + fix explanations */}
          <div className="w-full max-w-sm xl:max-w-md flex flex-col bg-surface border-l border-border overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <GitCompare className="w-4 h-4 text-accent" />
                <span className="text-sm font-medium text-white">Fix explanations</span>
              </div>
              {isDone && (
                <span className="text-xs text-green-400 font-mono flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  All fixed
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {phase === "planning" && (
                <div className="text-center py-12">
                  <Sparkles className="w-7 h-7 text-accent mx-auto mb-3 animate-pulse" />
                  <p className="text-sm text-gray-400">Groq is planning your fixes...</p>
                </div>
              )}

              {reviewInfo?.issues.map((issue, index) => {
                const planItem = planMap[issue.id];
                const explanation = explanations[issue.id];
                const liveExplain = explainTokens[issue.id];
                const isThisExplaining = activeExplainId === issue.id;
                const isThisFixed = !!explanation;

                if (!planItem && phase === "planning") return null;

                return (
                  <IssueFixCard
                    key={issue.id}
                    issue={issue}
                    planSummary={planItem?.fix_summary}
                    explanation={explanation}
                    explainTokens={liveExplain}
                    isExplaining={isThisExplaining}
                    isFixed={isThisFixed}
                    index={index}
                  />
                );
              })}

              {isDone && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-4 p-4 bg-green-500/5 border border-green-500/20 rounded-xl text-center"
                >
                  <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-2 opacity-80" />
                  <p className="text-sm text-green-300 font-medium mb-1">All fixes applied</p>
                  <p className="text-xs text-gray-500 mb-3">Copy or download the fixed code.</p>
                  <div className="flex items-center justify-center gap-2 flex-wrap">
                    <CopyButton text={fixedCode} label="Copy fixed code" />
                    <button
                      onClick={() => downloadFile(fixedCode, reviewInfo?.language)}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono text-gray-400 hover:text-white border border-border hover:border-gray-600 transition-all"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download {fixedFilename}
                    </button>
                  </div>
                </motion.div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Confirm Modal ─────────────────────────────────────────────────────── */}
      {showConfirm && (
        <ConfirmModal
          issueCount={reviewInfo?.issues?.length ?? 0}
          onConfirm={handleStart}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </div>
  );
}
