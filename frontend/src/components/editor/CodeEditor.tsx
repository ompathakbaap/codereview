"use client";
import CodeMirror from "@uiw/react-codemirror";
import { oneDark } from "@codemirror/theme-one-dark";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { cpp } from "@codemirror/lang-cpp";
import { EditorView, Decoration, DecorationSet } from "@codemirror/view";
import { StateField, StateEffect } from "@codemirror/state";
import { useMemo } from "react";
import { Issue } from "@/types";

const LANG_MAP: Record<string, any> = {
  python: python(),
  javascript: javascript({ jsx: true }),
  typescript: javascript({ jsx: true, typescript: true }),
  java: java(),
  cpp: cpp(),
  csharp: cpp(),
  go: javascript(), // fallback
  rust: javascript(), // fallback
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: "rgba(255,77,109,0.12)",
  high: "rgba(255,107,53,0.12)",
  medium: "rgba(249,199,79,0.08)",
  low: "rgba(124,131,253,0.08)",
  info: "rgba(144,224,239,0.06)",
};

function buildHighlightExtension(issues: Issue[], code: string) {
  const lines = code.split("\n");

  const marks: { from: number; to: number; color: string }[] = [];

  for (const issue of issues) {
    if (!issue.line_start) continue;
    const lineNum = parseInt(issue.line_start) - 1;
    if (lineNum < 0 || lineNum >= lines.length) continue;

    let from = lines.slice(0, lineNum).reduce((acc, l) => acc + l.length + 1, 0);
    const lineEnd = parseInt(issue.line_end || issue.line_start) - 1;
    let to = lines.slice(0, lineEnd + 1).reduce((acc, l) => acc + l.length + 1, 0) - 1;
    to = Math.min(to, code.length);

    if (from < to) {
      marks.push({ from, to, color: SEVERITY_COLORS[issue.severity] || SEVERITY_COLORS.low });
    }
  }

  const highlightMark = (color: string) =>
    Decoration.mark({ attributes: { style: `background: ${color}; border-radius: 3px;` } });

  const highlightField = StateField.define<DecorationSet>({
    create(state) {
      const decos = marks
        .filter(m => m.from < state.doc.length && m.to <= state.doc.length)
        .map(m => highlightMark(m.color).range(m.from, m.to));
      return Decoration.set(decos, true);
    },
    update(value) { return value; },
    provide(f) { return EditorView.decorations.from(f); },
  });

  return highlightField;
}

export default function CodeEditor({ code, language, issues }: { code: string; language: string; issues: Issue[] }) {
  const langExt = LANG_MAP[language] || python();
  const highlightExt = useMemo(() => buildHighlightExtension(issues, code), [issues, code]);

  return (
    <div className="h-full">
      <CodeMirror
        value={code}
        height="100%"
        theme={oneDark}
        editable={false}
        extensions={[langExt, highlightExt, EditorView.lineWrapping]}
        style={{ height: "100%", fontSize: "13px" }}
        basicSetup={{
          lineNumbers: true,
          highlightActiveLineGutter: true,
          foldGutter: true,
          syntaxHighlighting: true,
        }}
      />
    </div>
  );
}
