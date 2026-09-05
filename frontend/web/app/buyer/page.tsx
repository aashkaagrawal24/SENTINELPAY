"use client";

import Script from "next/script";
import { FormEvent, useState, useMemo } from "react";
import { CartCard, VerificationCard } from "../../components/commerce";
import { CampaignCard, GrowthCard, NegotiationCard } from "../../components/growth";
import { ProvenanceDrawer } from "../../components/provenance";
import { MarketIntelligence } from "../../components/market-intelligence";
import BulkProcurementPanel from "../../components/bulk-procurement";
import GlobalMarketplace, { MerchantOffer, CanonicalProduct } from "../../components/global-marketplace";
import { AgentExecutionTimeline, TimelineStep } from "../../components/common/agent-execution-timeline";
import { StatusBadge } from "../../components/common/status-badge";
import { apiFetch } from "../../lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { 
  ArrowLeft, MessageSquare, Play, Send, ShieldAlert, ShoppingCart, 
  Package, Store, Check, Sparkles, Users, Lock, Bot, ShieldCheck,
  CheckCircle2, RefreshCw
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

type Candidate = {
  product_id: string;
  merchant_id: string;
  merchant_name?: string;
  name: string;
  current_price_minor: number;
  currency: string;
  seller_count?: number;
  other_offers?: Array<{
    product_id: string;
    merchant_id: string;
    merchant_name: string;
    current_price_minor: number;
    currency: string;
    stock: number;
  }>;
  why_matched: string[];
};

type Intent = { max_budget_minor?: number; [key: string]: unknown };

