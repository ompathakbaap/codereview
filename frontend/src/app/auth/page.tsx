"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Code2, Zap, Lock, User, Mail, ArrowRight } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store";
import toast from "react-hot-toast";

export default function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ email: "", username: "", password: "" });
  const router = useRouter();
  const { setAuth } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const { data } = await api.post(endpoint, form);
      setAuth(data.access_token, data.user);
      toast.success(`Welcome, ${data.user.username}!`);
      router.push("/dashboard");
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background grid */}
      <div className="absolute inset-0 opacity-[0.03]"
        style={{ backgroundImage: "linear-gradient(#00e5ff 1px, transparent 1px), linear-gradient(90deg, #00e5ff 1px, transparent 1px)", backgroundSize: "40px 40px" }} />

      {/* Glow orb */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 bg-accent/5 rounded-full blur-3xl" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md relative"
      >
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/30 flex items-center justify-center">
              <Code2 className="w-5 h-5 text-accent" />
            </div>
            <span className="font-mono font-bold text-xl text-white">CodeReview<span className="text-accent">Agent</span></span>
          </div>
          <p className="text-gray-400 text-sm">AI-powered · Real-time · Collaborative</p>
        </div>

        {/* Card */}
        <div className="bg-surface border border-border rounded-2xl p-8 shadow-2xl">
          {/* Tabs */}
          <div className="flex bg-bg rounded-lg p-1 mb-8">
            {(["login", "register"] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)}
                className={`flex-1 py-2 rounded-md text-sm font-medium transition-all capitalize ${mode === m ? "bg-accent/10 text-accent border border-accent/30" : "text-gray-500 hover:text-gray-300"}`}>
                {m}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <AnimatePresence>
              {mode === "register" && (
                <motion.div key="email"
                  initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
                  <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Email</label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input type="email" required value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                      placeholder="you@example.com"
                      className="w-full bg-bg border border-border rounded-lg py-2.5 pl-10 pr-4 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-colors" />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div>
              <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Username</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input type="text" required value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                  placeholder="johndoe"
                  className="w-full bg-bg border border-border rounded-lg py-2.5 pl-10 pr-4 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-colors" />
              </div>
            </div>

            <div>
              <label className="block text-xs text-gray-400 mb-1.5 font-mono uppercase tracking-wider">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input type="password" required value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  placeholder="••••••••"
                  className="w-full bg-bg border border-border rounded-lg py-2.5 pl-10 pr-4 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-colors" />
              </div>
            </div>

            <button type="submit" disabled={loading}
              className="w-full mt-2 bg-accent/10 hover:bg-accent/20 border border-accent/30 hover:border-accent/60 text-accent font-medium py-3 rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50">
              {loading ? (
                <span className="w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
              ) : (
                <><span>{mode === "login" ? "Sign In" : "Create Account"}</span><ArrowRight className="w-4 h-4" /></>
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-border flex items-center gap-2 text-xs text-gray-500">
            <Zap className="w-3 h-3 text-accent" />
            <span>Powered by LangGraph · Ollama · Redis Pub/Sub</span>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
