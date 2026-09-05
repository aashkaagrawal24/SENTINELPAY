"use client";

import Script from "next/script";
import { FormEvent, useState } from "react";
import { CartCard, VerificationCard } from "@/components/commerce";
import { CampaignCard, GrowthCard, NegotiationCard } from "@/components/growth";
import { ProvenanceDrawer } from "@/components/provenance";
import { MarketIntelligence } from "@/components/market-intelligence";
import { apiFetch } from "@/lib/api";
import { motion } from "framer-motion";
import {
  Bot, Send, Play, ShieldAlert, ShoppingCart, MessageSquare,
  ArrowLeft, Store, Shield, Zap, Eye, CheckCircle2, Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

type Candidate = { product_id: string; merchant_id: string; name: string; current_price_minor: number; currency: string; why_matched: string[] };
type Intent = { max_budget_minor?: number; [key: string]: unknown };

export default function AIWorkspace() {
  const [thread, setThread] = useState("");
  const [intentId, setIntentId] = useState("");
  const [intent, setIntent] = useState<Intent | null>(null);
  const [mandate, setMandate] = useState<Record<string, unknown> | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [cartId, setCartId] = useState("");
  const [status, setStatus] = useState("Start a secured conversation to begin shopping with AI.");
  const [messages, setMessages] = useState<Array<{role: string; content: string}>>([]);
  const [loading, setLoading] = useState(false);
  const [agentSteps, setAgentSteps] = useState<Array<{step: string; status: string; time: string}>>([]);

  async function start() {
    setLoading(true);
    const r = await apiFetch("/api/conversations", { method: "POST", body: "{}" });
    const d = await r.json();
    setThread(d.id);
    setStatus("Conversation active — describe what you want to buy.");
    setAgentSteps(prev => [...prev, { step: "Session initialized", status: "DONE", time: new Date().toLocaleTimeString() }]);
    setLoading(false);
  }

  async function send(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const content = String(new FormData(e.currentTarget).get("message"));
    if (!content.trim()) return;
    setMessages(prev => [...prev, { role: "user", content }]);
    setLoading(true);
    setAgentSteps(prev => [...prev, { step: "Parsing intent...", status: "RUNNING", time: new Date().toLocaleTimeString() }]);

    const conversation = await apiFetch(`/api/conversations/${thread}/messages`, {
      method: "POST",
      body: JSON.stringify({ content })
    });
    const result = await conversation.json();
    setStatus(result.message || result.status);
    setMessages(prev => [...prev, { role: "assistant", content: result.message || result.status || "Intent parsed." }]);
    setIntent(result.parsed_intent || null);
    setCandidates(result.candidates || []);

    setAgentSteps(prev => {
      const updated = [...prev];
      updated[updated.length - 1] = { step: "Intent parsed", status: "DONE", time: new Date().toLocaleTimeString() };
      return updated;
    });

    if (result.parsed_intent) {
      if (result.intent_id) {
        setIntentId(result.intent_id);
      }
      setAgentSteps(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { step: `Found ${result.candidates?.length || 0} candidates`, status: "DONE", time: new Date().toLocaleTimeString() };
        return updated;
      });
    }
    setLoading(false);
    (e.target as HTMLFormElement).reset();
  }

  async function activate() {
    setLoading(true);
    setAgentSteps(prev => [...prev, { step: "Activating mandate...", status: "RUNNING", time: new Date().toLocaleTimeString() }]);
    const response = await apiFetch("/api/mandates", { method: "POST", body: JSON.stringify({ intent_id: intentId, confirmed: true }) });
    const data = await response.json();
    setMandate(data);
    setStatus(data.status === "ACTIVE" ? "Mandate ACTIVE — agent can now transact within bounds" : "Mandate activation failed");
    setAgentSteps(prev => {
      const updated = [...prev];
      updated[updated.length - 1] = { step: "Mandate activated", status: "DONE", time: new Date().toLocaleTimeString() };
      return updated;
    });
    setLoading(false);
  }

  async function buildCart() {
    const product = candidates[0];
    if (!product || !mandateId) return;
    setLoading(true);
    setAgentSteps(prev => [...prev, { step: "Building bounded cart...", status: "RUNNING", time: new Date().toLocaleTimeString() }]);
    const created = await apiFetch("/api/carts", { method: "POST", body: JSON.stringify({ merchant_id: product.merchant_id, mandate_id: mandateId }) });
    const cart = await created.json();
    if (!created.ok) {
      setStatus(cart.detail || "Cart creation failed");
      setLoading(false);
      return;
    }
    const added = await apiFetch(`/api/carts/${cart.id}/items`, { method: "POST", body: JSON.stringify({ product_id: product.product_id, quantity: 1 }) });
    if (!added.ok) {
      const error = await added.json();
      setStatus(error.detail || "Product could not be added");
      setLoading(false);
      return;
    }
    setCartId(cart.id);
    setStatus("Bounded cart ready — SecurityKernel will verify before payment");
    setAgentSteps(prev => {
      const updated = [...prev];
      updated[updated.length - 1] = { step: "Cart committed", status: "DONE", time: new Date().toLocaleTimeString() };
      return updated;
    });
    setLoading(false);
  }

  async function handleInstantList(info: { name: string; brand: string; category: string; price: number }) {
    setLoading(true);
    try {
      const merchantId = localStorage.getItem("sp_merchant_id") || "10000000-0000-0000-0000-000000000001";
      const sku = `DEMAND-${Date.now().toString().slice(-6)}`;
      const res = await apiFetch(`/api/merchants/${merchantId}/products`, {
        method: "POST",
        body: JSON.stringify({
          sku,
          name: info.name,
          brand: info.brand,
          category: info.category || "General",
          description: `On-demand listed ${info.name} with verified supply guarantee.`,
          base_price_minor: info.price * 100,
          variants: [{ variant_key: "default", name: "Default", attributes: { variant: "Standard" } }]
        })
      });
      const prod = await res.json();
      if (prod.id) {
        await apiFetch(`/api/merchants/${merchantId}/policies`, {
          method: "POST",
          body: JSON.stringify({
            scope: "PRODUCT",
            scope_reference: prod.id,
            base_price_minor: info.price * 100,
            minimum_sale_price_minor: Math.round(info.price * 0.9) * 100,
            maximum_discount_percent: 10,
            negotiation_enabled: true,
            max_negotiation_rounds: 3,
            upsell_enabled: true,
            cross_sell_enabled: true,
            valid_from: new Date().toISOString(),
            status: "ACTIVE"
          })
        }).catch(() => {});

        const catRes = await apiFetch("/api/agent/catalog/search", {
          method: "POST",
          body: JSON.stringify({ query: info.name })
        });
        const cat = await catRes.json();
        if (Array.isArray(cat) && cat.length > 0) {
          setCandidates(cat);
          setStatus(`Product "${info.name}" is now stocked in Sentinel Network!`);
          setAgentSteps(prev => [...prev, { step: `Stocked ${info.name} in catalog`, status: "DONE", time: new Date().toLocaleTimeString() }]);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  const mandateId = typeof mandate?.id === "string" ? mandate.id : undefined;

  return (
    <div className="min-h-screen bg-background">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="afterInteractive" />

      {/* Top Navigation */}
      <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex h-14 items-center justify-between px-4 md:px-8 max-w-full mx-auto">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" asChild className="gap-1.5 text-xs">
              <a href="/app"><ArrowLeft className="h-3.5 w-3.5" /> Hub</a>
            </Button>
            <div className="h-4 w-px bg-border" />
            <div className="flex items-center gap-2">
              <div className="p-1 bg-emerald-500/10 rounded-md ring-1 ring-emerald-500/20">
                <Bot className="h-4 w-4 text-emerald-400" />
              </div>
              <span className="font-bold tracking-tight text-sm">SENTINEL AI</span>
              <Badge className="text-[9px] py-0 px-1.5 bg-emerald-500/10 text-emerald-400 border-emerald-500/20">BUYER</Badge>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a href="/merchant/dashboard" className="text-xs text-blue-400 hover:underline flex items-center gap-1">
              <Store className="w-3 h-3" /> Merchant View
            </a>
            <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20">RAZORPAY TEST</Badge>
          </div>
        </div>
      </header>

      {/* 3-Column Layout */}
      <div className="flex h-[calc(100vh-56px)] overflow-hidden">
        {/* Left: Conversation */}
        <div className="w-full md:w-[380px] lg:w-[420px] border-r border-border/40 flex flex-col shrink-0">
          <div className="p-3 border-b border-border/40">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-emerald-400" /> Conversation
              </h3>
              <Button variant="secondary" size="sm" onClick={start} disabled={!!thread || loading} className="text-xs h-7">
                {thread ? "Active" : <><Play className="h-3 w-3 mr-1" /> Start</>}
              </Button>
            </div>
          </div>

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {messages.length === 0 && (
              <div className="text-center pt-8">
                <Bot className="w-8 h-8 text-emerald-400/30 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">{status}</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className={`max-w-[85%] px-3 py-2 rounded-xl text-sm ${
                  msg.role === "user"
                    ? "bg-emerald-500/10 text-emerald-100 border border-emerald-500/20"
                    : "bg-card/50 border border-border/50"
                }`}>
                  {msg.content}
                </div>
              </motion.div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="px-3 py-2 rounded-xl bg-card/50 border border-border/50">
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                </div>
              </div>
            )}
          </div>

          {/* Chat Input */}
          <div className="p-3 border-t border-border/40">
            <form onSubmit={send} className="flex gap-2">
              <Textarea
                name="message"
                className="min-h-[60px] max-h-[100px] resize-none text-sm"
                placeholder="Negotiate for premium Sony headphones under Rs 25,000..."
                disabled={!thread}
              />
              <Button type="submit" size="sm" disabled={!thread || loading} className="shrink-0 self-end bg-emerald-600 hover:bg-emerald-700">
                <Send className="w-4 h-4" />
              </Button>
            </form>
          </div>
        </div>

        {/* Center: Commerce Workspace */}
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 hidden md:block">
          {/* Mandate */}
          {intent && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="border-red-500/30 bg-red-500/5">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2 text-red-400">
                      <ShieldAlert className="h-4 w-4" /> Mandate Authority
                    </CardTitle>
                    <Badge className="bg-red-500/10 text-red-400 border-red-500/20 animate-pulse text-xs">
                      {mandate ? "ACTIVE" : "CONFIRM REQUIRED"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <pre className="p-3 rounded-lg bg-black/40 border border-red-500/20 text-xs font-mono text-red-300 overflow-auto max-h-32">
                    {JSON.stringify(intent, null, 2)}
                  </pre>
                  <Button
                    variant="destructive"
                    size="sm"
                    className="w-full"
                    disabled={!intentId || !!mandate}
                    onClick={activate}
                  >
                    {mandate ? "Mandate Cryptographically Active" : "Confirm & Activate Mandate"}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Market Intelligence */}
          {intent && (
            <MarketIntelligence
              query={typeof intent.product_query === "string" ? intent.product_query : "Product"}
              budgetMinor={intent.max_budget_minor}
              hasNativeStock={candidates.length > 0}
              nativePriceMinor={candidates[0]?.current_price_minor}
              onInstantList={handleInstantList}
            />
          )}

          {/* Product Candidates */}
          {candidates.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-base font-semibold">Matched Products</h3>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {candidates.map(p => (
                  <Card key={p.product_id} className="border-border/50">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base">{p.name}</CardTitle>
                      <p className="text-xl font-bold text-emerald-400">
                        {p.currency} {(p.current_price_minor / 100).toLocaleString("en-IN")}
                      </p>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-1 mb-3">
                        {p.why_matched.map((r, i) => (
                          <Badge key={i} variant="outline" className="text-[10px]">{r}</Badge>
                        ))}
                      </div>
                      <ProvenanceDrawer
                        label="Catalog source"
                        evidence={{
                          value: String(p.current_price_minor),
                          unit: "minor currency units",
                          valueType: "REAL_DATA",
                          trustClass: "MERCHANT_API",
                          method: "Agent-readable catalog DTO",
                          source: "Merchant catalog",
                          financialAuthority: "NONE",
                          updatedAt: new Date().toISOString()
                        }}
                      />
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Build Cart */}
          {candidates.length > 0 && mandateId && (
            <Card className="border-border/50">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShoppingCart className="h-4 w-4 text-emerald-400" /> Bounded Cart
                  </CardTitle>
                  <Badge variant="outline" className="text-xs">SHARED CART</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <Button
                  className="w-full bg-emerald-600 hover:bg-emerald-700"
                  disabled={!!cartId}
                  onClick={buildCart}
                >
                  {cartId ? "Cart Committed" : "Build Bounded Cart"}
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Negotiation / Growth / Campaign */}
          {cartId && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <NegotiationCard mandateId={mandateId} product={candidates[0]} cartId={cartId} />
              <GrowthCard mandateId={mandateId} product={candidates[0]} cartId={cartId} />
              <CampaignCard cartId={cartId} />
            </div>
          )}

          {/* Cart + Verification + Checkout */}
          {cartId && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <CartCard product={candidates[0]} budgetMinor={intent?.max_budget_minor} mandateId={mandateId} cartId={cartId} />
              <VerificationCard />
            </div>
          )}
        </div>

        {/* Right: Agent Activity */}
        <div className="w-72 border-l border-border/40 hidden lg:flex flex-col shrink-0">
          <div className="p-3 border-b border-border/40">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Zap className="w-4 h-4 text-yellow-400" /> Agent Steps
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {agentSteps.length === 0 && (
              <p className="text-xs text-muted-foreground text-center pt-4">
                Agent activity will appear here...
              </p>
            )}
            {agentSteps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-start gap-2 text-xs"
              >
                {step.status === "DONE" ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin shrink-0 mt-0.5" />
                )}
                <div>
                  <p className={step.status === "DONE" ? "text-muted-foreground" : "text-foreground"}>{step.step}</p>
                  <p className="text-muted-foreground/60">{step.time}</p>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Privacy Notice */}
          <div className="p-3 border-t border-border/40">
            <div className="p-2 rounded-lg bg-purple-500/5 border border-purple-500/10">
              <div className="flex items-center gap-1.5 text-xs text-purple-400">
                <Eye className="w-3 h-3" />
                <span className="font-medium">Privacy Active</span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-1">
                Your max budget is hidden from the merchant. Merchant floor is hidden from you.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
