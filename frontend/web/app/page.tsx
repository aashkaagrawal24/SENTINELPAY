"use client";

import { motion } from "framer-motion";
import { 
  ArrowRight, Shield, Store, Bot, Terminal, Zap, Eye, 
  CreditCard, BarChart3, Scale, Sparkles, Lock, CheckCircle2,
  Cpu, Activity, Layers, ArrowUpRight, ShieldCheck
} from "lucide-react";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function Home() {
  const [session, setSession] = useState<any>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
  }, []);

  const isLoggedIn = mounted && (session || (typeof window !== "undefined" && localStorage.getItem("demo_session")));

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08, delayChildren: 0.15 } }
  };
  const itemVariants = {
    hidden: { y: 16, opacity: 0 },
    visible: { y: 0, opacity: 1, transition: { duration: 0.4, ease: "easeOut" } }
  };

  return (
    <main className="min-h-screen bg-background text-foreground overflow-hidden selection:bg-primary/20">
      {/* Background ambient lighting */}
      <div className="absolute top-0 inset-x-0 h-[650px] bg-[radial-gradient(ellipse_80%_60%_at_50%_-20%,rgba(120,119,198,0.15),rgba(255,255,255,0))] -z-10 pointer-events-none" />
      <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-blue-500/5 blur-[120px] rounded-full -z-10 pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-[500px] h-[500px] bg-emerald-500/5 blur-[120px] rounded-full -z-10 pointer-events-none" />

      {/* Navigation */}
      <nav className="sticky top-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto flex h-16 items-center justify-between px-4 md:px-8">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-primary/10 rounded-xl border border-primary/20">
              <Shield className="h-5 w-5 text-primary" />
            </div>
            <span className="font-bold tracking-tight text-lg">SENTINELPAY</span>
            <Badge variant="outline" className="ml-1 text-[10px] border-primary/30 text-primary font-mono">
              v4.2 PROD
            </Badge>
          </div>

          <div className="flex items-center gap-3">
            <a 
              href="/buyer"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors font-medium hidden sm:inline"
            >
              Marketplace
            </a>
            <a 
              href="/merchant/dashboard"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors font-medium hidden sm:inline"
            >
              Merchant Console
            </a>

            {isLoggedIn ? (
              <Button size="sm" asChild className="gap-2 text-xs h-8 bg-primary hover:bg-primary/90">
                <a href="/app">Launch App <ArrowRight className="w-3.5 h-3.5" /></a>
              </Button>
            ) : (
              <Button size="sm" asChild className="gap-2 text-xs h-8 bg-primary hover:bg-primary/90">
                <a href="/login">Sign In <ArrowRight className="w-3.5 h-3.5" /></a>
              </Button>
            )}
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-20 pb-16 px-4">
        <div className="max-w-5xl mx-auto text-center space-y-8">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-semibold"
          >
            <Sparkles className="w-3.5 h-3.5 text-primary" />
            <span>Razorpay Buildathon · Track 01 — AI Growth &amp; Agentic Commerce</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.08 }}
            className="text-4xl sm:text-6xl md:text-7xl font-bold tracking-tight text-foreground leading-[1.08]"
          >
            Make your commerce{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-teal-300 to-emerald-400">
              transactable to AI.
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.16 }}
            className="text-base sm:text-lg md:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed"
          >
            SentinelPay turns merchants into agent-readable, negotiable and safely transactable businesses for autonomous AI buyers — while every money movement remains strictly bounded by Z3 formal proofs.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.24 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-3"
          >
            <Button size="lg" className="w-full sm:w-auto text-xs md:text-sm h-11 px-6 gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl" asChild>
              <a href={isLoggedIn ? "/merchant/dashboard" : "/login"}>
                <Store className="w-4 h-4" /> Open Merchant Console
              </a>
            </Button>
            <Button size="lg" className="w-full sm:w-auto text-xs md:text-sm h-11 px-6 gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-xl" asChild>
              <a href="/buyer">
                <Bot className="w-4 h-4" /> Launch AI Marketplace &amp; Buyer
              </a>
            </Button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.35 }}
            className="pt-2"
          >
            <a 
              href="/judge" 
              className="inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-rose-400 transition-colors font-mono"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Adversarial Judge Mode — Test Z3 Security Kernel Resistance</span>
              <ArrowRight className="w-3 h-3" />
            </a>
          </motion.div>
        </div>
      </section>

      {/* Two Core Systems Showcase */}
      <section className="py-12 px-4 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* System A */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <a href={isLoggedIn ? "/merchant/dashboard" : "/login"} className="block h-full group">
              <Card className="glass-panel-hover h-full border-blue-500/20 bg-gradient-to-br from-blue-500/5 via-card/80 to-transparent rounded-2xl cursor-pointer p-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="p-3 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 group-hover:bg-blue-500/20 transition-colors">
                      <Store className="w-6 h-6" />
                    </div>
                    <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[10px] font-mono">
                      SYSTEM A · FINTECH SAAS
                    </Badge>
                  </div>

                  <div>
                    <h3 className="text-xl font-bold text-foreground">Sentinel Merchant Console</h3>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Make your catalog machine-readable, set floor prices, execute autonomous campaigns, and track verified AI revenue attribution.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border/40 text-xs text-muted-foreground">
                    {["Catalog Ingestion Hub", "Z3 Pricing Policies", "Honest Revenue Attribution", "Live Agent Telemetry", "Bulk Volume Tiers", "Order Settlement Ledger"].map((item) => (
                      <div key={item} className="flex items-center gap-1.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
                        <span className="text-[11px]">{item}</span>
                      </div>
                    ))}
                  </div>

                  <div className="pt-2 flex items-center gap-1.5 text-xs text-blue-400 font-semibold group-hover:gap-2.5 transition-all">
                    <span>Enter Merchant Console</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </div>
                </div>
              </Card>
            </a>
          </motion.div>

          {/* System B */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <a href="/buyer" className="block h-full group">
              <Card className="glass-panel-hover h-full border-emerald-500/20 bg-gradient-to-br from-emerald-500/5 via-card/80 to-transparent rounded-2xl cursor-pointer p-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 group-hover:bg-emerald-500/20 transition-colors">
                      <Bot className="w-6 h-6" />
                    </div>
                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px] font-mono">
                      SYSTEM B · AGENTIC COMMERCE
                    </Badge>
                  </div>

                  <div>
                    <h3 className="text-xl font-bold text-foreground">Sentinel AI Marketplace &amp; Buyer</h3>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Delegate purchases to an autonomous BuyerAgent that discovers multi-merchant offers, negotiates bounded discounts, and initiates server-verified Razorpay payments.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border/40 text-xs text-muted-foreground">
                    {["Natural Language Intent", "Global Marketplace Index", "Multi-Seller Comparison", "Explainable Ranking", "Capability Mandates", "Razorpay Test Checkout"].map((item) => (
                      <div key={item} className="flex items-center gap-1.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                        <span className="text-[11px]">{item}</span>
                      </div>
                    ))}
                  </div>

                  <div className="pt-2 flex items-center gap-1.5 text-xs text-emerald-400 font-semibold group-hover:gap-2.5 transition-all">
                    <span>Explore Global Marketplace</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </div>
                </div>
              </Card>
            </a>
          </motion.div>
        </div>
      </section>

      {/* Cryptographic Architecture Stack */}
      <section className="py-16 px-4">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="max-w-4xl mx-auto"
        >
          <div className="text-center mb-8 space-y-1">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              Deterministic Security Architecture
            </h2>
            <p className="text-xs text-muted-foreground">
              Two autonomous systems, zero-knowledge privacy, unified by mathematical verification.
            </p>
          </div>

          <div className="glass-panel border-border/60 rounded-2xl p-6 md:p-8 space-y-6">
            {/* Top Agents */}
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-blue-500/5 border border-blue-500/20 text-center space-y-1">
                <div className="flex items-center justify-center gap-1.5 text-blue-400 font-bold text-xs">
                  <Store className="w-4 h-4" /> MerchantAgent
                </div>
                <p className="text-[11px] text-muted-foreground">Catalog DTO · Floor Policies · In-Stock Fulfillment</p>
              </div>

              <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-center space-y-1">
                <div className="flex items-center justify-center gap-1.5 text-emerald-400 font-bold text-xs">
                  <Bot className="w-4 h-4" /> BuyerAgent
                </div>
                <p className="text-[11px] text-muted-foreground">Intent Extraction · Budget Mandate · Multi-Seller Choice</p>
              </div>
            </div>

            {/* Middle Pipeline Items */}
            <div className="space-y-2.5">
              {[
                { icon: <Scale className="w-4 h-4" />, label: "Unified Z3 Solver", desc: "Buyer ceiling + Merchant floor + inventory + campaigns evaluated in one SAT formulation", color: "text-amber-400", bg: "border-amber-500/20 bg-amber-500/5" },
                { icon: <Shield className="w-4 h-4" />, label: "SecurityKernel Authority", desc: "Sole authorized payment path: ALLOW / DENY / REQUIRE_APPROVAL", color: "text-rose-400", bg: "border-rose-500/20 bg-rose-500/5" },
                { icon: <CreditCard className="w-4 h-4" />, label: "Razorpay Test Execution", desc: "Server-side cryptographic order creation and HMAC verification", color: "text-indigo-400", bg: "border-indigo-500/20 bg-indigo-500/5" },
                { icon: <Eye className="w-4 h-4" />, label: "Immutable Audit Trail", desc: "Tamper-evident hash-chained events stored in durable PostgreSQL", color: "text-purple-400", bg: "border-purple-500/20 bg-purple-500/5" },
              ].map((item) => (
                <div key={item.label} className={`flex items-center gap-3 p-3 rounded-xl border ${item.bg} text-xs`}>
                  <div className={`${item.color} shrink-0`}>{item.icon}</div>
                  <div className="space-y-0.5">
                    <p className={`font-semibold ${item.color}`}>{item.label}</p>
                    <p className="text-[11px] text-muted-foreground">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="py-8 text-center text-xs text-muted-foreground border-t border-border/30 font-mono">
        <p>&copy; 2026 SentinelPay Systems · Razorpay Buildathon Track 01</p>
      </footer>
    </main>
  );
}
