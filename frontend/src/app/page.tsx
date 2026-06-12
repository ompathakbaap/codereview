"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store";
import { Bug, Shield, Zap, Palette, GitPullRequest, Sparkles, ArrowRight } from "lucide-react";

const Logo = () => (
  <svg width="36" height="36" viewBox="0 0 64 64">
    <text x="10" y="46" fontFamily="Dancing Script, cursive" fontSize="46" fontWeight="700" fill="#FF6B2B">O</text>
    <text x="30" y="38" fontFamily="Dancing Script, cursive" fontSize="22" fontWeight="700" fill="#e8eaf0">m</text>
    <line x1="10" y1="48" x2="54" y2="48" stroke="#FF6B2B" strokeWidth="1.5" opacity="0.5"/>
  </svg>
);

export default function Home() {
  const router = useRouter();
  const { token, hydrate } = useAuthStore();

  useEffect(() => { hydrate(); }, []);

  return (
    <>
      <link href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@700&display=swap" rel="stylesheet" />
      <div className="min-h-screen bg-bg text-white">

        {/* Nav */}
        <nav className="border-b border-border px-6 py-4 flex items-center justify-between sticky top-0 bg-bg/80 backdrop-blur z-10">
          <div className="flex items-center gap-2">
            <Logo />
            <span className="font-semibold text-sm text-white">CodeReview Agent</span>
          </div>
          <div className="flex items-center gap-3">
            {token ? (
              <button onClick={() => router.push("/dashboard")}
                className="px-4 py-2 rounded-xl bg-accent text-bg text-sm font-semibold hover:bg-accent-dim transition-all">
                Dashboard
              </button>
            ) : (
              <>
                <button onClick={() => router.push("/auth")}
                  className="text-sm text-gray-400 hover:text-white transition-colors">
                  Sign in
                </button>
                <button onClick={() => router.push("/auth")}
                  className="px-4 py-2 rounded-xl bg-accent text-bg text-sm font-semibold hover:bg-accent-dim transition-all">
                  Get Started
                </button>
              </>
            )}
          </div>
        </nav>

        {/* Hero */}
        <section className="px-6 py-24 text-center max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent/10 border border-accent/20 text-accent text-xs font-mono mb-8">
            <Sparkles className="w-3 h-3" />
            Powered by LangGraph + Groq (llama-3.3-70b)
          </div>
          <h1 className="text-5xl font-bold mb-6 leading-tight">
            AI Code Reviews,<br />
            <span className="text-accent">In Real Time</span>
          </h1>
          <p className="text-gray-400 text-lg mb-10 max-w-2xl mx-auto">
            Paste your code or link a GitHub PR. Four AI agents run in parallel to catch bugs, security issues, style problems, and performance bottlenecks — all streaming live.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <button onClick={() => router.push("/auth")}
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-accent text-bg font-semibold hover:bg-accent-dim transition-all">
              Try it free <ArrowRight className="w-4 h-4" />
            </button>
            <a href="https://github.com/ompathakbaap/codereview" target="_blank"
              className="flex items-center gap-2 px-6 py-3 rounded-xl border border-border text-gray-300 hover:text-white hover:border-gray-500 transition-all text-sm">
              View on GitHub
            </a>
          </div>
        </section>

        {/* Features */}
        <section className="px-6 py-16 max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-center mb-12">Everything you need for better code</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { icon: <Bug className="w-5 h-5" />, title: "Bug Detection", desc: "Catches logic errors, null pointer issues, and edge cases before they hit production." },
              { icon: <Shield className="w-5 h-5" />, title: "Security Analysis", desc: "Finds SQL injection, XSS, hardcoded secrets, and other vulnerabilities instantly." },
              { icon: <Zap className="w-5 h-5" />, title: "Performance Check", desc: "Identifies O(n²) loops, memory leaks, and inefficient patterns in your code." },
              { icon: <Palette className="w-5 h-5" />, title: "Style Review", desc: "Enforces clean code principles, naming conventions, and best practices." },
              { icon: <GitPullRequest className="w-5 h-5" />, title: "GitHub PR Support", desc: "Paste a GitHub PR URL and review the entire diff automatically." },
              { icon: <Sparkles className="w-5 h-5" />, title: "Fix-It Mode", desc: "After finding issues, the AI generates a corrected version with explanations." },
            ].map((f, i) => (
              <div key={i} className="bg-surface border border-border rounded-xl p-5 hover:border-accent/30 transition-all">
                <div className="w-9 h-9 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center text-accent mb-3">
                  {f.icon}
                </div>
                <h3 className="font-semibold mb-1.5 text-white">{f.title}</h3>
                <p className="text-sm text-gray-400">{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Tech Stack */}
        <section className="px-6 py-16 max-w-3xl mx-auto text-center">
          <h2 className="text-2xl font-bold mb-4">Built with modern tech</h2>
          <p className="text-gray-400 mb-8">A production-grade stack — not a toy project.</p>
          <div className="flex flex-wrap justify-center gap-3">
            {["LangGraph", "Groq", "FastAPI", "Next.js 15", "PostgreSQL", "Redis", "WebSockets", "SSE Streaming"].map(t => (
              <span key={t} className="px-3 py-1.5 rounded-lg bg-surface border border-border text-sm text-gray-300 font-mono">{t}</span>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="px-6 py-24 text-center border-t border-border">
          <h2 className="text-3xl font-bold mb-4">Ready to review your code?</h2>
          <p className="text-gray-400 mb-8">Free to use. No credit card required.</p>
          <button onClick={() => router.push("/auth")}
            className="flex items-center gap-2 px-8 py-4 rounded-xl bg-accent text-bg font-semibold hover:bg-accent-dim transition-all mx-auto text-lg">
            Get Started Free <ArrowRight className="w-5 h-5" />
          </button>
        </section>

        {/* Footer */}
        <footer className="border-t border-border px-6 py-8 text-center text-sm text-gray-600">
          Built by Om Pathak ·{" "}
          <a href="https://github.com/ompathakbaap/codereview" target="_blank"
            className="hover:text-gray-400 transition-colors">
            GitHub
          </a>
        </footer>
      </div>
    </>
  );
}