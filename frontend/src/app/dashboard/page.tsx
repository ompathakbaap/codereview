"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, Code2, LogOut, Clock, CheckCircle, AlertCircle, Loader2,
  Bug, Shield, Palette, Zap, GitPullRequest, BarChart2, X,
} from "lucide-react";
import { useAuthStore, useReviewStore } from "@/store";
import { Review, ReviewStats } from "@/types";
import api from "@/lib/api";
import toast from "react-hot-toast";

const LANGUAGES = ["python", "javascript", "typescript", "java", "go", "rust", "cpp", "csharp", "unknown"];

// ── Sub-components ─────────────────────────────────────────────────────────────

const StatusIcon = ({ status }: { status: Review["status"] }) => {
  if (status === "complete") return <CheckCircle className="w-4 h-4 text-green-400" />;
  if (status === "running") return <Loader2 className="w-4 h-4 text-accent animate-spin" />;
  if (status === "error") return <AlertCircle className="w-4 h-4 text-red-400" />;
  return <Clock className="w-4 h-4 text-gray-400" />;
};

const CategoryBadge = ({ cat, count }: { cat: string; count: number }) => {
  const map: Record<string, { icon: React.ReactNode; cls: string }> = {
    bug:         { icon: <Bug className="w-3 h-3" />,    cls: "text-red-400 bg-red-500/10 border-red-500/20" },
    security:    { icon: <Shield className="w-3 h-3" />, cls: "text-orange-400 bg-orange-500/10 border-orange-500/20" },
    style:       { icon: <Palette className="w-3 h-3" />,cls: "text-purple-400 bg-purple-500/10 border-purple-500/20" },
    performance: { icon: <Zap className="w-3 h-3" />,    cls: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" },
  };
  const m = map[cat];
  if (!m || count === 0) return null;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs border font-mono ${m.cls}`}>
      {m.icon}{count}
    </span>
  );
};

// ── Stats Panel ────────────────────────────────────────────────────────────────

function StatsPanel({ stats }: { stats: ReviewStats }) {
  const catColors: Record<string, string> = {
    bug: "#f87171", security: "#fb923c", style: "#c084fc", performance: "#facc15",
  };
  const sevColors: Record<string, string> = {
    critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e", info: "#6b7280",
  };

  const catTotal = Object.values(stats.issues_by_category).reduce((a, b) => a + b, 0) || 1;
  const sevTotal = Object.values(stats.issues_by_severity).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      {/* Summary cards */}
      <div className="bg-surface border border-border rounded-xl p-4">
        <p className="text-xs text-gray-500 font-mono uppercase tracking-wider mb-1">Total Reviews</p>
        <p className="text-3xl font-bold text-white">{stats.total_reviews}</p>
      </div>
      <div className="bg-surface border border-border rounded-xl p-4">
        <p className="text-xs text-gray-500 font-mono uppercase tracking-wider mb-1">Issues Found</p>
        <p className="text-3xl font-bold text-accent">{stats.total_issues}</p>
      </div>

      {/* Issues by category — horizontal bars */}
      <div className="bg-surface border border-border rounded-xl p-4 col-span-2 md:col-span-1">
        <p className="text-xs text-gray-500 font-mono uppercase tracking-wider mb-3">By Category</p>
        <div className="space-y-2">
          {["bug", "security", "style", "performance"].map((cat) => {
            const count = stats.issues_by_category[cat] || 0;
            const pct = Math.round((count / catTotal) * 100);
            return (
              <div key={cat}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-400 capitalize">{cat}</span>
                  <span className="text-gray-500 font-mono">{count}</span>
                </div>
                <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${pct}%`, backgroundColor: catColors[cat] }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Issues by severity */}
      <div className="bg-surface border border-border rounded-xl p-4 col-span-2 md:col-span-1">
        <p className="text-xs text-gray-500 font-mono uppercase tracking-wider mb-3">By Severity</p>
        <div className="space-y-2">
          {["critical", "high", "medium", "low", "info"].map((sev) => {
            const count = stats.issues_by_severity[sev] || 0;
            const pct = Math.round((count / sevTotal) * 100);
            return (
              <div key={sev}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-400 capitalize">{sev}</span>
                  <span className="text-gray-500 font-mono">{count}</span>
                </div>
                <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${pct}%`, backgroundColor: sevColors[sev] }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Create Modal ───────────────────────────────────────────────────────────────

type CreateTab = "paste" | "pr";

interface CreateModalProps {
  onClose: () => void;
  onCreated: (id: string) => void;
}

function CreateModal({ onClose, onCreated }: CreateModalProps) {
  const { createReview } = useReviewStore();
  const [tab, setTab] = useState<CreateTab>("paste");
  const [creating, setCreating] = useState(false);

  // Paste tab state
  const [pasteForm, setPasteForm] = useState({ title: "", code: "", language: "python" });

  // PR tab state
  const [prForm, setPrForm] = useState({ pr_url: "", title: "", language: "" });

  const handlePaste = async () => {
    if (!pasteForm.code.trim()) { toast.error("Paste some code first"); return; }
    setCreating(true);
    try {
      const review = await createReview(pasteForm);
      toast.success("Review started!");
      onCreated(review.id);
    } catch {
      toast.error("Failed to create review");
    } finally {
      setCreating(false);
    }
  };

  const handlePR = async () => {
    if (!prForm.pr_url.trim()) { toast.error("Enter a GitHub PR URL"); return; }
    if (!prForm.pr_url.includes("github.com")) {
      toast.error("Must be a GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)");
      return;
    }
    setCreating(true);
    try {
      const { data } = await api.post("/api/reviews/from-pr", {
        pr_url: prForm.pr_url,
        title: prForm.title || undefined,
        language: prForm.language || undefined,
      });
      toast.success("PR review started!");
      onCreated(data.id);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to fetch PR");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
        className="bg-surface border border-border rounded-2xl w-full max-w-2xl shadow-2xl"
      >
        {/* Header */}
        <div className="p-6 border-b border-border flex items-center justify-between">
          <h2 className="font-bold text-white text-lg">New Code Review</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          {([["paste", <Code2 className="w-4 h-4" />, "Paste Code"],
             ["pr",    <GitPullRequest className="w-4 h-4" />, "GitHub PR"]] as const).map(([t, icon, label]) => (
            <button
              key={t}
              onClick={() => setTab(t as CreateTab)}
              className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? "border-accent text-accent"
                  : "border-transparent text-gray-500 hover:text-gray-300"
              }`}
            >
              {icon}{label}
            </button>
          ))}
        </div>

        {/* Tab: Paste */}
        {tab === "paste" && (
          <div className="p-6 space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Title</label>
                <input
                  value={pasteForm.title}
                  onChange={e => setPasteForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="Auth middleware review"
                  className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Language</label>
                <select
                  value={pasteForm.language}
                  onChange={e => setPasteForm(f => ({ ...f, language: e.target.value }))}
                  className="bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent/50"
                >
                  {LANGUAGES.filter(l => l !== "unknown").map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Paste Code</label>
              <textarea
                value={pasteForm.code}
                onChange={e => setPasteForm(f => ({ ...f, code: e.target.value }))}
                rows={12}
                placeholder="// Paste your code here..."
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 font-mono resize-none"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white border border-border hover:border-gray-500 transition-colors">Cancel</button>
              <button onClick={handlePaste} disabled={creating} className="px-4 py-2 rounded-lg text-sm bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent font-medium transition-all disabled:opacity-50 flex items-center gap-2">
                {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                {creating ? "Starting..." : "Run AI Review"}
              </button>
            </div>
          </div>
        )}

        {/* Tab: GitHub PR */}
        {tab === "pr" && (
          <div className="p-6 space-y-4">
            <div className="bg-accent/5 border border-accent/20 rounded-lg px-4 py-3 text-sm text-accent/80">
              Paste a public GitHub PR URL. The agent will fetch the diff and review it automatically.
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">GitHub PR URL</label>
              <input
                value={prForm.pr_url}
                onChange={e => setPrForm(f => ({ ...f, pr_url: e.target.value }))}
                placeholder="https://github.com/owner/repo/pull/123"
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 font-mono"
              />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Title Override <span className="text-gray-600">(optional)</span></label>
                <input
                  value={prForm.title}
                  onChange={e => setPrForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="Auto-detected from PR"
                  className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Language <span className="text-gray-600">(optional)</span></label>
                <select
                  value={prForm.language}
                  onChange={e => setPrForm(f => ({ ...f, language: e.target.value }))}
                  className="bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent/50"
                >
                  <option value="">Auto-detect</option>
                  {LANGUAGES.filter(l => l !== "unknown").map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white border border-border hover:border-gray-500 transition-colors">Cancel</button>
              <button onClick={handlePR} disabled={creating} className="px-4 py-2 rounded-lg text-sm bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent font-medium transition-all disabled:opacity-50 flex items-center gap-2">
                {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitPullRequest className="w-4 h-4" />}
                {creating ? "Fetching PR..." : "Review PR Diff"}
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();
  const { user, token, logout, hydrate, isHydrated } = useAuthStore();
  const { reviews, fetchReviews, isLoading } = useReviewStore();
  const [showCreate, setShowCreate] = useState(false);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [showStats, setShowStats] = useState(false);

  useEffect(() => { hydrate(); }, []);

  useEffect(() => {
  if (!isHydrated) return;
  if (!token) { router.push("/auth"); return; }
  fetchReviews();
}, [isHydrated, token]);

  useEffect(() => {
    if (token && reviews.length > 0 && !stats) {
      api.get<ReviewStats>("/api/reviews/stats")
        .then(r => setStats(r.data))
        .catch(() => {});
    }
  }, [token, reviews.length]);

  const issueCounts = (review: Review) => {
    const counts: Record<string, number> = {};
    for (const i of review.issues) counts[i.category] = (counts[i.category] || 0) + 1;
    return counts;
  };

  return (
    <div className="min-h-screen bg-bg">
      {/* Nav */}
      <header className="border-b border-border bg-surface/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Code2 className="w-5 h-5 text-accent" />
            <span className="font-mono font-bold text-white">CodeReview<span className="text-accent">Agent</span></span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-400 font-mono">@{user?.username}</span>
            <button onClick={() => { logout(); router.push("/auth"); }} className="text-gray-500 hover:text-gray-300 transition-colors">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        {/* Header row */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Code Reviews</h1>
            <p className="text-gray-400 text-sm mt-1">{reviews.length} review{reviews.length !== 1 ? "s" : ""} total</p>
          </div>
          <div className="flex items-center gap-2">
            {stats && (
              <button
                onClick={() => setShowStats(s => !s)}
                className={`flex items-center gap-2 border px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  showStats
                    ? "bg-white/5 border-white/20 text-white"
                    : "border-border text-gray-400 hover:text-white hover:border-gray-500"
                }`}
              >
                <BarChart2 className="w-4 h-4" />
                {showStats ? "Hide Stats" : "Stats"}
              </button>
            )}
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 bg-accent/10 hover:bg-accent/20 border border-accent/30 hover:border-accent/60 text-accent px-4 py-2 rounded-lg text-sm font-medium transition-all"
            >
              <Plus className="w-4 h-4" />New Review
            </button>
          </div>
        </div>

        {/* Stats panel */}
        <AnimatePresence>
          {showStats && stats && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <StatsPanel stats={stats} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Create modal */}
        {showCreate && (
          <CreateModal
            onClose={() => setShowCreate(false)}
            onCreated={(id) => { setShowCreate(false); router.push(`/review/${id}`); }}
          />
        )}

        {/* Reviews list */}
        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 text-accent animate-spin" />
          </div>
        ) : reviews.length === 0 ? (
          <div className="text-center py-20">
            <Code2 className="w-12 h-12 text-gray-700 mx-auto mb-4" />
            <p className="text-gray-500">No reviews yet. Create your first one.</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {reviews.map((review, i) => {
              const counts = issueCounts(review);
              const isPR = review.code.startsWith("diff --git") || review.code.startsWith("---");
              return (
                <motion.div
                  key={review.id}
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
                  onClick={() => router.push(`/review/${review.id}`)}
                  className="bg-surface border border-border hover:border-accent/30 rounded-xl p-5 cursor-pointer group transition-all"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <StatusIcon status={review.status} />
                        <h3 className="font-medium text-white group-hover:text-accent transition-colors truncate">{review.title}</h3>
                        <span className="text-xs text-gray-600 font-mono bg-bg px-2 py-0.5 rounded">{review.language}</span>
                        {isPR && (
                          <span className="inline-flex items-center gap-1 text-xs text-blue-400 bg-blue-500/10 border border-blue-500/20 px-1.5 py-0.5 rounded font-mono">
                            <GitPullRequest className="w-3 h-3" />PR
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 font-mono mb-3">
                        {new Date(review.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </p>
                      <div className="flex gap-1.5 flex-wrap">
                        {["bug", "security", "style", "performance"].map(cat => (
                          <CategoryBadge key={cat} cat={cat} count={counts[cat] || 0} />
                        ))}
                        {review.status === "complete" && Object.keys(counts).length === 0 && (
                          <span className="text-xs text-green-400 font-mono">✓ No issues found</span>
                        )}
                      </div>
                    </div>
                    <div className="text-gray-700 group-hover:text-accent transition-colors ml-4">→</div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
