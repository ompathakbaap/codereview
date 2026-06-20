"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useAuthStore } from "@/store";
import {
  ArrowRight,
  Bot,
  Braces,
  CheckCircle2,
  Cloud,
  Code2,
  Database,
  GitBranch,
  Laptop,
  Layers3,
  Server,
  ShieldCheck,
  Sparkles,
  Terminal,
  UserRound,
  Zap,
} from "lucide-react";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.08,
    },
  },
};

const Logo = () => (
  <div className="w-10 h-10 rounded-xl border border-accent/30 bg-accent/10 flex items-center justify-center glow-accent">
    <Code2 className="w-5 h-5 text-accent" />
  </div>
);

const AnimatedCodePanel = () => {
  const lines = [
    "review.start(repo)",
    "scan: security, bugs, perf",
    "fallback: groq -> gemini",
    "local: ollama enabled",
    "fix-it: diff generated",
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 28, rotateX: 8 }}
      animate={{ opacity: 1, y: 0, rotateX: 0 }}
      transition={{ duration: 0.7, ease: "easeOut" }}
      className="relative border border-border bg-surface/90 rounded-2xl overflow-hidden shadow-2xl"
    >
      <div className="flex items-center gap-2 border-b border-border px-4 py-3 bg-bg/60">
        <span className="w-2.5 h-2.5 rounded-full bg-red-400/80" />
        <span className="w-2.5 h-2.5 rounded-full bg-yellow-400/80" />
        <span className="w-2.5 h-2.5 rounded-full bg-green-400/80" />
        <span className="ml-3 text-xs text-gray-500 font-mono">agent.review.ts</span>
      </div>
      <div className="p-5 font-mono text-sm">
        {lines.map((line, index) => (
          <motion.div
            key={line}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 + index * 0.15 }}
            className="flex items-center gap-3 py-2"
          >
            <span className="text-gray-600 w-5 text-right">{index + 1}</span>
            <span className="text-gray-300">{line}</span>
            {index > 1 && <CheckCircle2 className="w-3.5 h-3.5 text-accent ml-auto" />}
          </motion.div>
        ))}
      </div>
      <motion.div
        className="absolute inset-x-0 top-12 h-16 bg-accent/10 blur-xl"
        animate={{ y: [0, 190, 0] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />
    </motion.div>
  );
};

