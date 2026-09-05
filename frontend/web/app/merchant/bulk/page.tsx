"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { apiFetch } from "@/lib/api";
import {
  Package, TrendingUp, Clock, CheckCircle2, XCircle, Boxes,
  Bot, Store, ChevronRight, AlertTriangle, Loader2, RefreshCw,
  ShieldCheck, BarChart3, Zap, Edit3, Send, Ban
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type RFQ = {
  rfq_id: string;
  product_name: string;
  base_price_inr: number;
  category: string;
  requested_quantity: number;
  available_to_promise: number;
  status: string;
  created_at: string;
  expires_at: string;
  negotiation_id?: string;
  neg_status?: string;
  final_unit_price_inr?: number;
  final_total_inr?: number;
};

type Analytics = {
  bulk: { revenue_inr: number; orders: number; avg_order_value_inr: number };
  retail: { revenue_inr: number; orders: number };
  total_revenue_inr: number;
  active_rfqs: number;
  active_negotiations: number;
};

type Opportunity = {
  product_id: string;
  product_name: string;
  category: string;
  base_price_inr: number;
  available_quantity: number;
  estimated_excess: number;
  suggested_bulk_range: { min: number; max: number };
  recommended_opening_price_inr: number;
  expected_settlement_range_inr: { low: number; high: number };
  estimated_revenue_range_inr: { low: number; high: number };
  confidence: string;
};

export default function BulkCommercePage() {
  const [merchantId, setMerchantId] = useState<string>("");
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRFQ, setSelectedRFQ] = useState<string | null>(null);
  const [analysisData, setAnalysisData] = useState<Record<string, Record<string, unknown>>>({});
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [sendingQuote, setSendingQuote] = useState<string | null>(null);

  const fetchAll = useCallback(async (mid: string) => {
    if (!mid) return;
    try {
      const [analyticsR, rfqsR, oppR] = await Promise.all([
        apiFetch(`/api/bulk/analytics/${mid}`),
        apiFetch(`/api/bulk/rfqs/merchant/${mid}`),
        apiFetch(`/api/bulk/opportunities/${mid}`),
      ]);
      if (analyticsR.ok) setAnalytics(await analyticsR.json());
      if (rfqsR.ok) { const d = await rfqsR.json(); setRfqs(d.rfqs || []); }
      if (oppR.ok) { const d = await oppR.json(); setOpportunities(d.opportunities || []); }
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    const mid = localStorage.getItem("sp_merchant_id") || "";
    setMerchantId(mid);
    if (mid) fetchAll(mid);
    else setLoading(false);
  }, [fetchAll]);

  // SSE for real-time RFQ updates
  useEffect(() => {
    if (!merchantId) return;
    const evtSource = new EventSource(
      `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/merchants/${merchantId}/events/stream`
    );
    evtSource.addEventListener("BULK_RFQ_CREATED", () => fetchAll(merchantId));
    evtSource.addEventListener("BULK_OFFER_ACCEPTED", () => fetchAll(merchantId));
    evtSource.addEventListener("BULK_COUNTER_OFFER", () => fetchAll(merchantId));
    return () => evtSource.close();
  }, [merchantId, fetchAll]);

  async function analyzeRFQ(rfqId: string) {
    setAnalyzing(rfqId);
    try {
      const r = await apiFetch(`/api/bulk/rfqs/${rfqId}/analyze`, { method: "POST" });
      const d = await r.json();
      if (r.ok) setAnalysisData(prev => ({ ...prev, [rfqId]: d }));
    } catch { /* ignore */ }
    setAnalyzing(null);
  }

  async function sendAIQuote(rfqId: string) {
    const analysis = analysisData[rfqId];
    if (!analysis) return;
    setSendingQuote(rfqId);
    try {
      const opt = (analysis as { pricing_optimization?: { recommended_unit_price_minor?: number; recommended_discount_pct?: number } }).pricing_optimization;
      if (!opt?.recommended_unit_price_minor) return;
      const r = await apiFetch(`/api/bulk/rfqs/${rfqId}/quote`, {
        method: "POST",
        body: JSON.stringify({
          unit_price_minor: opt.recommended_unit_price_minor,
          message: `MerchantAgent AI quote: ₹${(opt.recommended_unit_price_minor / 100).toFixed(2)}/unit (${opt.recommended_discount_pct?.toFixed(1)}% discount)`,
        }),
      });
      if (r.ok) await fetchAll(merchantId);
    } catch { /* ignore */ }
    setSendingQuote(null);
  }

  async function rejectRFQ(negotiationId: string) {
    try {
      await apiFetch(`/api/bulk/negotiations/${negotiationId}/reject`, { method: "POST", body: "{}" });
      await fetchAll(merchantId);
    } catch { /* ignore */ }
  }

  const statusColor = (s: string) => {
    switch (s) {
      case "SUBMITTED": case "UNDER_REVIEW": return "text-blue-400 bg-blue-500/10 border-blue-500/20";
      case "QUOTED": case "NEGOTIATING": return "text-yellow-400 bg-yellow-500/10 border-yellow-500/20";
      case "ACCEPTED": case "CONVERTED_TO_ORDER": return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
      case "REJECTED": case "EXPIRED": return "text-red-400 bg-red-500/10 border-red-500/20";
      default: return "text-muted-foreground";
    }
  };

  const confidenceBadge = (c: string) => {
    return c === "HIGH" ? "text-emerald-400 border-emerald-400/30" : c === "MEDIUM" ? "text-yellow-400 border-yellow-400/30" : "text-orange-400 border-orange-400/30";
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <Boxes className="h-10 w-10 text-purple-400/50" />
          <p className="text-muted-foreground text-sm">Loading Bulk Commerce…</p>
        </div>
      </div>
    );
  }

  if (!merchantId) {
    return (
      <Card className="border-yellow-500/20 bg-yellow-500/5">
        <CardContent className="pt-6 flex items-center gap-3 text-yellow-400">
          <AlertTriangle className="h-5 w-5" />
          No merchant session found. Create a merchant and reload.
        </CardContent>
      </Card>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Boxes className="h-6 w-6 text-purple-400" /> Bulk Commerce
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            AI-powered bulk procurement — inventory analysis, autonomous negotiation, real revenue.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => fetchAll(merchantId)} className="gap-2">
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {/* Metrics Bar */}
      {analytics && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[
            { label: "Active RFQs", value: String(analytics.active_rfqs), icon: Package, cls: "text-blue-400" },
            { label: "Active Negotiations", value: String(analytics.active_negotiations), icon: Bot, cls: "text-yellow-400" },
            { label: "Bulk Orders", value: String(analytics.bulk.orders), icon: CheckCircle2, cls: "text-emerald-400" },
            { label: "Bulk Revenue", value: `₹${analytics.bulk.revenue_inr.toLocaleString()}`, icon: TrendingUp, cls: "text-purple-400" },
            { label: "Avg Bulk AOV", value: `₹${analytics.bulk.avg_order_value_inr.toLocaleString()}`, icon: BarChart3, cls: "text-cyan-400" },
          ].map(m => (
            <Card key={m.label} className="border-border/50">
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <m.icon className={`h-4 w-4 ${m.cls}`} />
                  <span className="text-xs text-muted-foreground">{m.label}</span>
                </div>
                <div className={`text-xl font-bold font-mono ${m.cls}`}>{m.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Tabs defaultValue="rfqs">
        <TabsList>
          <TabsTrigger value="rfqs">Incoming RFQs ({rfqs.filter(r => !["REJECTED","EXPIRED","CONVERTED_TO_ORDER"].includes(r.status)).length})</TabsTrigger>
          <TabsTrigger value="opportunities">Revenue Opportunities ({opportunities.length})</TabsTrigger>
          <TabsTrigger value="history">All RFQs ({rfqs.length})</TabsTrigger>
        </TabsList>

        {/* Incoming RFQs */}
        <TabsContent value="rfqs" className="space-y-4">
          {rfqs.filter(r => !["REJECTED","EXPIRED","CONVERTED_TO_ORDER"].includes(r.status)).length === 0 ? (
            <Card className="border-border/50">
              <CardContent className="pt-8 pb-8 text-center text-muted-foreground text-sm">
                No active RFQs. Bulk procurement requests from buyers will appear here.
              </CardContent>
            </Card>
          ) : rfqs.filter(r => !["REJECTED","EXPIRED","CONVERTED_TO_ORDER"].includes(r.status)).map(rfq => (
            <motion.div key={rfq.rfq_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card className={`border ${selectedRFQ === rfq.rfq_id ? "border-purple-500/40 bg-purple-500/5" : "border-border/50"}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Package className="h-4 w-4 text-purple-400" />
                        {rfq.product_name}
                        <Badge variant="outline" className={`text-xs ${statusColor(rfq.status)}`}>{rfq.status}</Badge>
                      </CardTitle>
                      <CardDescription className="mt-1 font-mono text-xs">{rfq.rfq_id}</CardDescription>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-lg font-bold font-mono text-purple-400">×{rfq.requested_quantity}</div>
                      <div className="text-xs text-muted-foreground">ATP: {rfq.available_to_promise}</div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 space-y-3">
                  <div className="grid grid-cols-3 gap-3 text-xs">
                    <div><span className="text-muted-foreground">Base Price</span><br /><span className="font-mono font-semibold">₹{rfq.base_price_inr.toFixed(2)}</span></div>
                    <div><span className="text-muted-foreground">Category</span><br /><span>{rfq.category}</span></div>
                    <div><span className="text-muted-foreground">Created</span><br /><span>{new Date(rfq.created_at).toLocaleDateString()}</span></div>
                  </div>

                  {/* AI Analysis Result */}
                  {analysisData[rfq.rfq_id] && (
                    <div className="p-3 rounded-lg bg-yellow-500/5 border border-yellow-500/20 text-xs space-y-2">
                      <div className="font-semibold text-yellow-400 flex items-center gap-1">
                        <Bot className="h-3 w-3" /> MerchantAgent Analysis
                        <span className="ml-1 text-yellow-300/50">(HEURISTIC)</span>
                      </div>
                      <div className="grid grid-cols-4 gap-2">
                        {[
                          { label: "Recommended", value: `₹${(analysisData[rfq.rfq_id] as { pricing_optimization?: { recommended_unit_price_inr?: number } }).pricing_optimization?.recommended_unit_price_inr?.toFixed(2) || "—"}` },
                          { label: "Discount", value: `${(analysisData[rfq.rfq_id] as { pricing_optimization?: { recommended_discount_pct?: number } }).pricing_optimization?.recommended_discount_pct?.toFixed(1) || "—"}%` },
                          { label: "Acceptance P.", value: `${Math.round(((analysisData[rfq.rfq_id] as { pricing_optimization?: { recommended_acceptance_probability?: number } }).pricing_optimization?.recommended_acceptance_probability || 0) * 100)}%` },
                          { label: "ATP", value: String((analysisData[rfq.rfq_id] as { inventory_analysis?: { available_to_promise?: number } }).inventory_analysis?.available_to_promise || 0) },
                        ].map(m => (
                          <div key={m.label} className="p-2 rounded bg-black/20">
                            <div className="text-muted-foreground">{m.label}</div>
                            <div className="font-mono font-bold text-yellow-300">{m.value}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Accepted deal info */}
                  {rfq.neg_status === "ACCEPTED" && rfq.final_unit_price_inr && (
                    <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs">
                      <div className="font-semibold text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Deal Accepted
                      </div>
                      <div className="mt-1 font-mono">₹{rfq.final_unit_price_inr.toFixed(2)}/unit · Total ₹{rfq.final_total_inr?.toFixed(2)}</div>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2">
                    {!analysisData[rfq.rfq_id] && rfq.status === "SUBMITTED" && (
                      <Button size="sm" variant="outline" className="gap-1 border-yellow-500/30 text-yellow-400"
                        onClick={() => analyzeRFQ(rfq.rfq_id)}
                        disabled={analyzing === rfq.rfq_id}
                      >
                        {analyzing === rfq.rfq_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
                        AI Analyze
                      </Button>
                    )}
                    {analysisData[rfq.rfq_id] && rfq.status === "SUBMITTED" && (
                      <Button size="sm" variant="default" className="gap-1 bg-purple-600 hover:bg-purple-500"
                        onClick={() => sendAIQuote(rfq.rfq_id)}
                        disabled={sendingQuote === rfq.rfq_id}
                      >
                        {sendingQuote === rfq.rfq_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                        Send AI Quote
                      </Button>
                    )}
                    {rfq.negotiation_id && !["ACCEPTED","CONVERTED_TO_ORDER"].includes(rfq.neg_status || "") && (
                      <Button size="sm" variant="outline" className="gap-1 border-red-500/30 text-red-400"
                        onClick={() => rejectRFQ(rfq.negotiation_id!)}
                      >
                        <Ban className="h-3 w-3" /> Reject
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" className="gap-1 ml-auto"
                      onClick={() => setSelectedRFQ(selectedRFQ === rfq.rfq_id ? null : rfq.rfq_id)}
                    >
                      Details <ChevronRight className={`h-3 w-3 transition-transform ${selectedRFQ === rfq.rfq_id ? "rotate-90" : ""}`} />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </TabsContent>

        {/* Revenue Opportunities */}
        <TabsContent value="opportunities" className="space-y-4">
          <div className="text-xs text-muted-foreground flex items-center gap-2 p-3 rounded-lg bg-muted/20 border border-border/30">
            <AlertTriangle className="h-3 w-3 text-yellow-400 shrink-0" />
            <span>All estimates are <strong>HEURISTIC</strong> — based on inventory signals, not historical bulk data. Use as guidance only.</span>
          </div>
          {opportunities.length === 0 ? (
            <Card className="border-border/50">
              <CardContent className="pt-8 pb-8 text-center text-muted-foreground text-sm">
                No bulk opportunities detected. Add products with bulk quantities to discover opportunities.
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {opportunities.map(opp => (
                <motion.div key={opp.product_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <Card className="border-border/50 hover:border-purple-500/30 transition-colors">
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="text-base">{opp.product_name}</CardTitle>
                          <CardDescription>{opp.category}</CardDescription>
                        </div>
                        <Badge variant="outline" className={`text-xs ${confidenceBadge(opp.confidence)}`}>
                          {opp.confidence}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="grid grid-cols-2 gap-3 text-xs">
                        <div>
                          <div className="text-muted-foreground">Excess Inventory</div>
                          <div className="font-mono font-bold text-yellow-400">{opp.estimated_excess} units</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">Suggested Range</div>
                          <div className="font-mono font-bold text-purple-400">{opp.suggested_bulk_range.min}–{opp.suggested_bulk_range.max} units</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">Opening Price</div>
                          <div className="font-mono font-bold text-blue-400">₹{opp.recommended_opening_price_inr.toFixed(2)}/u</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">Est. Revenue</div>
                          <div className="font-mono font-bold text-emerald-400">
                            ₹{opp.estimated_revenue_range_inr.low.toLocaleString()}–{opp.estimated_revenue_range_inr.high.toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          )}
        </TabsContent>

        {/* All RFQs History */}
        <TabsContent value="history">
          <Card className="border-border/50">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Product</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Final Price</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rfqs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground py-8">No RFQ history yet.</TableCell>
                  </TableRow>
                ) : rfqs.map(rfq => (
                  <TableRow key={rfq.rfq_id}>
                    <TableCell className="font-medium">{rfq.product_name}</TableCell>
                    <TableCell className="text-right font-mono">{rfq.requested_quantity}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-xs ${statusColor(rfq.status)}`}>{rfq.status}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {rfq.final_unit_price_inr ? `₹${rfq.final_unit_price_inr.toFixed(2)}/u` : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(rfq.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
