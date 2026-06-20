"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useScroll,
  useSpring,
  useTransform,
} from "framer-motion";
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
  hidden: { opacity: 0, y: 28 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.09,
    },
  },
};

function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: 0, y: 0 });
  const particlesRef = useRef<
    Array<{ x: number; y: number; vx: number; vy: number; size: number; opacity: number; pulse: number }>
  >([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      const count = Math.min(70, Math.max(32, Math.floor(window.innerWidth / 24)));
      particlesRef.current = Array.from({ length: count }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        size: Math.random() * 1.8 + 0.6,
        opacity: Math.random() * 0.35 + 0.18,
        pulse: Math.random() * Math.PI * 2,
      }));
    };

    const handleMouse = (event: MouseEvent) => {
      mouseRef.current = { x: event.clientX, y: event.clientY };
    };

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("mousemove", handleMouse);

    let frame = 0;
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const particles = particlesRef.current;
      const mouse = mouseRef.current;

      particles.forEach((particle, index) => {
        particle.pulse += 0.018;

        const dx = mouse.x - particle.x;
        const dy = mouse.y - particle.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < 180 && distance > 0) {
          particle.vx += (dx / distance) * 0.012;
          particle.vy += (dy / distance) * 0.012;
        }

        particle.x += particle.vx;
        particle.y += particle.vy;
        particle.vx *= 0.992;
        particle.vy *= 0.992;

        if (particle.x < 0) particle.x = canvas.width;
        if (particle.x > canvas.width) particle.x = 0;
        if (particle.y < 0) particle.y = canvas.height;
        if (particle.y > canvas.height) particle.y = 0;

        const opacity = particle.opacity * (0.75 + 0.25 * Math.sin(particle.pulse));
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0, 229, 255, ${opacity})`;
        ctx.fill();

        for (let nextIndex = index + 1; nextIndex < particles.length; nextIndex++) {
          const other = particles[nextIndex];
          const lineX = particle.x - other.x;
          const lineY = particle.y - other.y;
          const lineDistance = Math.sqrt(lineX * lineX + lineY * lineY);
          if (lineDistance < 115) {
            ctx.beginPath();
            ctx.moveTo(particle.x, particle.y);
            ctx.lineTo(other.x, other.y);
            ctx.strokeStyle = `rgba(0, 229, 255, ${0.09 * (1 - lineDistance / 115)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      });

      frame = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", handleMouse);
    };
  }, []);

  return <canvas ref={canvasRef} className="fixed inset-0 z-0 pointer-events-none opacity-60" />;
}

function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 120, damping: 28 });

  return <motion.div className="fixed left-0 right-0 top-0 z-50 h-1 origin-left bg-accent" style={{ scaleX }} />;
}

function SpotlightCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const background = useMotionTemplate`radial-gradient(520px circle at ${mouseX}px ${mouseY}px, rgba(0,229,255,0.14), transparent 42%)`;

  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const rect = event.currentTarget.getBoundingClientRect();
      mouseX.set(event.clientX - rect.left);
      mouseY.set(event.clientY - rect.top);
    },
    [mouseX, mouseY]
  );

  return (
    <motion.div
      onMouseMove={handleMouseMove}
      whileHover={{ y: -6, borderColor: "rgba(0,229,255,0.34)" }}
      transition={{ duration: 0.25 }}
      className={`relative overflow-hidden rounded-2xl border border-border bg-surface/75 backdrop-blur-xl ${className}`}
    >
      <motion.div className="absolute inset-0 pointer-events-none" style={{ background }} />
      <div className="relative z-10">{children}</div>
    </motion.div>
  );
}

function TypingCode() {
  const [lines, setLines] = useState<string[]>([]);
  const fullLines = [
    { text: "const review = await agent.review(code);", color: "text-accent" },
    { text: "providers: ['groq', 'gemini', 'ollama']", color: "text-green-400" },
    { text: "mode: lines > 500 ? 'chunked' : 'fast'", color: "text-yellow-400" },
    { text: "issues.stream();", color: "text-blue-400" },
    { text: "fixes.generateSecurePatch();", color: "text-purple-400" },
  ];

  useEffect(() => {
    let currentLine = 0;
    let currentChar = 0;
    const interval = window.setInterval(() => {
      if (currentLine >= fullLines.length) {
        window.clearInterval(interval);
        return;
      }

      const activeLine = fullLines[currentLine];
      if (currentChar <= activeLine.text.length) {
        setLines((previous) => {
          const next = [...previous];
          next[currentLine] = activeLine.text.slice(0, currentChar);
          return next;
        });
        currentChar += 1;
      } else {
        currentLine += 1;
        currentChar = 0;
      }
    }, 34);

    return () => window.clearInterval(interval);
  }, []);

  return (
    <div className="font-mono text-sm leading-7">
      {fullLines.map((line, index) => (
        <div key={line.text} className="flex min-h-7">
          <span className="mr-4 w-6 select-none text-right text-gray-600">{index + 1}</span>
          <span className={line.color}>{lines[index] || ""}</span>
        </div>
      ))}
    </div>
  );
}

