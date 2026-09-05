"use client";

import { FormEvent, useState, useEffect, useCallback } from "react";
import { apiFetch } from "../lib/api";
import { motion, AnimatePresence } from "framer-motion";
import {
  Package, ShieldCheck, Zap, TrendingDown, CheckCircle2, XCircle,
  RotateCcw, ArrowRight, Clock, AlertTriangle, Loader2, Bot, Store
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

type RFQStatus =
  | "IDLE" | "CREATING" | "CREATED" | "ANALYZING" | "QUOTED"
  | "NEGOTIATING" | "ACCEPTED" | "REJECTED" | "ERROR";

type NegEvent = {
  sequence: number;
  actor: "BUYER_AGENT" | "MERCHANT_AGENT" | "SYSTEM";
  offer_type: string;
  quantity?: number;
  unit_price_minor?: number;
  total_value_minor?: number;
  message?: string;
  created_at?: string;
};

type FinalDeal = {
  unit_price_inr: number;
  quantity: number;
  total_inr: number;
  total_minor: number;
};

interface BulkProcurementPanelProps {
  initialProductId?: string;
  initialMerchantId?: string;
  initialProductName?: string;
  initialMerchantName?: string;
}

export default function BulkProcurementPanel({
  initialProductId,
  initialMerchantId,
  initialProductName,
  initialMerchantName,
}: BulkProcurementPanelProps = {}) {
  const [rfqId, setRfqId] = useState("");
  const [negotiationId, setNegotiationId] = useState("");
  const [status, setStatus] = useState<RFQStatus>("IDLE");
  const [events, setEvents] = useState<NegEvent[]>([]);
  const [finalDeal, setFinalDeal] = useState<FinalDeal | null>(null);
  const [reservation, setReservation] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [analysisData, setAnalysisData] = useState<Record<string, unknown> | null>(null);

  // Form values
  const [productId, setProductId] = useState(initialProductId || "");
  const [merchantId, setMerchantId] = useState(initialMerchantId || "");
  const [productName, setProductName] = useState(initialProductName || "");
  const [merchantName, setMerchantName] = useState(initialMerchantName || "");
  const [quantity, setQuantity] = useState("100");
  const [maxBudget, setMaxBudget] = useState(""); // private — stored locally, sent to backend as private field
  const [targetPrice, setTargetPrice] = useState(""); // private — buyer only
  const [deliveryMode, setDeliveryMode] = useState("SINGLE");
  const [allowSubs, setAllowSubs] = useState(false);
  const [negotiationEnabled, setNegotiationEnabled] = useState(true);

  useEffect(() => {
    if (initialProductId) setProductId(initialProductId);
    if (initialMerchantId) setMerchantId(initialMerchantId);
    if (initialProductName) setProductName(initialProductName);
    if (initialMerchantName) setMerchantName(initialMerchantName);
  }, [initialProductId, initialMerchantId, initialProductName, initialMerchantName]);

  const pollNegotiation = useCallback(async (negId: string) => {
    try {
      const r = await apiFetch(`/api/bulk/rfqs/${rfqId}`);
      if (!r.ok) return;
      const d = await r.json();
      const evts: NegEvent[] = d.events || [];
      setEvents(evts);
      const neg = d.negotiation;
      if (neg?.status === "ACCEPTED") {
        setStatus("ACCEPTED");
      } else if (neg?.status === "REJECTED") {
        setStatus("REJECTED");
      } else if (evts.length > 0) {
        setStatus("NEGOTIATING");
      }
    } catch { /* ignore poll errors */ }
  }, [rfqId]);

  useEffect(() => {
    if (status === "NEGOTIATING" && rfqId) {
      const interval = setInterval(() => pollNegotiation(negotiationId), 3000);
      return () => clearInterval(interval);
    }
  }, [status, rfqId, negotiationId, pollNegotiation]);

  async function createRFQ(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setStatus("CREATING");
    setEvents([]);
    setFinalDeal(null);
    setReservation(null);

    try {
      const body: Record<string, unknown> = {
        product_id: productId.trim(),
        merchant_id: merchantId.trim(),
        requested_quantity: parseInt(quantity),
        delivery_mode: deliveryMode,
        allow_substitutes: allowSubs,
        negotiation_enabled: negotiationEnabled,
      };
      // Private buyer constraints — sent to backend, stored server-side, never returned to merchant
      if (maxBudget) body.private_max_budget_minor = Math.round(parseFloat(maxBudget) * 100);
      if (targetPrice) body.private_target_unit_price_minor = Math.round(parseFloat(targetPrice) * 100);

      const r = await apiFetch("/api/bulk/rfqs", { method: "POST", body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "RFQ creation failed");

      setRfqId(d.rfq_id);
      setStatus("CREATED");

      // Immediately analyze (triggers MerchantAgent pricing)
      setStatus("ANALYZING");
      const analyzeR = await apiFetch(`/api/bulk/rfqs/${d.rfq_id}/analyze`, { method: "POST" });
      const analyzeD = await analyzeR.json();
      if (!analyzeR.ok) throw new Error(analyzeD.detail || "Analysis failed");
      setAnalysisData(analyzeD);

      // Auto-send AI quote
      const opt = (analyzeD as { pricing_optimization?: { recommended_unit_price_minor?: number; recommended_discount_pct?: number } }).pricing_optimization;
      if (opt?.recommended_unit_price_minor) {
        const quoteR = await apiFetch(`/api/bulk/rfqs/${d.rfq_id}/quote`, {
          method: "POST",
          body: JSON.stringify({
            unit_price_minor: opt.recommended_unit_price_minor,
            message: `MerchantAgent opens at ₹${(opt.recommended_unit_price_minor / 100).toFixed(2)}/unit (${opt.recommended_discount_pct?.toFixed(1)}% off list price)`,
          }),
        });
        const quoteD = await quoteR.json();
        if (!quoteR.ok) throw new Error(quoteD.detail || "Quoting failed");

        if (quoteD.negotiation_id) setNegotiationId(quoteD.negotiation_id);

        if (quoteD.status === "ACCEPTED") {
          // Auto-accept happened on backend — call accept endpoint to get reservation
          const acceptR = await apiFetch(`/api/bulk/negotiations/${quoteD.negotiation_id}/accept`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          const acceptD = await acceptR.json();
          if (acceptR.ok) {
            setFinalDeal(acceptD.final_deal);
            setReservation(acceptD.reservation);
            setStatus("ACCEPTED");
          }
        } else {
          setStatus("NEGOTIATING");
          // Re-fetch events immediately
          await pollNegotiation(quoteD.negotiation_id || "");
        }
      } else {
        setStatus("QUOTED");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setStatus("ERROR");
    }
  }

  async function manualAccept() {
    if (!negotiationId) return;
    try {
      const r = await apiFetch(`/api/bulk/negotiations/${negotiationId}/accept`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail);
      setFinalDeal(d.final_deal);
      setReservation(d.reservation);
      setStatus("ACCEPTED");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Accept failed");
    }
  }

  async function manualReject() {
    if (!negotiationId) return;
    try {
      await apiFetch(`/api/bulk/negotiations/${negotiationId}/reject`, { method: "POST", body: "{}" });
      setStatus("REJECTED");
    } catch { /* ignore */ }
  }

  function reset() {
    setRfqId(""); setNegotiationId(""); setStatus("IDLE");
    setEvents([]); setFinalDeal(null); setReservation(null);
    setError(""); setAnalysisData(null);
  }

  const actorColor = (actor: string) => {
    switch (actor) {
      case "BUYER_AGENT": return "text-blue-400 bg-blue-500/10 border-blue-500/20";
      case "MERCHANT_AGENT": return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
      default: return "text-muted-foreground bg-muted/10 border-border";
    }
  };

  const statusBadge = () => {
    const map: Record<string, { label: string; cls: string }> = {
      IDLE: { label: "Idle", cls: "text-muted-foreground" },
      CREATING: { label: "Creating RFQ…", cls: "text-blue-400" },
      CREATED: { label: "RFQ Created", cls: "text-blue-400" },
      ANALYZING: { label: "AI Analyzing…", cls: "text-yellow-400 animate-pulse" },
      QUOTED: { label: "Quoted", cls: "text-purple-400" },
      NEGOTIATING: { label: "Negotiating", cls: "text-orange-400 animate-pulse" },
      ACCEPTED: { label: "Deal Accepted ✓", cls: "text-emerald-400" },
      REJECTED: { label: "Rejected", cls: "text-red-400" },
      ERROR: { label: "Error", cls: "text-red-400" },
    };
    const s = map[status] || map.IDLE;
    return <span className={`text-xs font-mono font-semibold ${s.cls}`}>{s.label}</span>;
  };

  return (
    <div className="space-y-6">
      {/* RFQ Form */}
      <Card className="border-purple-500/20 bg-purple-500/5">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-xl flex items-center gap-2 text-purple-400">
              <Package className="h-5 w-5" /> Bulk Procurement Request (RFQ)
            </CardTitle>
            {statusBadge()}
          </div>
          <CardDescription>
            AI Buyer sends a Request for Quotation. MerchantAgent analyzes inventory + pricing.
            BuyerAgent negotiates autonomously. Private budget stays on buyer side only.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {(productName || merchantName) && (
            <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <Package className="h-4 w-4 text-purple-400 shrink-0" />
                <span>
                  Procuring: <strong className="text-foreground">{productName || "Selected Item"}</strong> from <strong className="text-purple-400">{merchantName || "Selected Merchant"}</strong>
                </span>
              </div>
              <button
                type="button"
                onClick={() => { setProductName(""); setMerchantName(""); setProductId(""); setMerchantId(""); }}
                className="text-muted-foreground hover:text-foreground text-xs underline"
              >
                Clear
              </button>
            </div>
          )}
          <form onSubmit={createRFQ} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="pid">Product ID</Label>
              <Input id="pid" placeholder="UUID of product" value={productId} onChange={e => setProductId(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mid">Merchant ID</Label>
              <Input id="mid" placeholder="UUID of merchant" value={merchantId} onChange={e => setMerchantId(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="qty">Requested Quantity</Label>
              <Input id="qty" type="number" min="1" value={quantity} onChange={e => setQuantity(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="del">Delivery Mode</Label>
              <select id="del" className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm" value={deliveryMode} onChange={e => setDeliveryMode(e.target.value)}>
                <option value="SINGLE">Single Delivery</option>
                <option value="STAGGERED">Staggered</option>
                <option value="ON_DEMAND">On Demand</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget" className="flex items-center gap-1">
                Max Budget (₹) <Badge variant="outline" className="text-xs text-yellow-400 border-yellow-400/30">🔒 Private</Badge>
              </Label>
              <Input id="budget" type="number" placeholder="Optional — stays on buyer side" value={maxBudget} onChange={e => setMaxBudget(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="target" className="flex items-center gap-1">
                Target Unit Price (₹) <Badge variant="outline" className="text-xs text-yellow-400 border-yellow-400/30">🔒 Private</Badge>
              </Label>
              <Input id="target" type="number" placeholder="Optional — never shown to merchant" value={targetPrice} onChange={e => setTargetPrice(e.target.value)} />
            </div>
            <div className="flex items-center gap-6 md:col-span-2">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={negotiationEnabled} onChange={e => setNegotiationEnabled(e.target.checked)} className="rounded" />
                Enable Agent Negotiation
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={allowSubs} onChange={e => setAllowSubs(e.target.checked)} className="rounded" />
                Allow Substitutes
              </label>
            </div>
            <div className="md:col-span-2 flex gap-3">
              <Button type="submit" className="flex-1" disabled={status !== "IDLE" && status !== "ERROR"}>
                {status === "CREATING" || status === "ANALYZING" ? (
                  <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Processing…</>
                ) : (
                  <><Zap className="h-4 w-4 mr-2" /> Launch Bulk RFQ</>
                )}
              </Button>
              {status !== "IDLE" && (
                <Button type="button" variant="outline" onClick={reset}>
                  <RotateCcw className="h-4 w-4" />
                </Button>
              )}
            </div>
          </form>

          {error && (
            <div className="mt-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" /> {error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pricing Analysis */}
      {analysisData && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="border-yellow-500/20 bg-yellow-500/5">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2 text-yellow-400">
                <TrendingDown className="h-5 w-5" /> MerchantAgent Pricing Analysis
              </CardTitle>
              <CardDescription className="text-yellow-300/70">
                HEURISTIC — deterministic model, not ML-trained. Merchant floor price not exposed to buyer.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                {[
                  {
                    label: "Recommended Price",
                    value: `₹${(analysisData as { pricing_optimization?: { recommended_unit_price_inr?: number } }).pricing_optimization?.recommended_unit_price_inr?.toFixed(2) || "—"}`,
                    cls: "text-emerald-400"
                  },
                  {
                    label: "Discount",
                    value: `${(analysisData as { pricing_optimization?: { recommended_discount_pct?: number } }).pricing_optimization?.recommended_discount_pct?.toFixed(1) || "—"}%`,
                    cls: "text-yellow-400"
                  },
                  {
                    label: "Acceptance P.",
                    value: `${Math.round(((analysisData as { pricing_optimization?: { recommended_acceptance_probability?: number } }).pricing_optimization?.recommended_acceptance_probability || 0) * 100)}%`,
                    cls: "text-blue-400"
                  },
                  {
                    label: "ATP",
                    value: String((analysisData as { inventory_analysis?: { available_to_promise?: number } }).inventory_analysis?.available_to_promise || 0),
                    cls: "text-purple-400"
                  },
                ].map((m) => (
                  <div key={m.label} className="p-3 rounded-lg bg-black/20 border border-border/30">
                    <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
                    <div className={`text-lg font-bold font-mono ${m.cls}`}>{m.value}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Negotiation Timeline */}
      {events.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="border-border/50">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Bot className="h-5 w-5 text-primary" /> Agent Negotiation Timeline
              </CardTitle>
              <CardDescription>Real-time offer/counter-offer log. Buyer constraints are private.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <AnimatePresence>
                  {events.map((ev) => (
                    <motion.div
                      key={ev.sequence}
                      initial={{ opacity: 0, x: ev.actor === "BUYER_AGENT" ? -20 : 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      className={`flex ${ev.actor === "BUYER_AGENT" ? "justify-start" : "justify-end"}`}
                    >
                      <div className={`max-w-[75%] rounded-lg border p-3 ${actorColor(ev.actor)}`}>
                        <div className="flex items-center gap-2 mb-1">
                          {ev.actor === "BUYER_AGENT" ? <Bot className="h-3 w-3" /> : <Store className="h-3 w-3" />}
                          <span className="text-xs font-semibold">{ev.actor}</span>
                          <Badge variant="outline" className="text-xs border-0 bg-transparent px-1">{ev.offer_type}</Badge>
                        </div>
                        {ev.unit_price_minor && (
                          <div className="font-mono text-sm font-bold">
                            ₹{(ev.unit_price_minor / 100).toFixed(2)}/unit × {ev.quantity} = ₹{((ev.total_value_minor || 0) / 100).toFixed(2)}
                          </div>
                        )}
                        {ev.message && <div className="text-xs opacity-70 mt-1">{ev.message}</div>}
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>

              {status === "NEGOTIATING" && (
                <div className="flex gap-3 mt-4">
                  <Button variant="default" size="sm" className="flex-1 bg-emerald-600 hover:bg-emerald-500" onClick={manualAccept}>
                    <CheckCircle2 className="h-4 w-4 mr-2" /> Accept Deal
                  </Button>
                  <Button variant="outline" size="sm" className="flex-1 border-red-500/30 text-red-400" onClick={manualReject}>
                    <XCircle className="h-4 w-4 mr-2" /> Reject
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Deal Accepted → Proceed to Payment */}
      {status === "ACCEPTED" && finalDeal && (
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
          <Card className="border-emerald-500/30 bg-emerald-500/5">
            <CardHeader>
              <CardTitle className="text-xl flex items-center gap-2 text-emerald-400">
                <CheckCircle2 className="h-6 w-6" /> Bulk Deal Confirmed
              </CardTitle>
              <CardDescription className="text-emerald-300/70">
                Inventory reserved · Payment will use existing Razorpay Test Mode flow
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="p-3 rounded-lg bg-black/20 border border-emerald-500/20 text-center">
                  <div className="text-xs text-muted-foreground">Unit Price</div>
                  <div className="text-xl font-bold text-emerald-400 font-mono">₹{finalDeal.unit_price_inr?.toFixed(2)}</div>
                </div>
                <div className="p-3 rounded-lg bg-black/20 border border-emerald-500/20 text-center">
                  <div className="text-xs text-muted-foreground">Quantity</div>
                  <div className="text-xl font-bold text-emerald-400 font-mono">{finalDeal.quantity}</div>
                </div>
                <div className="p-3 rounded-lg bg-black/20 border border-emerald-500/20 text-center">
                  <div className="text-xs text-muted-foreground">Total</div>
                  <div className="text-xl font-bold text-emerald-400 font-mono">₹{finalDeal.total_inr?.toFixed(2)}</div>
                </div>
              </div>
              {reservation && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3 text-yellow-400" />
                  <span>Reservation ID: <span className="font-mono text-yellow-400">{String((reservation as { reservation_id?: string }).reservation_id)}</span></span>
                  <span>· Expires in {String((reservation as { expires_in_minutes?: number }).expires_in_minutes)} min</span>
                </div>
              )}
              <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 text-sm text-blue-300 flex items-start gap-2">
                <ShieldCheck className="h-4 w-4 mt-0.5 shrink-0 text-blue-400" />
                <span>
                  Proceed to the <strong>checkout flow above</strong> using this product and merchant ID.
                  The bulk RFQ ID (<span className="font-mono">{rfqId}</span>) will be linked to the transaction for
                  proper revenue attribution (<strong>AGENT_NEGOTIATED_BULK</strong>).
                </span>
              </div>
              <div className="flex items-center gap-2 p-2 rounded bg-black/20 text-xs font-mono text-muted-foreground">
                <ArrowRight className="h-3 w-3" />
                RFQ: {rfqId}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {status === "REJECTED" && (
        <Card className="border-red-500/20 bg-red-500/5">
          <CardContent className="pt-6 flex items-center gap-3 text-red-400">
            <XCircle className="h-5 w-5" /> Bulk negotiation rejected. <Button variant="ghost" size="sm" onClick={reset}>Try Again</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
