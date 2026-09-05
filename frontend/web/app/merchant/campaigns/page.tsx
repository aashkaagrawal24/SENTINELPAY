"use client";

import { FormEvent, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Megaphone, Sparkles, RefreshCw, Play, Pause, Square,
  CheckCircle2, AlertTriangle, ShieldCheck, ArrowRight, Target, DollarSign, Calendar
} from "lucide-react";

type Opportunity = {
  id: string;
  score: number;
  reasons: string[];
  input_metrics: Record<string, unknown>;
  product_ids: string[];
  status: string;
};

type Campaign = {
  id: string;
  name: string;
  status: string;
  used_discount_budget_minor: number;
  reserved_discount_budget_minor: number;
  total_discount_budget_minor: number;
  current_redemptions: number;
  reserved_redemptions: number;
  maximum_redemptions: number;
  start_time: string;
  end_time: string;
};

export default function CampaignsPage() {
  const [merchantId, setMerchantId] = useState("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [status, setStatus] = useState("Ready to manage autonomous campaigns.");
  const [loading, setLoading] = useState(false);
  const [selectedOppId, setSelectedOppId] = useState("");
  const [selectedProductId, setSelectedProductId] = useState("");
  const [activeTab, setActiveTab] = useState("opportunities");
  const [formError, setFormError] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem("sp_merchant_id");
    if (stored) {
      setMerchantId(stored);
      loadCampaignData(stored);
    } else {
      // Default demo merchant if none found
      const defaultId = "10000000-0000-0000-0000-000000000001";
      setMerchantId(defaultId);
      loadCampaignData(defaultId);
    }
  }, []);

  async function call(path: string, init: RequestInit = {}) {
    const response = await apiFetch(path, init);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    return data;
  }

  async function loadCampaignData(id: string) {
    if (!id) return;
    setLoading(true);
    try {
      const [ops, active] = await Promise.all([
        call(`/api/merchants/${id}/campaign-opportunities`).catch(() => []),
        call(`/api/merchants/${id}/campaigns`).catch(() => [])
      ]);
      setOpportunities(Array.isArray(ops) ? ops : []);
      setCampaigns(Array.isArray(active) ? active : []);
      setStatus("Campaign state up-to-date with database signals.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }

  async function scan() {
    if (!merchantId) return;
    setLoading(true);
    try {
      const data = await call(`/api/merchants/${merchantId}/campaign-opportunities/scan`, {
        method: "POST",
        body: "{}"
      });
      setOpportunities(Array.isArray(data) ? data : []);
      setStatus(`${data.length} opportunity signals generated from PostgreSQL telemetry.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }

  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!merchantId) return;
    setLoading(true);
    const form = new FormData(event.currentTarget);
    const oppId = String(form.get("opportunity_id") || selectedOppId || "");
    const prodId = String(form.get("product_id") || selectedProductId || "783f7f92-b461-4fbe-9652-73bdbd8dda09");
    setFormError("");

    try {
      const startDate = form.get("start") ? new Date(String(form.get("start"))).toISOString() : new Date().toISOString();
      const endDate = form.get("end")
        ? new Date(String(form.get("end"))).toISOString()
        : new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

      await call(`/api/merchants/${merchantId}/campaigns`, {
        method: "POST",
        body: JSON.stringify({
          opportunity_id: oppId || null,
          name: form.get("name") || "XM4 Inventory Conversion",
          campaign_type: "INVENTORY_CONVERSION",
          objective: form.get("objective") || "Convert verified headphone demand",
          product_ids: [prodId],
          discount_type: "PERCENT",
          discount_value: Number(form.get("discount_bps") || 500),
          max_discount_per_order_minor: Number(form.get("max_discount") || 1000) * 100,
          total_discount_budget_minor: Number(form.get("budget") || 5000) * 100,
          maximum_redemptions: Number(form.get("redemptions") || 5),
          minimum_final_price_minor: Number(form.get("floor") || 18500) * 100,
          eligibility: { minimum_remaining_budget_minor: 50000 },
          start_time: startDate,
          end_time: endDate,
          stop_conditions: { inventory_below: 2 },
          requires_merchant_approval: true
        })
      });
      setStatus("Campaign created! State remains PROPOSED until operator explicit approval.");
      await loadCampaignData(merchantId);
      setActiveTab("active");
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Proposal failed";
      setStatus(msg);
      setFormError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function control(campaignId: string, action: "approve" | "pause" | "stop") {
    if (!merchantId) return;
    setLoading(true);
    try {
      await call(`/api/merchants/${merchantId}/campaigns/${campaignId}/${action}`, {
        method: "POST",
        body: "{}"
      });
      setStatus(`Campaign transition '${action}' committed to immutable audit log.`);
      await loadCampaignData(merchantId);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Transition failed");
    } finally {
      setLoading(false);
    }
  }

  // Pre-fill next week for datetime-local
  const defaultStart = new Date().toISOString().slice(0, 16);
  const defaultEnd = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16);

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-border/40">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20">
              <Megaphone className="w-5 h-5" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight">Campaign Control Room</h1>
            <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs">
              REAL DATA ONLY
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            PostgreSQL signal-backed opportunity detection and mathematically bounded promotions.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 bg-card/60 border border-border/50 rounded-lg px-3 py-1.5">
            <Label htmlFor="mId" className="text-xs text-muted-foreground shrink-0">Merchant:</Label>
            <Input
              id="mId"
              value={merchantId}
              onChange={(e) => {
                setMerchantId(e.target.value);
                localStorage.setItem("sp_merchant_id", e.target.value);
              }}
              placeholder="Merchant UUID"
              className="h-7 text-xs w-48 font-mono bg-background/50"
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => loadCampaignData(merchantId)}
            disabled={loading || !merchantId}
            className="gap-1.5 text-xs h-9"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button
            size="sm"
            onClick={scan}
            disabled={loading || !merchantId}
            className="gap-1.5 text-xs h-9 bg-blue-600 hover:bg-blue-700 text-white"
          >
            <Sparkles className="w-3.5 h-3.5" /> Scan Opportunities
          </Button>
        </div>
      </div>

      {/* Status Bar */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-card/40 border border-border/40 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-muted-foreground">{status}</span>
        </div>
        <div className="flex items-center gap-3 text-muted-foreground">
          <span>Signals: <strong className="text-foreground">{opportunities.length}</strong></span>
          <span>Active Campaigns: <strong className="text-foreground">{campaigns.length}</strong></span>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="bg-card/60 border border-border/50 p-1">
          <TabsTrigger value="opportunities" className="gap-2">
            <Sparkles className="w-4 h-4 text-blue-400" />
            Detected Opportunities ({opportunities.length})
          </TabsTrigger>
          <TabsTrigger value="propose" className="gap-2">
            <Target className="w-4 h-4 text-amber-400" />
            Propose Bounded Campaign
          </TabsTrigger>
          <TabsTrigger value="active" className="gap-2">
            <Megaphone className="w-4 h-4 text-emerald-400" />
            Active & Proposed Campaigns ({campaigns.length})
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Opportunities */}
        <TabsContent value="opportunities" className="space-y-4">
          {opportunities.length === 0 ? (
            <Card className="border-border/50 bg-card/30 text-center py-12">
              <CardContent className="space-y-3">
                <Sparkles className="w-10 h-10 text-muted-foreground/40 mx-auto" />
                <h3 className="text-base font-semibold">No Opportunity Signals Found</h3>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Click <strong>&quot;Scan Opportunities&quot;</strong> above to analyze real PostgreSQL inventory velocity, margin headroom, and buyer demand.
                </p>
                <Button size="sm" onClick={scan} disabled={loading} className="bg-blue-600 hover:bg-blue-700">
                  Run Opportunity Detector
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {opportunities.map((item, idx) => {
                const m = item.input_metrics as Record<string, number>;
                const stock = Number(m.available_quantity ?? 0);
                const marginPct = Math.round(Number(m.margin_room ?? 0) * 100);
                const confidence = Math.round(Number(item.score) * 100);
                const pressure = Number(m.inventory_pressure ?? 0);
                const views = Number(m.product_views ?? 0);
                const carts = Number(m.abandoned_carts ?? 0);

                // Derive urgency level
                const urgency = confidence >= 40 ? "HIGH" : confidence >= 33 ? "MEDIUM" : "LOW";
                const urgencyStyle = urgency === "HIGH"
                  ? "text-red-400 bg-red-500/10 border-red-500/20"
                  : urgency === "MEDIUM"
                  ? "text-amber-400 bg-amber-500/10 border-amber-500/20"
                  : "text-blue-400 bg-blue-500/10 border-blue-500/20";

                // Headline signal
                const headline = item.reasons.includes("EXCESS_INVENTORY")
                  ? stock >= 200
                    ? `${stock} units sitting idle — major overstock risk`
                    : `${stock} units with no active demand — clearance needed`
                  : item.reasons.includes("HIGH_INTEREST_LOW_CONVERSION")
                  ? "Strong buyer interest but low conversion — discount can close the gap"
                  : item.reasons.includes("ABANDONED_CARTS")
                  ? `${carts} abandoned cart${carts !== 1 ? "s" : ""} detected — recovery opportunity`
                  : "AI detected a pricing opportunity for this product";

                // Recommended action
                const suggestedDiscount = marginPct >= 15 ? "8–12%" : marginPct >= 10 ? "5–8%" : "3–5%";

                return (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.04 }}
                  >
                    <Card className={`border overflow-hidden hover:shadow-lg transition-all duration-300 ${
                      urgency === "HIGH" ? "border-red-500/20 hover:border-red-500/40" :
                      urgency === "MEDIUM" ? "border-amber-500/20 hover:border-amber-500/40" :
                      "border-border/50 hover:border-blue-500/30"
                    } bg-card/60 backdrop-blur`}>

                      {/* Card Top Bar */}
                      <div className={`h-1 w-full ${
                        urgency === "HIGH" ? "bg-gradient-to-r from-red-500 to-orange-500" :
                        urgency === "MEDIUM" ? "bg-gradient-to-r from-amber-500 to-yellow-400" :
                        "bg-gradient-to-r from-blue-500 to-indigo-500"
                      }`} />

                      <CardContent className="p-4 space-y-4">
                        {/* Header Row */}
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <Badge variant="outline" className={`text-[10px] font-semibold px-2 py-0.5 ${urgencyStyle}`}>
                                {urgency} PRIORITY
                              </Badge>
                              <Badge variant="outline" className="text-[10px] text-emerald-400 bg-emerald-500/10 border-emerald-500/20 px-2 py-0.5">
                                {item.status}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground leading-relaxed mt-1">{headline}</p>
                          </div>

                          {/* Confidence Ring */}
                          <div className="flex flex-col items-center flex-shrink-0">
                            <div className="relative w-12 h-12">
                              <svg viewBox="0 0 36 36" className="w-12 h-12 -rotate-90">
                                <circle cx="18" cy="18" r="14" fill="none" className="stroke-muted/30" strokeWidth="3" />
                                <circle
                                  cx="18" cy="18" r="14" fill="none"
                                  className={urgency === "HIGH" ? "stroke-red-400" : urgency === "MEDIUM" ? "stroke-amber-400" : "stroke-blue-400"}
                                  strokeWidth="3"
                                  strokeDasharray={`${confidence * 0.88} 88`}
                                  strokeLinecap="round"
                                />
                              </svg>
                              <span className="absolute inset-0 flex items-center justify-center text-xs font-bold">{confidence}%</span>
                            </div>
                            <span className="text-[9px] text-muted-foreground mt-0.5">confidence</span>
                          </div>
                        </div>

                        {/* Signal Tags */}
                        <div className="flex flex-wrap gap-1.5">
                          {item.reasons.map((r) => (
                            <span key={r} className="text-[10px] font-medium bg-blue-500/10 text-blue-300 border border-blue-500/20 rounded-full px-2 py-0.5">
                              {r.replace(/_/g, " ")}
                            </span>
                          ))}
                        </div>

                        {/* Key Metrics Grid */}
                        <div className="grid grid-cols-3 gap-2">
                          <div className="bg-muted/20 rounded-lg p-2 text-center border border-border/30">
                            <p className="text-[10px] text-muted-foreground mb-0.5">Stock</p>
                            <p className="font-bold text-sm text-amber-400">{stock}</p>
                            <p className="text-[9px] text-muted-foreground">units</p>
                          </div>
                          <div className="bg-muted/20 rounded-lg p-2 text-center border border-border/30">
                            <p className="text-[10px] text-muted-foreground mb-0.5">Margin Room</p>
                            <p className={`font-bold text-sm ${marginPct >= 15 ? "text-emerald-400" : "text-amber-400"}`}>{marginPct}%</p>
                            <p className="text-[9px] text-muted-foreground">available</p>
                          </div>
                          <div className="bg-muted/20 rounded-lg p-2 text-center border border-border/30">
                            <p className="text-[10px] text-muted-foreground mb-0.5">Demand</p>
                            <p className={`font-bold text-sm ${views + carts > 0 ? "text-blue-400" : "text-muted-foreground"}`}>
                              {views + carts > 0 ? views + carts : "—"}
                            </p>
                            <p className="text-[9px] text-muted-foreground">signals</p>
                          </div>
                        </div>

                        {/* Inventory bar */}
                        <div className="space-y-1">
                          <div className="flex justify-between text-[10px] text-muted-foreground">
                            <span>Inventory pressure</span>
                            <span className={pressure >= 0.8 ? "text-red-400 font-semibold" : "text-muted-foreground"}>
                              {pressure >= 0.8 ? "Excess" : pressure >= 0.5 ? "High" : "Normal"}
                            </span>
                          </div>
                          <div className="h-1.5 bg-muted/30 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-700 ${
                                pressure >= 0.8 ? "bg-gradient-to-r from-red-500 to-orange-400" :
                                pressure >= 0.5 ? "bg-gradient-to-r from-amber-500 to-yellow-400" :
                                "bg-gradient-to-r from-blue-500 to-indigo-400"
                              }`}
                              style={{ width: `${Math.min(100, pressure * 100)}%` }}
                            />
                          </div>
                        </div>

                        {/* AI Suggestion */}
                        <div className="bg-blue-500/5 border border-blue-500/15 rounded-lg p-2.5 flex items-start gap-2">
                          <Sparkles className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-[10px] font-semibold text-blue-300">AI Suggestion</p>
                            <p className="text-[10px] text-muted-foreground mt-0.5">
                              Apply <strong className="text-blue-300">{suggestedDiscount} discount</strong> within your {marginPct}% margin headroom to unlock demand signals.
                            </p>
                          </div>
                        </div>

                        {/* Product ID pill */}
                        {item.product_ids?.[0] && (
                          <p className="text-[9px] font-mono text-muted-foreground/50 truncate">
                            Product: {item.product_ids[0]}
                          </p>
                        )}

                        {/* CTA */}
                        <Button
                          size="sm"
                          className="w-full text-xs gap-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-sm"
                          onClick={() => {
                            setSelectedOppId(item.id);
                            if (item.product_ids?.[0]) setSelectedProductId(item.product_ids[0]);
                            setActiveTab("propose");
                          }}
                        >
                          <Target className="w-3.5 h-3.5" />
                          Convert to Bounded Campaign
                          <ArrowRight className="w-3 h-3" />
                        </Button>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* Tab 2: Propose Campaign Form */}
        <TabsContent value="propose" className="space-y-4">
          <Card className="border-border/50 bg-card/40 max-w-3xl">
            <CardHeader>
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-amber-400" />
                <CardTitle className="text-lg">Propose Bounded Campaign</CardTitle>
              </div>
              <CardDescription>
                Campaigns remain in <strong className="text-amber-400">PROPOSED</strong> state. No discounts are applied autonomously without formal SecurityKernel boundaries and explicit operator confirmation.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={propose} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="oppSelect">Linked Opportunity</Label>
                    <select
                      id="oppSelect"
                      name="opportunity_id"
                      value={selectedOppId}
                      onChange={(e) => setSelectedOppId(e.target.value)}
                      className="w-full h-9 rounded-md border border-input bg-background/50 px-3 py-1 text-sm text-foreground"
                    >
                      <option value="">Manual Promotion (No Linked Opp)</option>
                      {opportunities.filter(o => o.status === "OPEN").map(o => (
                        <option value={o.id} key={o.id}>
                          {o.id.slice(0, 8)}... ({Math.round(o.score * 100)}% score)
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="prodId">Target Product UUID</Label>
                    <Input
                      id="prodId"
                      name="product_id"
                      value={selectedProductId}
                      onChange={(e) => setSelectedProductId(e.target.value)}
                      placeholder="e.g. 783f7f92-b461-4fbe-9652-73bdbd8dda09"
                      className="bg-background/50 font-mono text-xs"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="cName">Campaign Name</Label>
                    <Input
                      id="cName"
                      name="name"
                      defaultValue="XM4 Inventory Conversion"
                      required
                      className="bg-background/50"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="cObj">Objective</Label>
                    <Input
                      id="cObj"
                      name="objective"
                      defaultValue="Convert verified headphone demand"
                      required
                      className="bg-background/50"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 border-t border-border/30">
                  <div className="space-y-1.5">
                    <Label htmlFor="dBps">Discount BPS (500 = 5%)</Label>
                    <Input
                      id="dBps"
                      name="discount_bps"
                      type="number"
                      defaultValue="500"
                      required
                      className="bg-background/50"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="mDisc">Max Discount / Order (INR)</Label>
                    <Input
                      id="mDisc"
                      name="max_discount"
                      type="number"
                      defaultValue="1000"
                      required
                      className="bg-background/50"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="tBudg">Total Budget (INR)</Label>
                    <Input
                      id="tBudg"
                      name="budget"
                      type="number"
                      defaultValue="5000"
                      required
                      className="bg-background/50"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="mRed">Maximum Redemptions</Label>
                    <Input
                      id="mRed"
                      name="redemptions"
                      type="number"
                      defaultValue="5"
                      required
                      className="bg-background/50"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="mFloor">Minimum Floor Price (INR)</Label>
                    <Input
                      id="mFloor"
                      name="floor"
                      type="number"
                      defaultValue="18500"
                      required
                      className="bg-background/50"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="sDate">Start Date/Time</Label>
                    <Input
                      id="sDate"
                      name="start"
                      type="datetime-local"
                      defaultValue={defaultStart}
                      required
                      className="bg-background/50 text-xs"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="eDate">End Date/Time</Label>
                    <Input
                      id="eDate"
                      name="end"
                      type="datetime-local"
                      defaultValue={defaultEnd}
                      required
                      className="bg-background/50 text-xs"
                    />
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>Security Kernel will prevent redemptions if product inventory falls below 2 units.</span>
                </div>

                {formError && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400 flex items-start gap-2 animate-in fade-in zoom-in-95">
                    <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
                    <div>
                      <strong className="block font-semibold mb-1">Campaign Rejected by Security Kernel</strong>
                      <span>{formError}</span>
                    </div>
                  </div>
                )}

                <Button type="submit" disabled={loading || !merchantId} className="w-full bg-amber-600 hover:bg-amber-700 text-white">
                  Create PROPOSED Campaign
                </Button>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: Active Campaigns */}
        <TabsContent value="active" className="space-y-4">
          {campaigns.length === 0 ? (
            <Card className="border-border/50 bg-card/30 text-center py-12">
              <CardContent className="space-y-3">
                <Megaphone className="w-10 h-10 text-muted-foreground/40 mx-auto" />
                <h3 className="text-base font-semibold">No Campaigns Created Yet</h3>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Propose your first campaign from detected opportunities or using custom mathematical constraints.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {campaigns.map((item) => {
                const used = (item.used_discount_budget_minor + item.reserved_discount_budget_minor) / 100;
                const total = item.total_discount_budget_minor / 100;
                const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;

                return (
                  <motion.div key={item.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                    <Card className="border-border/50 bg-card/50">
                      <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                          <Badge className={`text-[10px] ${
                            item.status === "ACTIVE"
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                              : item.status === "PROPOSED"
                              ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                              : "bg-red-500/10 text-red-400 border-red-500/20"
                          }`}>
                            {item.status}
                          </Badge>
                          <span className="text-xs text-muted-foreground font-mono">
                            {item.id.slice(0, 8)}...
                          </span>
                        </div>
                        <CardTitle className="text-base mt-2">{item.name}</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {/* Budget Bar */}
                        <div className="space-y-1.5">
                          <div className="flex justify-between text-xs">
                            <span className="text-muted-foreground">Budget Spent:</span>
                            <span className="font-semibold">₹{used.toLocaleString("en-IN")} / ₹{total.toLocaleString("en-IN")}</span>
                          </div>
                          <div className="w-full bg-secondary/50 rounded-full h-2 overflow-hidden">
                            <div className="bg-blue-500 h-2 rounded-full transition-all duration-300" style={{ width: `${pct}%` }} />
                          </div>
                        </div>

                        {/* Metrics */}
                        <div className="grid grid-cols-2 gap-2 text-xs bg-black/30 p-2.5 rounded-lg border border-border/30">
                          <div>
                            <p className="text-muted-foreground">Redemptions</p>
                            <p className="font-semibold">{item.current_redemptions + item.reserved_redemptions} / {item.maximum_redemptions}</p>
                          </div>
                          <div>
                            <p className="text-muted-foreground">Duration</p>
                            <p className="font-semibold">{new Date(item.start_time).toLocaleDateString()} - {new Date(item.end_time).toLocaleDateString()}</p>
                          </div>
                        </div>

                        {/* Controls */}
                        <div className="flex items-center gap-2 pt-2">
                          {item.status === "PROPOSED" && (
                            <Button
                              size="sm"
                              onClick={() => control(item.id, "approve")}
                              disabled={loading}
                              className="flex-1 text-xs gap-1 bg-emerald-600 hover:bg-emerald-700"
                            >
                              <Play className="w-3.5 h-3.5" /> Approve
                            </Button>
                          )}
                          {item.status === "ACTIVE" && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => control(item.id, "pause")}
                              disabled={loading}
                              className="flex-1 text-xs gap-1 text-amber-400 hover:text-amber-300 border-amber-500/30"
                            >
                              <Pause className="w-3.5 h-3.5" /> Pause
                            </Button>
                          )}
                          {["ACTIVE", "PAUSED", "SCHEDULED"].includes(item.status) && (
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => control(item.id, "stop")}
                              disabled={loading}
                              className="text-xs gap-1"
                            >
                              <Square className="w-3.5 h-3.5" /> Stop
                            </Button>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