export default function BuyerPage() {
  const [activeTab, setActiveTab] = useState("marketplace");
  const [thread, setThread] = useState("");
  const [intentId, setIntentId] = useState("");
  const [intent, setIntent] = useState<Intent | null>(null);
  const [mandate, setMandate] = useState<Record<string, unknown> | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCandidateIndex, setSelectedCandidateIndex] = useState(0);
  const [cartId, setCartId] = useState("");
  const [status, setStatus] = useState("Start a secured conversation or browse the Global Marketplace.");
  const [isSearching, setIsSearching] = useState(false);
  const [queryText, setQueryText] = useState("Find Vanilla Ice Cream Tub under Rs 150, check across all merchants, and pick the best offer.");
  const [bulkInitialData, setBulkInitialData] = useState<{
    productId?: string;
    merchantId?: string;
    productName?: string;
    merchantName?: string;
  }>({});

  const quickPrompts = [
    { label: "Vanilla Ice Cream (< ₹150)", prompt: "Find Vanilla Ice Cream Tub under Rs 150, check across all merchants, and pick the best offer." },
    { label: "Sony Headphones (< ₹25,000)", prompt: "Find Sony WH-1000XM5 wireless headphones under Rs 25,000 across all merchants." },
    { label: "MacBook Pro 16 (< ₹3,50,000)", prompt: "Find Apple MacBook Pro 16 M3 Max under Rs 3,50,000 across all merchants." },
    { label: "Nike Sneakers (< ₹17,000)", prompt: "Find Nike Air Jordan 1 high top sneakers under Rs 17,000." },
  ];
  
  async function start() {
    const r = await apiFetch("/api/conversations", { method: "POST", body: "{}" });
    const d = await r.json();
    setThread(d.id);
    setStatus("Conversation active — ask BuyerAgent to find or negotiate any product.");
  }
  
  async function send(e?: FormEvent<HTMLFormElement>, customQuery?: string) {
    if (e) e.preventDefault();
    const content = customQuery || queryText;
    if (!content.trim()) return;
    
    // Auto-start session if not started
    let activeThread = thread;
    if (!activeThread) {
      const r = await apiFetch("/api/conversations", { method: "POST", body: "{}" });
      const d = await r.json();
      activeThread = d.id;
      setThread(d.id);
    }

    setIsSearching(true);
    setStatus("BuyerAgent parsing intent and searching SentinelPay global catalog...");
    try {
      const conversation = await apiFetch(`/api/conversations/${activeThread}/messages`, { 
        method: "POST", 
        body: JSON.stringify({ content }) 
      });
      const result = await conversation.json();
      setStatus(result.message || result.status);
      setIntent(result.parsed_intent || null);
      setCandidates(result.candidates || []);
      setSelectedCandidateIndex(0);
      if (result.intent_id) {
        setIntentId(result.intent_id);
      }
    } catch (err) {
      console.error(err);
      setStatus("Error processing search query");
    } finally {
      setIsSearching(false);
    }
  }
  
  async function activate() {
    const response = await apiFetch("/api/mandates", { method: "POST", body: JSON.stringify({ intent_id: intentId, confirmed: true }) });
    const data = await response.json();
    setMandate(data);
    setStatus(data.status === "ACTIVE" ? "Mandate ACTIVE — bounds authorized" : "Mandate activation failed");
  }
  
  async function buildCart() {
    const product = candidates[selectedCandidateIndex] || candidates[0];
    if (!product || !mandateId) return;
    const created = await apiFetch("/api/carts", { method: "POST", body: JSON.stringify({ merchant_id: product.merchant_id, mandate_id: mandateId }) });
    const cart = await created.json();
    if (!created.ok) {
      setStatus(cart.detail || "Cart creation failed");
      return;
    }
    const added = await apiFetch(`/api/carts/${cart.id}/items`, { method: "POST", body: JSON.stringify({ product_id: product.product_id, quantity: 1 }) });
    if (!added.ok) {
      const error = await added.json();
      setStatus(error.detail || "Product could not be added");
      return;
    }
    setCartId(cart.id);
    setStatus(`Bounded cart ready with ${product.merchant_name || 'selected merchant'}. Ready for negotiation and checkout.`);
  }

  async function handleSelectRetailOffer(offer: MerchantOffer, product: CanonicalProduct) {
    setStatus(`Connecting to ${offer.merchant_name} for ${product.name}...`);
    try {
      // 1. Create intent
      const r = await apiFetch("/api/intents", {
        method: "POST",
        body: JSON.stringify({ raw_text: `Buy 1 unit of ${product.name} from ${offer.merchant_name} at Rs ${offer.unit_price_minor / 100}` })
      });
      const intentData = await r.json();
      setIntentId(intentData.id);
      setIntent(intentData.parsed_intent || null);

      // 2. Activate mandate
      const mRes = await apiFetch("/api/mandates", {
        method: "POST",
        body: JSON.stringify({ intent_id: intentData.id, confirmed: true })
      });
      const mandateData = await mRes.json();
      setMandate(mandateData);

      // 3. Create cart with the chosen merchant
      const cRes = await apiFetch("/api/carts", {
        method: "POST",
        body: JSON.stringify({ merchant_id: offer.merchant_id, mandate_id: mandateData.id })
      });
      const cart = await cRes.json();
      if (!cRes.ok) {
        setStatus(cart.detail || "Cart creation failed");
        return;
      }

      // 4. Add item
      const added = await apiFetch(`/api/carts/${cart.id}/items`, {
        method: "POST",
        body: JSON.stringify({ product_id: offer.product_id, quantity: 1 })
      });
      if (!added.ok) {
        const error = await added.json();
        setStatus(error.detail || "Item addition failed");
        return;
      }

      // 5. Update candidates with chosen merchant
      const candidate: Candidate = {
        product_id: offer.product_id,
        merchant_id: offer.merchant_id,
        merchant_name: offer.merchant_name,
        name: product.name,
        current_price_minor: offer.unit_price_minor,
        currency: offer.currency,
        seller_count: product.seller_count,
        why_matched: [
          `Selected Merchant: ${offer.merchant_name}`,
          `${offer.stock} units available`,
          offer.negotiation_enabled ? "Autonomous negotiation supported" : "Fixed price",
          `SKU: ${offer.sku}`
        ]
      };
      setCandidates([candidate]);
      setSelectedCandidateIndex(0);
      setCartId(cart.id);
      setStatus(`Cart bounded to ${offer.merchant_name}. Proceed to negotiation, campaign add-ons, or payment.`);
      setActiveTab("retail");
    } catch (err) {
      console.error(err);
      setStatus("Failed to initialize transaction for selected merchant");
    }
  }

  function handleSelectBulkOffer(offer: MerchantOffer, product: CanonicalProduct) {
    setBulkInitialData({
      productId: offer.product_id,
      merchantId: offer.merchant_id,
      productName: product.name,
      merchantName: offer.merchant_name
    });
    setActiveTab("bulk");
  }

  function handleSwitchCandidateOffer(targetOffer: { product_id: string; merchant_id: string; merchant_name: string; current_price_minor: number; currency: string; stock: number }, originalCandidate: Candidate) {
    const updatedCandidate: Candidate = {
      product_id: targetOffer.product_id,
      merchant_id: targetOffer.merchant_id,
      merchant_name: targetOffer.merchant_name,
      name: originalCandidate.name,
      current_price_minor: targetOffer.current_price_minor,
      currency: targetOffer.currency,
      seller_count: originalCandidate.seller_count,
      other_offers: originalCandidate.other_offers,
      why_matched: [
        `Switched to Seller: ${targetOffer.merchant_name}`,
        `${targetOffer.stock} units in stock`,
        `Price: ₹${targetOffer.current_price_minor / 100}`,
      ]
    };
    setCandidates([updatedCandidate]);
    setSelectedCandidateIndex(0);
    setCartId(""); // Reset cart so it recommits to new merchant
    setStatus(`Switched seller to ${targetOffer.merchant_name}. Click "Build Bounded Cart" to commit.`);
  }
  
  const mandateId = typeof mandate?.id === "string" ? mandate.id : undefined;
  const selectedProduct = candidates[selectedCandidateIndex] || candidates[0];

  // Dynamic calculation of timeline steps for agent execution visualization
  const timelineSteps: TimelineStep[] = useMemo(() => {
    return [
      {
        id: "req",
        label: "Request Received",
        description: intent ? "User intent extracted and bounded" : "Awaiting purchase intent",
        status: isSearching ? "processing" : intent ? "success" : "pending"
      },
      {
        id: "disc",
        label: "Discovering Merchants",
        description: candidates.length > 0 ? `Indexed ${candidates.length} candidate(s)` : "Scanning network catalog",
        status: isSearching ? "processing" : candidates.length > 0 ? "success" : "pending"
      },
      {
        id: "comp",
        label: "Comparing Offers",
        description: selectedProduct ? `Selected ${selectedProduct.merchant_name || 'best offer'}` : "Analyzing seller conditions",
        status: selectedProduct ? "success" : "pending"
      },
      {
        id: "sec",
        label: "Security Kernel",
        description: cartId ? "Cart committed via Z3 solver" : mandate ? "Mandate active, cart pending" : "Awaiting mandate confirmation",
        status: cartId ? "success" : mandate ? "processing" : "pending"
      },
      {
        id: "pay",
        label: "Razorpay Test Payment",
        description: cartId ? "Server-side checkout ready" : "Awaiting cart commitment",
        status: cartId ? "processing" : "pending"
      },
      {
        id: "aud",
        label: "Audit Receipt",
        description: "Durable cryptographic ledger record",
        status: "pending"
      }
    ];
  }, [isSearching, intent, candidates.length, selectedProduct, mandate, cartId]);
  
  return (
    <div className="min-h-screen bg-background pb-16">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="afterInteractive" />
      
      {/* Top Navigation */}
      <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center justify-between px-4 md:px-8 max-w-7xl mx-auto">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" asChild className="gap-2 text-xs">
              <a href="/app">
                <ArrowLeft className="h-4 w-4" />
                <span className="hidden sm:inline">Hub</span>
              </a>
            </Button>
            <div className="h-4 w-px bg-border" />
            <div className="flex items-center gap-2">
              <div className="p-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <Bot className="h-4 w-4" />
              </div>
              <span className="font-bold tracking-tight text-xs md:text-sm">
                SENTINELPAY MARKETPLACE &amp; BUYER
              </span>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <a 
              href="/merchant/dashboard" 
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1 font-medium"
            >
              <Store className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Switch to Merchant Console</span>
            </a>
            <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20 text-[10px] font-mono">
              RAZORPAY TEST MODE
            </Badge>
          </div>
        </div>
      </header>

      <main className="container max-w-7xl mx-auto p-4 md:p-8 pt-6 space-y-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border/40">
            <TabsList className="bg-muted/40 border border-border/50 p-1 rounded-xl">
              <TabsTrigger value="marketplace" className="gap-2 text-xs rounded-lg">
                <Store className="h-4 w-4 text-primary" /> Global Marketplace
              </TabsTrigger>
              <TabsTrigger value="retail" className="gap-2 text-xs rounded-lg">
                <ShoppingCart className="h-4 w-4 text-emerald-400" /> Retail &amp; AI Chat
              </TabsTrigger>
              <TabsTrigger value="bulk" className="gap-2 text-xs rounded-lg">
                <Package className="h-4 w-4 text-amber-400" /> Bulk Procurement
              </TabsTrigger>
            </TabsList>

            <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
              <Lock className="w-3.5 h-3.5 text-purple-400" />
              <span>Buyer Budget Privacy Active</span>
            </div>
          </div>

          {/* ── GLOBAL MARKETPLACE TAB ── */}
          <TabsContent value="marketplace" className="space-y-6">
            <GlobalMarketplace
              onSelectRetailOffer={handleSelectRetailOffer}
              onSelectBulkOffer={handleSelectBulkOffer}
            />
          </TabsContent>

          {/* ── RETAIL & AI CHAT TAB ── */}
          <TabsContent value="retail" className="space-y-6">
            {/* Live Agent Execution Timeline */}
            <AgentExecutionTimeline steps={timelineSteps} />

            {/* Chat / Intent Extraction Section */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="glass-panel border-border/60">
                <CardHeader className="pb-3 border-b border-border/40">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="space-y-1">
                      <CardTitle className="text-base flex items-center gap-2 text-foreground">
                        <Bot className="h-4 w-4 text-emerald-400" /> BuyerAgent Autonomous Search &amp; Intent Parser
                      </CardTitle>
                      <CardDescription className="text-xs text-muted-foreground">
                        {status}
                      </CardDescription>
                    </div>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={start} 
                      disabled={!!thread}
                      className="text-xs h-8 border-border/60 shrink-0"
                    >
                      {thread ? (
                        <span className="flex items-center gap-1.5 text-emerald-400">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                          Session Active
                        </span>
                      ) : (
                        <><Play className="h-3.5 w-3.5 mr-1.5 text-primary" /> Start Agent Session</>
                      )}
                    </Button>
                  </div>
                </CardHeader>

                <CardContent className="pt-4 space-y-4">
                  {/* Quick prompt suggestions */}
                  <div className="space-y-1.5">
                    <span className="text-[11px] text-muted-foreground font-mono">Quick Inquiries:</span>
                    <div className="flex flex-wrap gap-2">
                      {quickPrompts.map((qp, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => {
                            setQueryText(qp.prompt);
                            send(undefined, qp.prompt);
                          }}
                          className="text-[11px] px-2.5 py-1 rounded-lg bg-muted/40 hover:bg-primary/10 border border-border/50 hover:border-primary/40 text-muted-foreground hover:text-foreground transition-all"
                        >
                          {qp.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <form onSubmit={(e) => send(e)} className="space-y-3">
                    <Textarea 
                      value={queryText}
                      onChange={(e) => setQueryText(e.target.value)}
                      name="message" 
                      className="min-h-[90px] resize-none bg-background/50 text-xs md:text-sm font-sans leading-relaxed"
                      placeholder="e.g. Find Sony WH-1000XM5 under Rs 25,000, check all merchants, and pick the best offer..."
                    />
                    <div className="flex justify-end">
                      <Button 
                        type="submit" 
                        size="sm"
                        disabled={isSearching}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white gap-2 text-xs h-9 px-4"
                      >
                        {isSearching ? (
                          <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Searching Network...</>
                        ) : (
                          <><Send className="w-3.5 h-3.5" /> Interpret &amp; Compare Marketplace</>
                        )}
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            </motion.div>

            {/* Universal Market Intelligence */}
            {intent && (
              <MarketIntelligence />
            )}

            {/* Mandate Authorization Section with Cryptographic Seal */}
            {intent && (
              <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}>
                <Card className="border-rose-500/30 bg-rose-500/5 backdrop-blur-sm">
                  <CardHeader className="pb-3 border-b border-rose-500/20">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base flex items-center gap-2 text-rose-400">
                        <ShieldAlert className="h-4 w-4" /> Cryptographic Mandate Authority
                      </CardTitle>
                      <Badge className="bg-rose-500/10 text-rose-400 border-rose-500/20 text-[10px] font-mono animate-pulse">
                        {mandate ? "MANDATE ACTIVE" : "HUMAN CONFIRMATION REQUIRED"}
                      </Badge>
                    </div>
                    <CardDescription className="text-xs text-rose-300/80 mt-1">
                      The autonomous agent is strictly bounded by the parsed parameters below. It cannot exceed this ceiling.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="pt-4 space-y-4">
                    <pre className="p-3.5 rounded-xl bg-black/60 border border-rose-500/20 text-xs font-mono text-rose-300 overflow-auto max-h-40">
                      {JSON.stringify(intent, null, 2)}
                    </pre>
                    <Button 
                      variant="destructive" 
                      className="w-full text-xs h-9 bg-rose-600 hover:bg-rose-700 text-white font-medium"
                      disabled={!intentId || !!mandate} 
                      onClick={activate}
                    >
                      {mandate ? "✓ Mandate Cryptographically Signed & Active" : "Confirm & Sign Mandate Authorization"}
                    </Button>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* Candidate Products Grid with Multi-Seller Support */}
            {candidates.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between pb-1 border-b border-border/40">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground font-mono">
                    Matching Products Across Marketplace ({candidates.length})
                  </h3>
                  <span className="text-xs text-muted-foreground">
                    Active Choice: <strong className="text-foreground">{selectedProduct?.merchant_name || selectedProduct?.merchant_id}</strong>
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                  {candidates.map((p, idx) => {
                    const isSelected = idx === selectedCandidateIndex;
                    return (
                      <motion.div key={p.product_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                        <Card className={`glass-panel h-full flex flex-col justify-between transition-all rounded-2xl ${
                          isSelected ? "border-primary ring-1 ring-primary/40 bg-primary/5" : "border-border/60"
                        }`}>
                          <CardHeader className="pb-3 space-y-2">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-muted-foreground bg-muted/40 px-2 py-0.5 rounded border border-border/40">
                                {p.merchant_name || "Merchant"}
                              </span>
                              {isSelected && (
                                <Badge className="bg-primary text-primary-foreground text-[10px] font-bold">
                                  SELECTED SELLER
                                </Badge>
                              )}
                            </div>
                            <CardTitle className="text-base font-bold text-foreground">{p.name}</CardTitle>
                            <div className="text-2xl font-bold font-mono text-emerald-400">
                              {p.currency} {(p.current_price_minor / 100).toLocaleString("en-IN")}
                            </div>
                          </CardHeader>
                          
                          <CardContent className="flex-1 space-y-3">
                            <div className="flex flex-wrap gap-1.5">
                              {p.why_matched.map((reason, i) => (
                                <span key={i} className="inline-flex items-center rounded-md bg-muted/50 border border-border/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                                  {reason}
                                </span>
                              ))}
                            </div>

                            {/* Other Sellers for Same Product */}
                            {p.other_offers && p.other_offers.length > 0 && (
                              <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-3 space-y-2 text-xs">
                                <span className="font-semibold text-indigo-400 flex items-center gap-1.5 text-[11px]">
                                  <Users className="h-3.5 w-3.5" /> Other Verified Sellers:
                                </span>
                                <div className="space-y-1.5">
                                  {p.other_offers.map((alt) => (
                                    <div key={alt.product_id} className="flex items-center justify-between gap-2 pt-1 border-t border-indigo-500/10 text-xs">
                                      <span className="text-muted-foreground">{alt.merchant_name} (₹{alt.current_price_minor / 100})</span>
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-6 px-2 text-[10px] border-border/60 hover:border-indigo-500/40"
                                        onClick={() => handleSwitchCandidateOffer(alt, p)}
                                      >
                                        Switch Seller
                                      </Button>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            <ProvenanceDrawer 
                              label="Public price provenance" 
                              evidence={{
                                value: String(p.current_price_minor),
                                unit: "minor currency units",
                                valueType: "REAL_DATA",
                                trustClass: "MERCHANT_API",
                                method: "Agent-readable catalog DTO",
                                source: p.merchant_name ? `${p.merchant_name} catalog` : "Merchant catalog",
                                financialAuthority: "NONE",
                                updatedAt: new Date().toISOString()
                              }}
                            />
                          </CardContent>

                          <div className="p-4 pt-0">
                            {!isSelected ? (
                              <Button
                                variant="outline"
                                size="sm"
                                className="w-full text-xs h-8 border-border/60 hover:border-primary/40"
                                onClick={() => {
                                  setSelectedCandidateIndex(idx);
                                  setCartId("");
                                }}
                              >
                                Select This Merchant Offer
                              </Button>
                            ) : (
                              <div className="text-center text-xs text-primary font-medium py-1 font-mono">
                                ✓ Ready for bounded cart commitment
                              </div>
                            )}
                          </div>
                        </Card>
                      </motion.div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Cart Building Section */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="glass-panel border-border/60">
                <CardHeader className="pb-3 border-b border-border/40">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2 text-foreground">
                      <ShoppingCart className="h-4 w-4 text-primary" /> Commit Bounded Product
                    </CardTitle>
                    <Badge className="bg-primary/10 text-primary border-primary/20 text-[10px] font-mono">
                      {selectedProduct?.merchant_name ? `SELLER: ${selectedProduct.merchant_name.toUpperCase()}` : "BOUNDED CART"}
                    </Badge>
                  </div>
                  <CardDescription className="text-xs text-muted-foreground mt-1">
                    Negotiation, dynamic discounts, and promotional campaigns modify this cart strictly through SecurityKernel verification.
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-4">
                  <Button 
                    className="w-full text-xs h-9 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
                    disabled={!mandateId || !selectedProduct || !!cartId} 
                    onClick={buildCart}
                  >
                    {cartId 
                      ? `✓ Bounded Cart Active (${selectedProduct?.merchant_name || 'Selected Merchant'})` 
                      : `Build Bounded Cart (${selectedProduct?.merchant_name || 'Selected Merchant'})`}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>

            {/* Advanced Modules (Negotiation, Growth, Campaign) */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              <NegotiationCard mandateId={mandateId} product={selectedProduct} cartId={cartId} />
              <GrowthCard mandateId={mandateId} product={selectedProduct} cartId={cartId} />
              <CampaignCard cartId={cartId} />
            </div>

            {/* Checkout & Verification Modules */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 pb-16">
              <CartCard product={selectedProduct} budgetMinor={intent?.max_budget_minor} mandateId={mandateId} cartId={cartId} />
              <VerificationCard />
            </div>
          </TabsContent>

          {/* ── BULK PROCUREMENT TAB ── */}
          <TabsContent value="bulk">
            <BulkProcurementPanel
              initialProductId={bulkInitialData.productId}
              initialMerchantId={bulkInitialData.merchantId}
              initialProductName={bulkInitialData.productName}
              initialMerchantName={bulkInitialData.merchantName}
            />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
