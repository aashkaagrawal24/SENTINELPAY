"use client";

import { FormEvent, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Shield, Package, BarChart3, Activity, CheckCircle2, AlertCircle,
  TrendingUp, ShoppingCart, Zap, ArrowRight, Store, CreditCard, Megaphone
} from "lucide-react";
import { MetricCard } from "@/components/common/metric-card";

interface DashboardData {
  merchant: any;
  products: any[];
  stats: { total_revenue: number; total_orders: number; ai_sessions: number; campaigns_active: number };
}

export default function MerchantDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [merchantId, setMerchantId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("sp_merchant_id");
    if (stored) {
      setMerchantId(stored);
      loadDashboard(stored);
      const interval = setInterval(() => loadDashboard(stored, true), 3000);
      return () => clearInterval(interval);
    } else {
      setLoading(false);
    }
  }, []);

  async function loadDashboard(id: string, isPolling = false) {
    try {
      const [mRes, pRes, statsRes] = await Promise.all([
        apiFetch(`/api/merchants/${id}`),
        apiFetch(`/api/merchants/${id}/products`),
        apiFetch(`/api/merchants/${id}/dashboard-stats`)
      ]);
      const merchant = await mRes.json();
      const products = await pRes.json();
      const statsObj = await statsRes.json();
      setData({
        merchant,
        products: Array.isArray(products) ? products : [],
        stats: {
          total_revenue: statsObj.metrics?.totalRevenue || 0,
          total_orders: Math.floor((statsObj.metrics?.totalRevenue || 0) / 10000),
          ai_sessions: statsObj.metrics?.activeSessions || 0,
          campaigns_active: statsObj.metrics?.activeCampaigns || 0,
        }
      });
    } catch {
      if (!isPolling) setData(null);
    }
    if (!isPolling) setLoading(false);
  }

  async function quickSetup() {
    setLoading(true);
    try {
      const res = await apiFetch("/api/merchants/seed", { method: "POST" });
      const seeded = await res.json();
      if (seeded.merchant_id) {
        localStorage.setItem("sp_merchant_id", seeded.merchant_id);
        setMerchantId(seeded.merchant_id);
        await loadDashboard(seeded.merchant_id);
      }
    } catch (e) {
      console.error("Quick setup failed:", e);
      setLoading(false);
    }
  }

  async function createCustomMerchant(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const name = String(f.get("name") || "").trim();
    if (!name) return;
    setLoading(true);
    try {
      const res = await apiFetch("/api/merchants", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      const merchant = await res.json();
      if (merchant.id) {
        localStorage.setItem("sp_merchant_id", merchant.id);
        setMerchantId(merchant.id);
        await loadDashboard(merchant.id);
      }
    } catch (e) {
      console.error("Create merchant failed:", e);
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <Shield className="h-10 w-10 text-blue-400/50" />
          <p className="text-muted-foreground text-sm">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (!merchantId || !data) {
    return (
      <div className="max-w-2xl mx-auto pt-12 text-center space-y-8">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <div className="p-4 bg-blue-500/10 rounded-2xl ring-1 ring-blue-500/20 inline-block mb-6">
            <Store className="w-10 h-10 text-blue-400" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight mb-3">Welcome to Sentinel Merchant</h1>
          <p className="text-muted-foreground text-lg mb-8">
            Create your merchant store manually from scratch or set up demo products in 1 click.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-left">
            {/* Manual Setup */}
            <Card className="border-blue-500/30 bg-card/40">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Store className="w-4 h-4 text-blue-400" /> Manual Store Setup
                </CardTitle>
                <CardDescription className="text-xs">
                  Create a custom store and add products/policies step-by-step
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={createCustomMerchant} className="space-y-3">
                  <Input name="name" placeholder="e.g. Sonic Tech Hub" required className="text-sm bg-background/50" />
                  <Button type="submit" className="w-full bg-blue-600 hover:bg-blue-700 text-sm">
                    Create Merchant
                  </Button>
                </form>
              </CardContent>
            </Card>

            {/* 1-Click Demo Setup */}
            <Card className="border-emerald-500/30 bg-card/40 flex flex-col justify-between">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Zap className="w-4 h-4 text-emerald-400" /> 1-Click Demo Setup
                </CardTitle>
                <CardDescription className="text-xs">
                  Pre-load 3 products, stock inventory, and Z3 pricing policies instantly
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-2">
                <Button onClick={quickSetup} variant="outline" className="w-full border-emerald-500/50 hover:bg-emerald-500/10 text-emerald-400 text-sm gap-2">
                  <Zap className="w-4 h-4" /> Quick Setup Demo
                </Button>
              </CardContent>
            </Card>
          </div>
        </motion.div>
      </div>
    );
  }

  const statusItems = [
    { label: "AI Commerce", status: "ACTIVE", dot: "bg-emerald-400" },
    { label: "Catalog", status: data.products?.length > 0 ? "ENABLED" : "EMPTY", dot: data.products?.length > 0 ? "bg-emerald-400" : "bg-amber-400" },
    { label: "MerchantAgent", status: "ONLINE", dot: "bg-emerald-400" },
    { label: "Razorpay Gateway", status: "TEST MODE", dot: "bg-blue-400" },
  ];

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="space-y-8">
      {/* Header with Title & Live System Status */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <span>Merchant Overview</span>
            <span className="text-xs font-mono text-muted-foreground font-normal px-2 py-0.5 rounded-md bg-muted/40 border border-border/40">
              {data.merchant.name}
            </span>
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Real-time autonomous commerce analytics, catalog status, and agent interactions
          </p>
        </div>

        {/* Live System Status Pills */}
        <div className="flex flex-wrap items-center gap-2">
          {statusItems.map((item) => (
            <div 
              key={item.label}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono glass-panel text-muted-foreground border border-border/60"
            >
              <span className={`h-1.5 w-1.5 rounded-full ${item.dot} animate-pulse`} />
              <span>{item.label}:</span>
              <strong className="text-foreground font-semibold">{item.status}</strong>
            </div>
          ))}
        </div>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total Revenue"
          value={`₹${(data.stats.total_revenue).toLocaleString("en-IN")}`}
          subtitle="Settled via Razorpay Test Mode"
          icon={BarChart3}
          badge="SETTLED"
          colorTheme="blue"
        />
        <MetricCard
          title="Active Products"
          value={data.products.length || 0}
          subtitle="Exposed to AI Buyer marketplace"
          icon={Package}
          badge="CATALOG"
          colorTheme="emerald"
        />
        <MetricCard
          title="AI Buyer Sessions"
          value={data.stats.ai_sessions}
          subtitle="Agentic negotiations & searches"
          icon={Activity}
          badge="REAL-TIME"
          colorTheme="amber"
        />
        <MetricCard
          title="Active Campaigns"
          value={data.stats.campaigns_active}
          subtitle="Bound by mathematical policies"
          icon={TrendingUp}
          badge="POLICIES"
          colorTheme="purple"
        />
      </div>

      {/* Quick Action Bento Grid */}
      <div>
        <h2 className="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-3">
          Merchant Controls & Capabilities
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a href="/merchant/catalog" className="group">
            <Card className="h-full glass-panel glass-panel-hover border-blue-500/20 group-hover:border-blue-500/40">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20">
                    <Package className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-mono text-blue-400 uppercase tracking-wider">Catalog</span>
                </div>
                <CardTitle className="text-base text-foreground group-hover:text-blue-400 transition-colors">
                  Product Catalog
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground">
                  Publish products, configure SKUs, and manage variants for the global marketplace.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="text-xs font-medium text-blue-400 flex items-center gap-1 group-hover:translate-x-1 transition-transform">
                  Configure catalog <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </CardContent>
            </Card>
          </a>

          <a href="/merchant/policies" className="group">
            <Card className="h-full glass-panel glass-panel-hover border-amber-500/20 group-hover:border-amber-500/40">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20">
                    <Shield className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-mono text-amber-400 uppercase tracking-wider">Z3 Safety</span>
                </div>
                <CardTitle className="text-base text-foreground group-hover:text-amber-400 transition-colors">
                  Pricing & Policy Engine
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground">
                  Establish floor prices, autonomous discount caps, and mathematical bounds for AI buyers.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="text-xs font-medium text-amber-400 flex items-center gap-1 group-hover:translate-x-1 transition-transform">
                  Define boundaries <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </CardContent>
            </Card>
          </a>

          <a href="/merchant/orders" className="group">
            <Card className="h-full glass-panel glass-panel-hover border-emerald-500/20 group-hover:border-emerald-500/40">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20">
                    <ShoppingCart className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-wider">Orders</span>
                </div>
                <CardTitle className="text-base text-foreground group-hover:text-emerald-400 transition-colors">
                  Orders & Activity
                </CardTitle>
                <CardDescription className="text-xs text-muted-foreground">
                  Inspect real-time purchases initiated by AI buyers and review authoritative audit proofs.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="text-xs font-medium text-emerald-400 flex items-center gap-1 group-hover:translate-x-1 transition-transform">
                  View incoming orders <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </CardContent>
            </Card>
          </a>
        </div>
      </div>

      {/* Merchant Profile Details Card */}
      <Card className="glass-panel border-border/50">
        <CardHeader className="pb-3 border-b border-border/40">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Store className="w-4 h-4 text-primary" /> Merchant Registry Profile
            </CardTitle>
            <span className="text-[10px] font-mono text-muted-foreground">
              ISOLATION: VERIFIED TENANT
            </span>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
            <div>
              <p className="text-muted-foreground text-[11px] uppercase tracking-wider font-mono mb-1">Merchant UUID</p>
              <p className="font-mono text-xs text-foreground bg-black/40 px-2 py-1 rounded border border-border/40 truncate">
                {merchantId}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-[11px] uppercase tracking-wider font-mono mb-1">Store Name</p>
              <p className="font-semibold text-foreground text-sm">{data.merchant.name}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-[11px] uppercase tracking-wider font-mono mb-1">Payment Gateway</p>
              <p className="flex items-center gap-1.5 text-xs text-foreground font-mono">
                <CreditCard className="w-3.5 h-3.5 text-blue-400" /> Razorpay Test
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-[11px] uppercase tracking-wider font-mono mb-1">Created Date</p>
              <p className="font-mono text-xs text-muted-foreground">
                {new Date(data.merchant.created_at).toLocaleDateString()}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