function Logo() {
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 glow-accent">
      <Code2 className="h-5 w-5 text-accent" />
    </div>
  );
}

function SectionHeader({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-90px" }}
      transition={{ duration: 0.55 }}
      className="max-w-3xl"
    >
      <p className="mb-3 font-mono text-xs uppercase tracking-[0.25em] text-accent">{eyebrow}</p>
      <h2 className="text-3xl font-bold leading-tight text-white md:text-5xl">{title}</h2>
      <p className="mt-4 text-base leading-7 text-gray-400 md:text-lg">{text}</p>
    </motion.div>
  );
}

export default function Home() {
  const router = useRouter();
  const { token, hydrate } = useAuthStore();
  const { scrollYProgress } = useScroll();
  const heroY = useTransform(scrollYProgress, [0, 0.4], [0, 130]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.28], [1, 0]);

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
      items: ["FastAPI", "Python", "Streaming APIs", "WebSockets"],
    },
    {
      title: "AI Layer",
      icon: Bot,
      items: ["Groq", "Gemini", "Ollama", "Provider Fallback"],
    },
    {
      title: "Data & Deploy",
      icon: Database,
      items: ["PostgreSQL", "Redis", "Railway", "Vercel"],
    },
  ];

  const builderCards = [
    { icon: UserRound, label: "Built by Om Pathak", value: "Designed, engineered, deployed, and tuned as a full-stack AI project." },
    { icon: Terminal, label: "Developer-focused", value: "Made for the exact workflow devs care about: review code, understand issues, generate fixes." },
    { icon: Cloud, label: "Demo-ready", value: "Runs live with cloud APIs, while still supporting local Ollama for developer use." },
  ];

  const productFlow = [
    { icon: Braces, title: "Review", text: "Paste code or submit a PR and stream issues as the agent analyzes it." },
    { icon: ShieldCheck, title: "Detect", text: "Find bugs, security risks, performance problems, and unsafe patterns." },
    { icon: Zap, title: "Fix", text: "Generate corrected code with explanations, diffs, and downloadable output." },
    { icon: Layers3, title: "Scale", text: "Use fast review for small files and chunked mode for larger code samples." },
  ];

  return (
    <div className="min-h-screen overflow-x-hidden bg-bg text-white selection:bg-accent/30 selection:text-white">
      <ScrollProgress />
      <ParticleField />

      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(0,229,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,229,255,0.05)_1px,transparent_1px)] bg-[size:48px_48px]" />
        <motion.div
          className="absolute left-1/2 top-0 h-96 w-96 -translate-x-1/2 rounded-full bg-accent/10 blur-3xl"
          animate={{ scale: [1, 1.2, 1], opacity: [0.35, 0.65, 0.35] }}
          transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <nav className="sticky top-0 z-40 flex items-center justify-between border-b border-border bg-bg/70 px-5 py-4 backdrop-blur-xl md:px-8">
        <button onClick={() => router.push("/")} className="flex items-center gap-3">
          <Logo />
          <span className="text-sm font-semibold md:text-base">CodeReview Agent</span>
        </button>
        <div className="flex items-center gap-3">
          <a
            href="https://github.com/ompathakbaap/codereview"
            target="_blank"
            className="hidden items-center gap-2 text-sm text-gray-400 transition-colors hover:text-white sm:flex"
          >
            <GitBranch className="h-4 w-4" />
            GitHub
          </a>
          <button
            onClick={() => router.push(token ? "/dashboard" : "/auth")}
            className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-bg transition-all hover:bg-accent-dim glow-accent"
          >
            {token ? "Dashboard" : "Try Demo"}
          </button>
        </div>
      </nav>

      <main className="relative z-10">
        <section className="flex min-h-[calc(100vh-73px)] items-center px-5 py-14 md:px-8 md:py-20">
          <motion.div style={{ y: heroY, opacity: heroOpacity }} className="mx-auto grid w-full max-w-7xl items-center gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
            <motion.div variants={stagger} initial="hidden" animate="show">
              <motion.div variants={fadeUp} className="mb-7 inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1.5 font-mono text-xs text-accent">
                <Sparkles className="h-3.5 w-3.5" />
                Built by Om Pathak
              </motion.div>
              <motion.h1 variants={fadeUp} className="text-5xl font-bold leading-[0.95] tracking-tight md:text-7xl">
                AI code reviews that <span className="text-accent">fix the code</span>.
              </motion.h1>
              <motion.p variants={fadeUp} className="mt-7 max-w-2xl text-lg leading-8 text-gray-400 md:text-xl">
                A full-stack AI reviewer that detects issues, explains them, and generates validated fixes with cloud APIs, local Ollama support, and large-file chunking.
              </motion.p>
              <motion.div variants={fadeUp} className="mt-9 flex flex-wrap gap-3">
                <motion.button
                  whileHover={{ y: -2, scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => router.push(token ? "/dashboard" : "/auth")}
                  className="flex items-center gap-2 rounded-xl bg-accent px-6 py-3 font-bold text-bg transition-all hover:bg-accent-dim glow-accent"
                >
                  Open Project <ArrowRight className="h-4 w-4" />
                </motion.button>
                <motion.a
                  whileHover={{ y: -2 }}
                  href="#what"
                  className="flex items-center gap-2 rounded-xl border border-border px-6 py-3 text-gray-300 transition-all hover:border-accent/40 hover:text-white"
                >
                  See What It Does
                </motion.a>
              </motion.div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 32, rotateX: 8 }}
              animate={{ opacity: 1, y: 0, rotateX: 0 }}
              transition={{ duration: 0.7, ease: "easeOut" }}
              className="relative overflow-hidden rounded-2xl border border-border bg-surface/90 shadow-2xl"
            >
              <div className="flex items-center gap-2 border-b border-border bg-bg/60 px-4 py-3">
                <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-yellow-400/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-green-400/80" />
                <span className="ml-3 font-mono text-xs text-gray-500">agent.review.ts</span>
              </div>
              <div className="p-5">
                <TypingCode />
              </div>
              <motion.div
                className="absolute inset-x-0 top-12 h-20 bg-accent/10 blur-xl"
                animate={{ y: [0, 190, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              />
            </motion.div>
          </motion.div>
        </section>

        <section id="creator" className="border-t border-border px-5 py-20 md:px-8">
          <div className="mx-auto grid max-w-7xl items-center gap-10 lg:grid-cols-[0.8fr_1.2fr]">
            <SectionHeader
              eyebrow="01 / Who made it"
              title="Built by Om Pathak"
              text="This is a real developer tool, not a static AI wrapper: live review streams, auth, dashboard workflows, API failover, local model mode, and Fix-It output that developers can actually inspect."
            />
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              className="grid gap-4 sm:grid-cols-3"
            >
              {builderCards.map((item) => {
                const Icon = item.icon;
                return (
                  <motion.div key={item.label} variants={fadeUp}>
                    <SpotlightCard className="h-full p-5">
                      <Icon className="mb-5 h-6 w-6 text-accent" />
                      <p className="font-semibold text-white">{item.label}</p>
                      <p className="mt-2 text-sm leading-6 text-gray-500">{item.value}</p>
                    </SpotlightCard>
                  </motion.div>
                );
              })}
            </motion.div>
          </div>
        </section>

        <section id="stack" className="border-t border-border bg-surface/20 px-5 py-20 md:px-8">
          <div className="mx-auto max-w-7xl">
            <SectionHeader
              eyebrow="02 / Tech stack"
              title="A modern AI-first stack"
              text="The app combines a polished Next.js interface with a FastAPI backend, streaming transport, persistent data, deployment on Vercel and Railway, and multiple AI execution paths for API and local use."
            />
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4"
            >
              {techGroups.map((group) => {
                const Icon = group.icon;
                return (
                  <motion.div key={group.title} variants={fadeUp}>
                    <SpotlightCard className="h-full p-5">
                      <motion.div
                        className="absolute inset-x-0 top-0 h-px bg-accent"
                        animate={{ x: ["-100%", "100%"] }}
                        transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
                      />
                      <Icon className="mb-5 h-6 w-6 text-accent" />
                      <h3 className="mb-4 font-bold text-white">{group.title}</h3>
                      <div className="flex flex-wrap gap-2">
                        {group.items.map((tech) => (
                          <span key={tech} className="rounded-lg border border-border bg-bg/70 px-2.5 py-1 font-mono text-xs text-gray-300">
                            {tech}
                          </span>
                        ))}
                      </div>
                    </SpotlightCard>
                  </motion.div>
                );
              })}
            </motion.div>
          </div>
        </section>

        <section id="what" className="border-t border-border px-5 py-20 md:px-8">
          <div className="mx-auto max-w-7xl">
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
              className="mt-10 grid gap-4 md:grid-cols-4"
            >
              {productFlow.map((step, index) => {
                const Icon = step.icon;
                return (
                  <motion.div key={step.title} variants={fadeUp}>
                    <SpotlightCard className="h-full p-5">
                      <motion.div
                        className="absolute -right-8 -top-8 h-24 w-24 rounded-full border border-accent/20"
                        animate={{ rotate: 360 }}
                        transition={{ duration: 12 + index * 2, repeat: Infinity, ease: "linear" }}
                      />
                      <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl border border-accent/20 bg-accent/10 text-accent">
                        <Icon className="h-5 w-5" />
                      </div>
                      <p className="mb-2 font-mono text-xs text-accent">0{index + 1}</p>
                      <h3 className="font-bold text-white">{step.title}</h3>
                      <p className="mt-3 text-sm leading-6 text-gray-500">{step.text}</p>
                    </SpotlightCard>
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
