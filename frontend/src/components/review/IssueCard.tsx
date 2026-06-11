"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bug, Shield, Palette, Zap, ChevronDown, ChevronUp, Lightbulb } from "lucide-react";
import { Issue } from "@/types";

const CATEGORY_CONFIG = {
  bug: { icon: Bug, label: "Bug", color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/20" },
  security: { icon: Shield, label: "Security", color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/20" },
  style: { icon: Palette, label: "Style", color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20" },
  performance: { icon: Zap, label: "Performance", color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/20" },
};

const SEVERITY_CLASSES = {
  critical: "badge-critical",
  high: "badge-high",
  medium: "badge-medium",
  low: "badge-low",
  info: "badge-info",
};

export default function IssueCard({ issue, onCommentClick }: { issue: Issue; onCommentClick?: (issue: Issue) => void }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = CATEGORY_CONFIG[issue.category] || CATEGORY_CONFIG.bug;
  const Icon = cfg.icon;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className={`border ${cfg.border} ${cfg.bg} rounded-xl overflow-hidden`}
    >
      {/* Header */}
      <div className="p-4 flex items-start gap-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className={`w-8 h-8 rounded-lg ${cfg.bg} border ${cfg.border} flex items-center justify-center flex-shrink-0`}>
          <Icon className={`w-4 h-4 ${cfg.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${SEVERITY_CLASSES[issue.severity]}`}>
              {issue.severity}
            </span>
            <span className={`text-xs font-mono ${cfg.color}`}>{cfg.label}</span>
            {issue.line_start && (
              <span className="text-xs text-gray-500 font-mono">
                line {issue.line_start}{issue.line_end && issue.line_end !== issue.line_start ? `–${issue.line_end}` : ""}
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-white">{issue.title}</p>
        </div>
        <div className="text-gray-500 flex-shrink-0">
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </div>

      {/* Expanded content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-white/5"
          >
            <div className="p-4 space-y-4">
              <p className="text-sm text-gray-300 leading-relaxed">{issue.description}</p>

              {issue.code_snippet && (
                <div className="bg-black/30 rounded-lg p-3 font-mono text-xs text-gray-300 overflow-x-auto border border-white/5">
                  <pre>{issue.code_snippet}</pre>
                </div>
              )}

              {issue.suggestion && (
                <div className="flex gap-2 bg-black/20 rounded-lg p-3 border border-white/5">
                  <Lightbulb className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-gray-300 leading-relaxed">{issue.suggestion}</p>
                </div>
              )}

              {onCommentClick && (
                <button onClick={() => onCommentClick(issue)}
                  className="text-xs text-gray-500 hover:text-accent transition-colors font-mono">
                  + add comment
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
