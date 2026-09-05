"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "../lib/api";
import type { CheckoutProduct } from "./commerce";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { MessageSquare, TrendingUp, Tag, PlusCircle, CheckCircle2, Loader2 } from "lucide-react";

type Negotiation = {
  id: string;
  status: string;
  decision: string;
  reason_code: string;
  buyer_ceiling_minor: number;
  starting_price_minor: number;
  fallback_price_minor?: number;
  current_round: number;
  max_rounds: number;
  final_agreed_price_minor?: number;
};

type GrowthOffer = {
  offered_product_id: string;
  name: string;
  price_minor: number;
  currency: string;
  relationship_type: string;
};

type CampaignOffer = {
  offer_id: string;
  campaign_id: string;
  name: string;
  objective: string;
  discount_minor: number;
  expires_at: string;
  source: string;
  eligibility: Record<string, unknown>;
};

async function json(path: string, init: RequestInit) {
  const response = await apiFetch(path, init);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

// ─── NegotiationCard ────────────────────────────────────────────────────────

export function NegotiationCard({ mandateId, product, cartId }: { mandateId?: string; product?: CheckoutProduct; cartId?: string }) {
  const [session, setSession] = useState<Negotiation | null>(null);
  // Only kept for manual override fallback — AI fills this automatically
  const [amount, setAmount] = useState<number | "">("");
  const [log, setLog] = useState<string[]>(["Waiting for mandate…"]);
  const [finalPrice, setFinalPrice] = useState<number | null>(null);
  const [done, setDone] = useState(false);

  function addLog(msg: string) {
    setLog(prev => [...prev, msg]);
  }

  // ── Autonomous negotiation engine ──────────────────────────────────────────
  useEffect(() => {
    if (!mandateId || !product || !cartId) return;
    runAutonomousNegotiation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mandateId, product?.product_id, cartId]);

  async function runAutonomousNegotiation() {
    if (!mandateId || !product || !cartId) return;

    try {
      // Step 1: Start negotiation session
      addLog("🤖 Starting negotiation session…");
      const session: Negotiation = await json("/api/negotiations", {
        method: "POST",
        body: JSON.stringify({ mandate_id: mandateId, product_id: product.product_id }),
      });
      setSession(session);

      const ceiling = session.buyer_ceiling_minor;      // buyer's max (from mandate)
      const asking  = session.starting_price_minor;     // merchant's asking price
      addLog(`📊 Merchant asking: ₹${(asking / 100).toLocaleString("en-IN")} | Your ceiling: ₹${(ceiling / 100).toLocaleString("en-IN")}`);

      // If already accepted (merchant floor ≤ ceiling), no rounds needed
      if (session.status !== "OPEN") {
        await applyResult(session);
        return;
      }

      // Step 2: Run negotiation rounds with smart math strategy
      // Strategy: open at midpoint, each rejection moves 60% of remaining gap toward asking price
      let currentSession = session;
      let offer = Math.min(Math.round(asking * 0.8), ceiling);   // Round 1: start with a 20% discount request
      const maxRounds = session.max_rounds;

      for (let round = 1; round <= maxRounds; round++) {
        // Clamp offer: never below merchant floor logic, never above ceiling
        offer = Math.min(offer, ceiling);
        setAmount(offer / 100);
        addLog(`🔄 Round ${round}/${maxRounds}: Offering ₹${(offer / 100).toLocaleString("en-IN")}`);

        const step: Negotiation = await json(`/api/negotiations/${currentSession.id}/step`, {
          method: "POST",
          body: JSON.stringify({
            actor: "BUYER_AGENT",
            proposed_amount_minor: offer,
            text: `AI buyer autonomous offer — round ${round}`,
          }),
        });
        setSession(step);
        currentSession = step;

        if (step.status === "ACCEPTED") {
          const agreed = step.final_agreed_price_minor ?? offer;
          addLog(`✅ ACCEPTED at ₹${(agreed / 100).toLocaleString("en-IN")}`);
          await applyResult(step, agreed);
          return;
        }

        if (step.status === "FALLBACK") {
          const fallback = step.fallback_price_minor ?? asking;
          addLog(`⚡ FALLBACK price: ₹${(fallback / 100).toLocaleString("en-IN")}`);
          await applyResult(step, fallback);
          return;
        }

        if (step.status === "REJECTED" || step.decision === "REJECTED") {
          addLog(`↩ Round ${round} rejected — adjusting offer…`);
          // Move 60% of gap between current offer and asking price toward asking
          const gap = asking - offer;
          offer = Math.round(offer + gap * 0.6);
        }
      }

      // All rounds exhausted — apply whatever final state we have
      addLog("⚠️ Max rounds reached — applying best available price.");
      await applyResult(currentSession);

    } catch (err) {
      addLog(`❌ ${err instanceof Error ? err.message : "Negotiation failed"}`);
      setDone(true);
    }
  }

  async function applyResult(s: Negotiation, agreedMinor?: number) {
    if (!cartId) return;
    const price = agreedMinor ?? s.final_agreed_price_minor ?? s.starting_price_minor;
    try {
      addLog("🔒 Applying price & re-verifying with SecurityKernel…");
      const data = await json(`/api/negotiations/${s.id}/apply-to-cart`, {
        method: "POST",
        body: JSON.stringify({ cart_id: cartId }),
      });
      setFinalPrice(price);
      addLog(`🛡 SecurityKernel: ${data.security_recommit.outcome}`);
    } catch (err) {
      addLog(`❌ Apply failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setDone(true);
    }
  }
  // ── End autonomous engine ──────────────────────────────────────────────────

  return (
    <Card className="border-border/50 bg-card h-full flex flex-col">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/20">
        <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
          <CardTitle className="text-sm font-semibold flex items-center gap-2 text-cyan-400 min-w-0 truncate">
            <MessageSquare className="w-4 h-4 shrink-0" /> Price conversation
          </CardTitle>
          <Badge className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20 shrink-0">NEGOTIATION</Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-4 flex-1 flex flex-col space-y-3 overflow-y-auto">
        {/* Live log */}
        <div className="rounded-lg bg-black/40 border border-cyan-500/10 p-3 space-y-1 min-h-[100px]">
          {log.map((line, i) => (
            <p key={i} className="text-xs font-mono text-cyan-300/80">{line}</p>
          ))}
          {!done && (
            <div className="flex items-center gap-1.5 pt-1">
              <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />
              <span className="text-[10px] text-cyan-400/60">negotiating…</span>
            </div>
          )}
        </div>

        {/* Final result panel */}
        {done && finalPrice !== null && (
          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <p className="text-xs text-emerald-400/70 uppercase tracking-wider mb-0.5">Final Agreed Price</p>
            <p className="text-2xl font-bold text-emerald-400">
              ₹{(finalPrice / 100).toLocaleString("en-IN")}
            </p>
            <p className="text-[10px] text-emerald-400/50 mt-1">Applied to cart & verified by SecurityKernel</p>
          </div>
        )}

        {/* Session info */}
        {session && (
          <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
            <span>Round {session.current_round}/{session.max_rounds}</span>
            <Badge variant="outline" className={session.status === "OPEN" ? "border-amber-500/50 text-amber-500" : "border-emerald-500/50 text-emerald-500"}>
              {session.status}
            </Badge>
          </div>
        )}
      </CardContent>
    </Card>
  );
}


// ─── GrowthCard ──────────────────────────────────────────────────────────────

export function GrowthCard({ mandateId, product, cartId }: { mandateId?: string; product?: CheckoutProduct; cartId?: string }) {
  const [offers, setOffers] = useState<GrowthOffer[]>([]);
  const [eventIds, setEventIds] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [statusText, setStatusText] = useState("");

  // AUTONOMOUS FLOW: auto-load as soon as cartId becomes available
  useEffect(() => {
    if (!mandateId || !product || !cartId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartId]);

  async function load() {
    if (!mandateId || !product || !cartId) return;
    setStatus("loading");
    setStatusText("");
    try {
      const data = await json("/api/growth/recommendations", { method: "POST", body: JSON.stringify({ mandate_id: mandateId, source_product_id: product.product_id, cart_id: cartId }) });
      setOffers([...data.upsells, ...data.cross_sells]);
      setEventIds(data.event_ids);
      if (data.upsells.length === 0 && data.cross_sells.length === 0) {
        setStatusText("No eligible add-ons for this product.");
      } else {
        setStatusText("Eligible add-ons found — explicit acceptance required.");
      }
      setStatus("done");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Recommendations failed");
      setStatus("done");
    }
  }

  async function accept(offer: GrowthOffer) {
    const eventType = offer.relationship_type === "UPSELL" ? "upsell" : "cross_sell";
    try {
      const data = await json(`/api/growth/${eventType}/${eventIds[offer.offered_product_id]}/accept`, { method: "POST", body: JSON.stringify({ cart_id: cartId, confirmed: true }) });
      setStatusText(`Accepted ${offer.name}. SecurityKernel: ${data.security_recommit.outcome}`);
      setOffers(current => current.filter(item => item.offered_product_id !== offer.offered_product_id));
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Acceptance failed");
    }
  }

  return (
    <Card className="border-border/50 bg-card h-full flex flex-col">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/20">
        <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
          <CardTitle className="text-sm font-semibold flex items-center gap-2 text-orange-400 min-w-0 truncate">
            <TrendingUp className="w-4 h-4 shrink-0" /> Eligible add-ons
          </CardTitle>
          <Badge className="bg-orange-500/10 text-orange-400 border-orange-500/20 shrink-0">GROWTH</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-4 flex-1 flex flex-col space-y-4 overflow-y-auto">
        {status === "loading" && (
          <div className="flex items-center justify-center gap-2 py-6 text-orange-400 text-xs">
            <Loader2 className="w-4 h-4 animate-spin" /> Fetching mandate-safe offers…
          </div>
        )}

        {status === "done" && offers.length > 0 && (
          <div className="space-y-3">
            {offers.map(offer => (
              <div className="p-3 rounded-lg border border-border/50 bg-muted/20" key={offer.offered_product_id}>
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h4 className="font-medium text-sm">{offer.name}</h4>
                    <p className="text-xs text-muted-foreground mt-0.5">{offer.currency} {(offer.price_minor / 100).toLocaleString("en-IN")}</p>
                  </div>
                  <Badge variant="outline" className="text-[10px] uppercase bg-background">{offer.relationship_type}</Badge>
                </div>
                <Button size="sm" variant="secondary" className="w-full h-8 text-xs bg-muted/50 hover:bg-muted" onClick={() => accept(offer)}>
                  <PlusCircle className="w-3 h-3 mr-1" /> Add & re-verify
                </Button>
              </div>
            ))}
          </div>
        )}

        {(status === "idle" || (status === "done" && offers.length === 0)) && (
          <p className="text-xs text-muted-foreground text-center py-4">
            {status === "idle" ? "Waiting for cart…" : statusText || "No eligible add-ons for this product."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ─── CampaignCard ────────────────────────────────────────────────────────────

export function CampaignCard({ cartId }: { cartId?: string }) {
  const [offers, setOffers] = useState<CampaignOffer[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [statusText, setStatusText] = useState("");

  // AUTONOMOUS FLOW: auto-load AND auto-apply as soon as cartId becomes available
  useEffect(() => {
    if (!cartId) return;
    autoLoadAndApply();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartId]);

  async function autoLoadAndApply() {
    if (!cartId) return;
    setStatus("loading");
    setStatusText("");
    try {
      const data: CampaignOffer[] = await json("/api/campaign-offers/eligible", { method: "POST", body: JSON.stringify({ cart_id: cartId }) });
      if (!data.length) {
        setStatusText("No discount available on this product.");
        setStatus("done");
        return;
      }
      // Autonomously apply the best (first) campaign
      const best = data[0];
      try {
        const applied = await json(`/api/campaign-offers/${best.offer_id}/apply`, { method: "POST", body: JSON.stringify({ cart_id: cartId }) });
        setStatusText(`✓ Campaign applied: Save INR ${(best.discount_minor / 100).toLocaleString("en-IN")}. SecurityKernel: ${applied.security_recommit.outcome}`);
        setOffers([]);
      } catch {
        // If auto-apply fails, show remaining offers for manual selection
        setOffers(data);
        setStatusText("Auto-apply failed — select offer manually.");
      }
      setStatus("done");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Offer lookup failed");
      setStatus("done");
    }
  }

  async function apply(offer: CampaignOffer) {
    try {
      const data = await json(`/api/campaign-offers/${offer.offer_id}/apply`, { method: "POST", body: JSON.stringify({ cart_id: cartId }) });
      setStatusText(`INR ${(offer.discount_minor / 100).toLocaleString("en-IN")} applied. Unified SecurityKernel: ${data.security_recommit.outcome}`);
      setOffers([]);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Campaign application failed");
    }
  }

  return (
    <Card className="border-border/50 bg-card h-full flex flex-col">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/20">
        <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
          <CardTitle className="text-sm font-semibold flex items-center gap-2 text-purple-400 min-w-0 truncate">
            <Tag className="w-4 h-4 shrink-0" /> Campaign offers
          </CardTitle>
          <Badge className="bg-purple-500/10 text-purple-400 border-purple-500/20 shrink-0">CAMPAIGN</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-4 flex-1 flex flex-col space-y-4 overflow-y-auto">
        {status === "loading" && (
          <div className="flex items-center justify-center gap-2 py-6 text-purple-400 text-xs">
            <Loader2 className="w-4 h-4 animate-spin" /> Fetching & auto-applying campaigns…
          </div>
        )}

        {status === "done" && offers.length > 0 && (
          <div className="space-y-3">
            {offers.map(offer => (
              <div className="p-3 rounded-lg border border-purple-500/20 bg-purple-500/5" key={offer.offer_id}>
                <h4 className="font-medium text-sm text-purple-300">{offer.name}</h4>
                <p className="text-xs text-muted-foreground mt-1 mb-2">{offer.objective}</p>
                <div className="flex items-center gap-2 text-xs mb-3">
                  <span className="font-semibold text-emerald-400">Save INR {(offer.discount_minor / 100).toLocaleString("en-IN")}</span>
                </div>
                <Button size="sm" className="w-full h-8 text-xs bg-purple-600 hover:bg-purple-700 text-white" onClick={() => apply(offer)}>
                  <CheckCircle2 className="w-3 h-3 mr-1" /> Apply verified offer
                </Button>
                <p className="text-[9px] text-muted-foreground/60 text-center mt-2 uppercase tracking-wider">Source: {offer.source}</p>
              </div>
            ))}
          </div>
        )}

        {(status === "idle" || (status === "done" && offers.length === 0)) && (
          <p className="text-xs text-muted-foreground text-center py-4">
            {status === "idle" ? "Waiting for cart…" : statusText || "No campaigns available."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