const SectionHeader = ({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) => (
  <motion.div
    variants={fadeUp}
    initial="hidden"
    whileInView="show"
    viewport={{ once: true, margin: "-80px" }}
    transition={{ duration: 0.55 }}
    className="max-w-3xl"
  >
    <p className="text-xs uppercase tracking-[0.25em] text-accent font-mono mb-3">{eyebrow}</p>
    <h2 className="text-3xl md:text-5xl font-bold text-white leading-tight">{title}</h2>
    <p className="text-gray-400 mt-4 text-base md:text-lg leading-7">{text}</p>
  </motion.div>
);

export default function Home() {
  const router = useRouter();
  const { token, hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const techGroups = [
    {
      title: "Frontend",
      icon: Laptop,
      items: ["Next.js", "React", "Tailwind CSS", "Framer Motion"],
    },
    {
      title: "Backend",
      icon: Server,
      items: ["FastAPI", "Python", "SSE Streaming", "WebSockets"],
    },
    {
      title: "AI Layer",
      icon: Bot,
      items: ["Groq", "Gemini", "Ollama", "LangGraph"],
    },
    {
      title: "Data & Deploy",
      icon: Database,
      items: ["PostgreSQL", "Redis", "Railway", "Vercel"],
    },
  ];

  const productFlow = [
    { icon: Braces, title: "Review", text: "Paste code or submit a PR and stream issue detection live." },
    { icon: ShieldCheck, title: "Detect", text: "Find bugs, security risks, performance issues, and unsafe patterns." },
    { icon: Zap, title: "Fix", text: "Generate corrected code with diffs, explanations, and downloads." },
    { icon: Layers3, title: "Scale", text: "Use fast mode for small files and chunked mode for larger files." },
  ];

  return (
    <div className="min-h-screen bg-bg text-white overflow-hidden">
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(0,229,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,229,255,0.05)_1px,transparent_1px)] bg-[size:48px_48px]" />
        <motion.div
          className="absolute left-1/2 top-0 h-96 w-96 -translate-x-1/2 rounded-full bg-accent/10 blur-3xl"
          animate={{ scale: [1, 1.18, 1], opacity: [0.4, 0.65, 0.4] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <nav className="relative z-10 border-b border-border px-5 md:px-8 py-4 flex items-center justify-between bg-bg/70 backdrop-blur-xl sticky top-0">
        <button onClick={() => router.push("/")} className="flex items-center gap-3">
          <Logo />
          <span className="font-semibold text-sm md:text-base">CodeReview Agent</span>
        </button>
        <div className="flex items-center gap-3">
          <a
            href="https://github.com/ompathakbaap/codereview"
            target="_blank"
            className="hidden sm:flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <GitBranch className="w-4 h-4" />
            GitHub
          </a>
          <button
            onClick={() => router.push(token ? "/dashboard" : "/auth")}
            className="px-4 py-2 rounded-xl bg-accent text-bg text-sm font-semibold hover:bg-accent-dim transition-all glow-accent"
          >
            {token ? "Dashboard" : "Try Demo"}
          </button>
        </div>
      </nav>

      <main className="relative z-10">
        <section className="min-h-[calc(100vh-73px)] px-5 md:px-8 py-14 md:py-20 flex items-center">
          <div className="max-w-7xl mx-auto w-full grid lg:grid-cols-[1.05fr_0.95fr] gap-10 lg:gap-16 items-center">
            <motion.div variants={stagger} initial="hidden" animate="show">
              <motion.div
                variants={fadeUp}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent/20 bg-accent/10 text-accent text-xs font-mono mb-7"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Built by Om Pathak
              </motion.div>
              <motion.h1 variants={fadeUp} className="text-5xl md:text-7xl font-bold leading-[0.95] tracking-tight">
                AI code reviews that{" "}
                <span className="text-accent">fix the code</span>.
              </motion.h1>
              <motion.p variants={fadeUp} className="text-gray-400 text-lg md:text-xl leading-8 mt-7 max-w-2xl">
                A full-stack AI reviewer that detects issues, explains them, and generates validated fixes with
                cloud APIs, local Ollama support, and large-file chunking.
              </motion.p>
              <motion.div variants={fadeUp} className="flex flex-wrap gap-3 mt-9">
                <button
                  onClick={() => router.push(token ? "/dashboard" : "/auth")}
                  className="flex items-center gap-2 px-6 py-3 rounded-xl bg-accent text-bg font-bold hover:bg-accent-dim transition-all glow-accent"
                >
                  Open Project <ArrowRight className="w-4 h-4" />
                </button>
                <a
                  href="#what"
                  className="flex items-center gap-2 px-6 py-3 rounded-xl border border-border text-gray-300 hover:text-white hover:border-accent/40 transition-all"
                >
                  See What It Does
                </a>
              </motion.div>
            </motion.div>
            <AnimatedCodePanel />
          </div>
        </section>

        <section id="creator" className="px-5 md:px-8 py-20 border-t border-border">
          <div className="max-w-7xl mx-auto grid lg:grid-cols-[0.8fr_1.2fr] gap-10 items-center">
            <SectionHeader
              eyebrow="01 / Who made it"
              title="Built by Om Pathak"
              text="I built this as a real developer tool, not a static AI wrapper: real-time review streams, auth, dashboard analytics, API failover, local model mode, and Fix-It workflows that produce downloadable code."
            />
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              className="grid sm:grid-cols-3 gap-4"
            >
              {[
                { icon: UserRound, label: "Full-Stack Developer", value: "Frontend + backend ownership" },
                { icon: Terminal, label: "AI Tooling", value: "Review, fix, validate loops" },
                { icon: Cloud, label: "Deployment", value: "Vercel + Railway live app" },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <motion.div
                    key={item.label}
                    variants={fadeUp}
                    whileHover={{ y: -6, borderColor: "rgba(0,229,255,0.45)" }}
                    className="bg-surface/80 border border-border rounded-2xl p-5"
                  >
                    <Icon className="w-6 h-6 text-accent mb-5" />
                    <p className="font-semibold text-white">{item.label}</p>
                    <p className="text-sm text-gray-500 mt-2 leading-6">{item.value}</p>
                  </motion.div>
                );
              })}
            </motion.div>
          </div>
        </section>

        <section id="stack" className="px-5 md:px-8 py-20 border-t border-border bg-surface/20">
          <div className="max-w-7xl mx-auto">
            <SectionHeader
              eyebrow="02 / Tech stack"
              title="A modern AI-first stack"
              text="The project combines a polished Next.js interface with a FastAPI backend, streaming transport, persistent data, and multiple AI execution modes for cloud and local development."
            />
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              className="grid md:grid-cols-2 lg:grid-cols-4 gap-4 mt-10"
            >
              {techGroups.map((group) => {
                const Icon = group.icon;
                return (
                  <motion.div
                    key={group.title}
                    variants={fadeUp}
                    whileHover={{ y: -8 }}
                    className="relative overflow-hidden bg-bg/80 border border-border rounded-2xl p-5"
                  >
                    <motion.div
                      className="absolute inset-x-0 top-0 h-px bg-accent"
                      animate={{ x: ["-100%", "100%"] }}
                      transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
                    />
                    <Icon className="w-6 h-6 text-accent mb-5" />
                    <h3 className="font-bold text-white mb-4">{group.title}</h3>
                    <div className="flex flex-wrap gap-2">
                      {group.items.map((tech) => (
                        <span key={tech} className="px-2.5 py-1 rounded-lg bg-surface border border-border text-xs text-gray-300 font-mono">
                          {tech}
                        </span>
                      ))}
                    </div>
                  </motion.div>
                );
              })}
            </motion.div>
          </div>
        </section>

        <section id="what" className="px-5 md:px-8 py-20 border-t border-border">
          <div className="max-w-7xl mx-auto">
            <SectionHeader
              eyebrow="03 / What it does"
              title="Reviews, fixes, and explains code"
              text="Users paste code or review a PR, watch issues stream in live, then run Fix-It to generate corrected code with diffs, explanations, and downloadable output."
            />
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              className="grid md:grid-cols-4 gap-4 mt-10"
            >
              {productFlow.map((step, index) => {
                const Icon = step.icon;
                return (
                  <motion.div
                    key={step.title}
                    variants={fadeUp}
                    className="relative bg-surface/80 border border-border rounded-2xl p-5 overflow-hidden"
                  >
                    <motion.div
                      className="absolute -right-8 -top-8 w-24 h-24 rounded-full border border-accent/20"
                      animate={{ rotate: 360 }}
                      transition={{ duration: 12 + index * 2, repeat: Infinity, ease: "linear" }}
                    />
                    <div className="w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center text-accent mb-5">
                      <Icon className="w-5 h-5" />
                    </div>
                    <p className="text-xs text-accent font-mono mb-2">0{index + 1}</p>
                    <h3 className="font-bold text-white">{step.title}</h3>
                    <p className="text-sm text-gray-500 leading-6 mt-3">{step.text}</p>
                  </motion.div>
                );
              })}
            </motion.div>
          </div>
        </section>
      </main>
    </div>
  );
}
