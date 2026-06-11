"use client";
import { useMemo } from "react";

interface DiffLine {
  type: "added" | "removed" | "unchanged" | "header";
  content: string;
  lineNumOld: number | null;
  lineNumNew: number | null;
}

function parseDiff(diffStr: string): DiffLine[] {
  const lines = diffStr.split("\n");
  const result: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const raw of lines) {
    if (raw.startsWith("---") || raw.startsWith("+++")) {
      result.push({ type: "header", content: raw, lineNumOld: null, lineNumNew: null });
    } else if (raw.startsWith("@@")) {
      // Parse hunk header: @@ -a,b +c,d @@
      const match = raw.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (match) {
        oldLine = parseInt(match[1]) - 1;
        newLine = parseInt(match[2]) - 1;
      }
      result.push({ type: "header", content: raw, lineNumOld: null, lineNumNew: null });
    } else if (raw.startsWith("+")) {
      newLine++;
      result.push({ type: "added", content: raw.slice(1), lineNumOld: null, lineNumNew: newLine });
    } else if (raw.startsWith("-")) {
      oldLine++;
      result.push({ type: "removed", content: raw.slice(1), lineNumOld: oldLine, lineNumNew: null });
    } else if (raw.startsWith(" ")) {
      oldLine++;
      newLine++;
      result.push({ type: "unchanged", content: raw.slice(1), lineNumOld: oldLine, lineNumNew: newLine });
    }
  }

  return result;
}

interface Props {
  diff: string;
  className?: string;
}

export default function DiffViewer({ diff, className = "" }: Props) {
  const lines = useMemo(() => parseDiff(diff), [diff]);

  if (!diff) return null;

  return (
    <div className={`font-mono text-xs overflow-x-auto rounded-xl border border-border bg-[#090b10] ${className}`}>
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, i) => {
            if (line.type === "header") {
              return (
                <tr key={i} className="bg-[#1a1f2e]">
                  <td colSpan={3} className="px-4 py-1 text-gray-500 select-none">{line.content}</td>
                </tr>
              );
            }

            const rowBg =
              line.type === "added"
                ? "bg-[#0d2016]"
                : line.type === "removed"
                ? "bg-[#1e0d0d]"
                : "";

            const textColor =
              line.type === "added"
                ? "text-green-300"
                : line.type === "removed"
                ? "text-red-300"
                : "text-gray-400";

            const prefix =
              line.type === "added" ? "+" : line.type === "removed" ? "−" : " ";

            const prefixColor =
              line.type === "added"
                ? "text-green-500"
                : line.type === "removed"
                ? "text-red-500"
                : "text-gray-700";

            return (
              <tr key={i} className={`${rowBg} group hover:brightness-110 transition-all`}>
                {/* Old line number */}
                <td className="w-10 px-2 py-0.5 text-right text-gray-700 select-none border-r border-border/40 group-hover:text-gray-500">
                  {line.lineNumOld ?? ""}
                </td>
                {/* New line number */}
                <td className="w-10 px-2 py-0.5 text-right text-gray-700 select-none border-r border-border/40 group-hover:text-gray-500">
                  {line.lineNumNew ?? ""}
                </td>
                {/* Content */}
                <td className={`px-3 py-0.5 whitespace-pre ${textColor}`}>
                  <span className={`${prefixColor} select-none mr-2`}>{prefix}</span>
                  {line.content}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
