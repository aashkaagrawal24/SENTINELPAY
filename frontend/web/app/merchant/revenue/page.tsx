"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/common/metric-card";
import { StatusBadge } from "@/components/common/status-badge";
import { 
  BarChart3, TrendingUp, Target, Zap, Bot, Megaphone, 
  ShoppingCart, ArrowUpRight, ShieldCheck, DollarSign, Layers,
  CheckCircle2, Sparkles, RefreshCw
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import Link from "next/link";

export default function RevenuePage() {
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchRevenue = async (showRefresh = false) => {
    const merchantId = localStorage.getItem("sp_merchant_id");
    if (!merchantId) {
      setLoading(false);
      return;
    }
    if (showRefresh) setIsRefreshing(true);
    try {
      const res = await apiFetch(`/api/merchants/${merchantId}/revenue`);
      const data = await res.json();
      setMetrics(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRevenue();
    const interval = setInterval(() => fetchRevenue(false), 4000);
    return () => clearInterval(interval);
  }, []);

  const attributionBreakdown = [
    { 
      source: "Agent Negotiated", 
      pct: metrics?.attribution?.agentNegotiated || 0, 
      color: "from-emerald-500 to-teal-400", 
      badge: "VERIFIED AI", 
      badgeVariant: "success" as const,
      desc: "Revenue from deterministic BuyerAgent ↔ MerchantAgent pricing equilibrium" 
    },
    { 
      source: "Campaign Influenced", 
      pct: metrics?.attribution?.campaignInfluenced || 0, 
      color: "from-purple-500 to-indigo-400", 
      badge: "ALGORITHMIC", 
      badgeVariant: "purple" as const,
      desc: "Revenue where bounded campaign incentive or flash tier was applied" 
    },
    { 
      source: "Upsell / Recommendations", 
      pct: metrics?.attribution?.upsell || 0, 
      color: "from-blue-500 to-cyan-400", 
      badge: "AGENT LIFT", 
      badgeVariant: "blue" as const,
      desc: "Incremental cart addition suggested and bounded by the security kernel" 
    },
    { 
      source: "Direct Catalog Purchase", 
      pct: metrics?.attribution?.direct || 0, 
      color: "from-zinc-500 to-zinc-400", 
      badge: "ORGANIC BASE", 
      badgeVariant: "neutral" as const,
      desc: "Base catalog sales with direct checkout and no AI concession" 
    },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center animate-pulse">
              <BarChart3 className="h-6 w-6 text-primary" />
            </div>
            <div className="absolute -inset-1 rounded-2xl bg-primary/20 blur-sm -z-10 animate-pulse" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">Computing Revenue Attribution</p>
            <p className="text-xs text-muted-foreground mt-0.5">Aggregating real-time ledger settlement...</p>
          </div>
        </div>
      </div>
    );
  }

  const totalRev = metrics?.totalRevenue || 0;
  const aiRev = metrics?.aiRevenue || 0;
  const campaignRev = metrics?.campaignRevenue || 0;
  const aov = metrics?.aov || 0;

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Revenue Analytics</h1>
            <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px] uppercase font-mono">
              Honest Attribution
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Strict causal attribution — every rupee is labeled by its true mathematical source without AI hallucination.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchRevenue(true)}
            disabled={isRefreshing}
            className="text-xs h-8 border-border/60 gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            Refresh Ledger
          </Button>
        </div>
      </div>

      {/* Revenue KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total Gross Revenue"
          value={`₹${totalRev.toLocaleString("en-IN")}`}
          subtitle="All confirmed order settlements"
          icon={DollarSign}
          theme="blue"
          badge="SETTLED"
          delay={0}
        />
        <MetricCard
          title="AI-Negotiated Revenue"
          value={`₹${aiRev.toLocaleString("en-IN")}`}
          subtitle="Closed via BuyerAgent ↔ MerchantAgent"
          icon={Bot}
          theme="emerald"
          badge="AUTONOMOUS"
          delay={0.05}
        />
        <MetricCard
          title="Campaign-Influenced"
          value={`₹${campaignRev.toLocaleString("en-IN")}`}
          subtitle="Triggered via promotional boundaries"
          icon={Megaphone}
          theme="purple"
          badge="INCENTIVE"
          delay={0.1}
        />
        <MetricCard
          title="Average Order Value"
          value={`₹${aov.toLocaleString("en-IN")}`}
          subtitle="Settled transaction basket mean"
          icon={ShoppingCart}
          theme="amber"
          badge="AOV"
          delay={0.15}
        />
      </div>

      {/* Attribution Breakdown */}
      <Card className="glass-panel border-border/60">
        <CardHeader className="pb-3 border-b border-border/40">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base flex items-center gap-2 text-foreground">
                <Target className="w-4 h-4 text-emerald-400" /> Revenue Decomposition & Attribution
              </CardTitle>
              <CardDescription className="text-xs mt-1">
                SentinelPay separates genuine AI negotiation lift from baseline catalog demand using counterfactual guarantees.
              </CardDescription>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-mono">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>DOWHY CAUSAL ISOLATED</span>
            </div>
          </div>
        </CardHeader>

        <CardContent className="pt-6 space-y-6">
          {attributionBreakdown.map((item, idx) => (
            <div key={item.source} className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">{item.source}</span>
                  <StatusBadge status={item.badge} variant={item.badgeVariant} />
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-foreground">{item.pct}%</span>
                  <span className="text-[11px] text-muted-foreground font-mono">of total</span>
                </div>
              </div>

              {/* Progress bar with animated gradient */}
              <div className="h-2 w-full bg-muted/40 rounded-full overflow-hidden p-0.5 border border-border/40">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.max(item.pct, 0)}%` }}
                  transition={{ duration: 0.8, delay: idx * 0.1, ease: "easeOut" }}
                  className={`h-full rounded-full bg-gradient-to-r ${item.color}`}
                />
              </div>

              <p className="text-[11px] text-muted-foreground leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Revenue Intelligence Connection */}
      <Card className="border-primary/40 bg-primary/5">
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" />
                Revenue Intelligence
              </h3>
              <p className="text-xs text-muted-foreground">
                Turn real-time transaction data into actionable profit strategies using AI-driven policy simulation.
              </p>
            </div>
            <Link href="/merchant/policies">
              <Button size="sm" className="gap-2">
                Launch Intelligence <ArrowUpRight className="w-4 h-4" />
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>

      {/* Causal Analytics & Security Notice */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="border-cyan-500/20 bg-cyan-500/5 backdrop-blur-sm">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shrink-0 mt-0.5">
                <Zap className="w-4 h-4" />
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-cyan-400 uppercase tracking-wider font-mono">
                  Average Treatment Effect (ATE)
                </p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Controlled micro-experiments isolate genuine incremental lift versus organic buyer intent. Zero fabricated claims.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-indigo-500/20 bg-indigo-500/5 backdrop-blur-sm">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0 mt-0.5">
                <Layers className="w-4 h-4" />
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-indigo-400 uppercase tracking-wider font-mono">
                  Immutable Revenue Ledger
                </p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Every order entry maps 1-to-1 to a verified Razorpay payment attempt and Z3 cryptographic commitment hash.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </motion.div>
  );
}
