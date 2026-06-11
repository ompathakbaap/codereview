"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bug, Shield, Palette, Zap, ChevronDown, ChevronUp, Loader2, CheckCircle, Sparkles } from "lucide-react";

const CATEGORY_CONFIG = {
  bug: { icon: Bug, label: "Bug", color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/20", glow: "shadow-red-500/10" },
  security: { icon: Shield, label: "Security", color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/20", glow: "shadow-orange-500/10" },
  style: { icon: Palette, label: "Style", color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20", glow: "shadow-purple-500/10" },
  performance: { icon: Zap, label: "Performance", color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/20", glow: "shadow-yellow-500/10" },
};

const SEVERITY_CLASSES: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border border-red-500/30",
  high: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
  medium: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  low: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  info: "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30",
};

interface Issue {
  id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  suggestion?: string | null;
  line_start?: string | null;
  line_end?: string | null;
}

interface Props {
  issue: Issue;
  planSummary?: string;
  explanation?: string;
  explainTokens?: string;
  isExplaining?: boolean;
  isFixed?: boolean;
  index: number;
}

export default function IssueFixCard({
  issue,
  planSummary,
  explanation,
  explainTokens,
  isExplaining,
  isFixed,
  index,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const cfg = CATEGORY_CONFIG[issue.category as keyof typeof CATEGORY_CONFIG] || CATEGORY_CONFIG.bug;
  const Icon = cfg.icon;

  const liveText = explanation || explainTokens || "";
  const showExplanation = liveText || isExplaining;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={`border ${cfg.border} ${cfg.bg} rounded-xl overflow-hidden shadow-lg ${cfg.glow}`}
    >
      {/* Header */}
      <div
        className="p-4 flex items-start gap-3 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className={`w-8 h-8 rounded-lg ${cfg.bg} border ${cfg.border} flex items-center justify-center flex-shrink-0`}>
          <Icon className={`w-4 h-4 ${cfg.color}`} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${SEVERITY_CLASSES[issue.severity] || SEVERITY_CLASSES.low}`}>
              {issue.severity}
            </span>
            <span className={`text-xs font-mono ${cfg.color}`}>{cfg.label}</span>
            {issue.line_start && (
              <span className="text-xs text-gray-500 font-mono">
                line {issue.line_start}
                {issue.line_end && issue.line_end !== issue.line_start ? `–${issue.line_end}` : ""}
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-white leading-snug">{issue.title}</p>
        </div>

        {/* Status badge */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {isFixed ? (
            <span className="flex items-center gap-1 text-xs text-green-400 font-mono bg-green-500/10 border border-green-500/20 px-2 py-1 rounded-lg">
              <CheckCircle className="w-3 h-3" />
              Fixed
            </span>
          ) : isExplaining ? (
            <span className="flex items-center gap-1 text-xs text-accent font-mono">
              <Loader2 className="w-3 h-3 animate-spin" />
              Explaining...
            </span>
          ) : planSummary ? (
            <span className="flex items-center gap-1 text-xs text-cyan-400/60 font-mono">
              <Sparkles className="w-3 h-3" />
              Planned
            </span>
          ) : null}
          <div className="text-gray-600 ml-1">
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </div>
      </div>

      {/* Expanded content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-white/5"
          >
            <div className="p-4 space-y-3">
              {/* Original description */}
              <p className="text-sm text-gray-400 leading-relaxed">{issue.description}</p>

              {/* Fix plan summary */}
              {planSummary && (
                <div className="flex gap-2 items-start bg-cyan-500/5 border border-cyan-500/15 rounded-lg p-3">
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs text-cyan-400 font-mono mb-0.5">Fix plan</p>
                    <p className="text-sm text-gray-300">{planSummary}</p>
                  </div>
                </div>
              )}

              {/* Streaming explanation */}
              {showExplanation && (
                <div className="bg-black/30 border border-white/5 rounded-lg p-3">
                  <div className="flex items-center gap-1.5 mb-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                    <p className="text-xs text-accent font-mono">Fix explanation</p>
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                    {liveText}
                    {isExplaining && !explanation && (
                      <span className="inline-block w-1.5 h-4 bg-accent/70 ml-0.5 animate-pulse rounded-sm" />
                    )}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
