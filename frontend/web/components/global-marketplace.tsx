"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "../lib/api";
import { motion, AnimatePresence } from "framer-motion";
import {
  Store, Search, Filter, Sparkles, CheckCircle2, AlertTriangle,
  ArrowRight, Tag, Package, ShoppingCart, Users, Layers, ShieldCheck,
  TrendingUp, RefreshCw, X, ChevronRight, Check, Bot, Zap, ArrowUpRight
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState } from "@/components/common/empty-state";

export type MerchantOffer = {
  product_id: string;
  merchant_id: string;
  merchant_name: string;
  sku: string;
  unit_price_minor: number;
  currency: string;
  condition: string;
  stock: number;
  inventory_status: string;
  negotiation_enabled: boolean;
  max_discount_percent: number;
  bulk_enabled: boolean;
  bulk_min_quantity: number;
  bulk_discount_percent: number;
  // Ranked fields
  rank?: number;
  is_recommended?: boolean;
  can_fulfill?: boolean;
  reasons?: string[];
};

export type CanonicalProduct = {
  canonical_id: string;
  name: string;
  brand: string;
  category: string;
  description: string;
  seller_count: number;
  min_price_minor: number;
  max_price_minor: number;
  starting_price_inr: number;
  total_stock: number;
  negotiation_available: boolean;
  bulk_available: boolean;
  best_offer: MerchantOffer;
  offers: MerchantOffer[];
};

interface GlobalMarketplaceProps {
  onSelectRetailOffer: (offer: MerchantOffer, product: CanonicalProduct) => void;
  onSelectBulkOffer: (offer: MerchantOffer, product: CanonicalProduct) => void;
}

export default function GlobalMarketplace({ onSelectRetailOffer, onSelectBulkOffer }: GlobalMarketplaceProps) {
  const [products, setProducts] = useState<CanonicalProduct[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");
  const [inStockOnly, setInStockOnly] = useState(false);
  const [multiSellerOnly, setMultiSellerOnly] = useState(false);
  const [negotiableOnly, setNegotiableOnly] = useState(false);
  const [bulkOnly, setBulkOnly] = useState(false);
  const [sortBy, setSortBy] = useState("best_match");

  // Selected product for offers modal
  const [activeProduct, setActiveProduct] = useState<CanonicalProduct | null>(null);
  const [offersModalOpen, setOffersModalOpen] = useState(false);

  // AI Offer Ranking state
  const [aiQuantity, setAiQuantity] = useState("1");
  const [rankingLoading, setRankingLoading] = useState(false);
  const [rankedOffers, setRankedOffers] = useState<MerchantOffer[]>([]);
  const [aiExplanation, setAiExplanation] = useState("");

  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery.trim()) params.set("query", searchQuery.trim());
      if (selectedCategory && selectedCategory !== "ALL") params.set("category", selectedCategory);
      if (inStockOnly) params.set("in_stock_only", "true");
      if (multiSellerOnly) params.set("multi_seller_only", "true");
      if (negotiableOnly) params.set("negotiable_only", "true");
      if (bulkOnly) params.set("bulk_only", "true");
      if (sortBy) params.set("sort_by", sortBy);

      const res = await apiFetch(`/api/marketplace/catalog?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setProducts(data.products || []);
        if (data.categories?.length > 0) {
          setCategories(data.categories);
        }
      }
    } catch (e) {
      console.error("Failed to load marketplace catalog:", e);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, selectedCategory, inStockOnly, multiSellerOnly, negotiableOnly, bulkOnly, sortBy]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const handleOpenOffers = (product: CanonicalProduct) => {
    setActiveProduct(product);
    setRankedOffers(product.offers);
    setAiExplanation("");
    setAiQuantity("1");
    setOffersModalOpen(true);
  };

  const handleRankOffers = async (qty: number) => {
    if (!activeProduct) return;
    setRankingLoading(true);
    try {
      const res = await apiFetch("/api/marketplace/rank-offers", {
        method: "POST",
        body: JSON.stringify({
          offers: activeProduct.offers,
          quantity: qty,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setRankedOffers(data.ranked_offers || activeProduct.offers);
        setAiExplanation(data.explanation || "");
      }
    } catch (e) {
      console.error("Failed to rank offers:", e);
    } finally {
      setRankingLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Hero / Header Banner with Dark Graphite Fintech Elevation */}
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-r from-primary/10 via-card/80 to-background p-6 backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 border border-primary/20 px-3 py-1 text-xs font-semibold text-primary">
              <Store className="h-3.5 w-3.5" /> Global Multi-Merchant Network
            </div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-foreground">
              Autonomous Commerce Marketplace
            </h1>
            <p className="text-xs md:text-sm text-muted-foreground leading-relaxed">
              Discover verified products across all SentinelPay merchants. Compare live price curves, inspect warehouse inventory, and delegate supplier selection to the autonomous BuyerAgent.
            </p>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <div className="flex flex-col items-end px-4 py-2 rounded-xl bg-background/60 border border-border/60">
              <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-mono">Catalog Scale</span>
              <span className="font-mono text-xl font-bold text-foreground">{products.length} Products</span>
            </div>
            <Button 
              variant="outline" 
              size="icon" 
              onClick={fetchCatalog} 
              disabled={loading} 
              title="Refresh Marketplace Feed"
              className="h-11 w-11 rounded-xl border-border/60 hover:border-primary/40"
            >
              <RefreshCw className={`h-4 w-4 text-foreground ${loading ? "animate-spin text-primary" : ""}`} />
            </Button>
          </div>
        </div>
      </div>

      {/* Search & Filter Controls */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search across merchants (e.g. Sony WH-1000XM5, Vanilla Ice Cream, MacBook, Footwear)..."
              className="pl-10 pr-9 h-11 bg-card/60 border-border/60 rounded-xl text-xs md:text-sm"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="h-11 rounded-xl border border-border/60 bg-card/60 px-3 py-2 text-xs font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="best_match">Sort: Best Match</option>
              <option value="price_low">Price: Low to High</option>
              <option value="price_high">Price: High to Low</option>
              <option value="stock_high">Availability: Highest Stock</option>
              <option value="sellers_high">Competition: Most Sellers</option>
            </select>
          </div>
        </div>

        {/* Dynamic Category Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
          <button
            onClick={() => setSelectedCategory("ALL")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
              selectedCategory === "ALL"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "bg-muted/40 text-muted-foreground hover:bg-muted/70 hover:text-foreground border border-border/40"
            }`}
          >
            All Categories
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                selectedCategory === cat
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/40 text-muted-foreground hover:bg-muted/70 hover:text-foreground border border-border/40"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Filter Badges / Toggles */}
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
          <button
            onClick={() => setInStockOnly(!inStockOnly)}
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border transition-all ${
              inStockOnly
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400 font-medium"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            <Check className={`h-3 w-3 ${inStockOnly ? "opacity-100" : "opacity-0"}`} />
            In Stock Only
          </button>

          <button
            onClick={() => setMultiSellerOnly(!multiSellerOnly)}
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border transition-all ${
              multiSellerOnly
                ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-400 font-medium"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            <Users className="h-3 w-3" />
            Multiple Sellers Only
          </button>

          <button
            onClick={() => setNegotiableOnly(!negotiableOnly)}
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border transition-all ${
              negotiableOnly
                ? "border-sky-500/40 bg-sky-500/10 text-sky-400 font-medium"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            <Sparkles className="h-3 w-3" />
            Negotiation Enabled
          </button>

          <button
            onClick={() => setBulkOnly(!bulkOnly)}
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border transition-all ${
              bulkOnly
                ? "border-amber-500/40 bg-amber-500/10 text-amber-400 font-medium"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            <Package className="h-3 w-3" />
            Bulk Tiers Available
          </button>
        </div>
      </div>

      {/* Catalog Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 py-8">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-64 rounded-2xl border border-border/40 bg-card/40 animate-pulse" />
          ))}
        </div>
      ) : products.length === 0 ? (
        <EmptyState
          icon={Store}
          title="No Matching Marketplace Products"
          description="Try adjusting your search terms, clearing active filters, or expanding category parameters."
          actionLabel="Clear All Filters"
          onAction={() => {
            setSearchQuery("");
            setSelectedCategory("ALL");
            setInStockOnly(false);
            setMultiSellerOnly(false);
            setNegotiableOnly(false);
            setBulkOnly(false);
          }}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {products.map((p) => (
            <motion.div
              key={p.canonical_id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="h-full"
            >
              <Card className="glass-panel-hover h-full flex flex-col justify-between border-border/60 rounded-2xl">
                <CardHeader className="pb-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-muted-foreground bg-muted/40 px-2 py-0.5 rounded border border-border/40">
                      {p.brand}
                    </span>
                    <Badge variant="outline" className="text-[10px] text-muted-foreground border-border/50">
                      {p.category}
                    </Badge>
                  </div>

                  <CardTitle className="text-base font-bold text-foreground line-clamp-1" title={p.name}>
                    {p.name}
                  </CardTitle>

                  {p.description && (
                    <CardDescription className="line-clamp-2 text-xs text-muted-foreground">
                      {p.description}
                    </CardDescription>
                  )}
                </CardHeader>

                <CardContent className="space-y-4 flex-1">
                  {/* Pricing and Multi-Seller highlight */}
                  <div className="space-y-1 pt-1 border-t border-border/30">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
                      Market Price Curve
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="text-2xl font-bold font-mono text-emerald-400">
                        ₹{p.starting_price_inr.toLocaleString("en-IN")}
                      </span>
                      {p.seller_count > 1 && p.max_price_minor > p.min_price_minor && (
                        <span className="text-xs font-mono text-muted-foreground">
                          up to ₹{(p.max_price_minor / 100).toLocaleString("en-IN")}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Seller & Stock Meta */}
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    {p.seller_count > 1 ? (
                      <span className="inline-flex items-center gap-1 rounded-md bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 text-[11px] font-semibold text-indigo-300">
                        <Users className="h-3 w-3" /> {p.seller_count} merchants
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-2 py-0.5 text-[11px] text-muted-foreground">
                        <Store className="h-3 w-3" /> {p.best_offer.merchant_name}
                      </span>
                    )}

                    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ${
                      p.total_stock > 0
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-destructive/10 text-destructive border border-destructive/20"
                    }`}>
                      {p.total_stock > 0 ? `${p.total_stock} in stock` : "Out of stock"}
                    </span>

                    {p.negotiation_available && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 text-[11px] text-sky-400">
                        <Sparkles className="h-3 w-3" /> Negotiable
                      </span>
                    )}

                    {p.bulk_available && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-[11px] text-amber-400">
                        <Package className="h-3 w-3" /> Bulk
                      </span>
                    )}
                  </div>
                </CardContent>

                <CardFooter className="pt-3 pb-3 border-t border-border/40">
                  <Button
                    variant="outline"
                    className="w-full text-xs font-semibold justify-between border-border/60 hover:border-primary/40 group h-9"
                    onClick={() => handleOpenOffers(p)}
                  >
                    <span>
                      {p.seller_count > 1 ? `Compare ${p.seller_count} Merchant Offers` : "View Details & Procurement"}
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform text-muted-foreground group-hover:text-foreground" />
                  </Button>
                </CardFooter>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      {/* Offers Comparison Modal with Futuristic Styling */}
      <AnimatePresence>
        {offersModalOpen && activeProduct && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              className="relative w-full max-w-3xl max-h-[90vh] flex flex-col rounded-2xl border border-border/80 bg-card shadow-2xl overflow-hidden"
            >
              {/* Modal Header */}
              <div className="p-6 pb-4 border-b border-border/40 relative bg-muted/10">
                <button
                  onClick={() => setOffersModalOpen(false)}
                  className="absolute right-5 top-5 p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className="text-[10px] uppercase font-mono">{activeProduct.brand}</Badge>
                  <Badge variant="secondary" className="text-[10px]">{activeProduct.category}</Badge>
                </div>
                <h2 className="text-xl md:text-2xl font-bold text-foreground">
                  {activeProduct.name}
                </h2>
                <p className="text-xs text-muted-foreground mt-1">
                  Autonomous offer comparison across {activeProduct.seller_count} verified sellers with deterministic pricing bounds.
                </p>
              </div>

              {/* Modal Body */}
              <div className="p-6 overflow-y-auto space-y-6">
                {/* AI Offer Recommendation Tool */}
                <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-lg bg-primary/20 text-primary">
                        <Bot className="h-4 w-4" />
                      </div>
                      <span className="font-semibold text-xs text-foreground">
                        Autonomous BuyerAgent Seller Ranking
                      </span>
                    </div>
                    <Badge className="bg-primary/10 text-primary border-primary/20 text-[9px] font-mono">
                      Z3 EXPLAINABLE
                    </Badge>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <label className="text-[11px] text-muted-foreground block mb-1 font-mono">
                        Target Order Volume:
                      </label>
                      <Input
                        type="number"
                        min="1"
                        value={aiQuantity}
                        onChange={(e) => setAiQuantity(e.target.value)}
                        placeholder="e.g. 1 (Retail) or 50 (Bulk)"
                        className="h-9 text-xs font-mono bg-background/80"
                      />
                    </div>
                    <Button
                      size="sm"
                      className="mt-5 h-9 text-xs bg-primary hover:bg-primary/90 text-primary-foreground gap-1.5"
                      disabled={rankingLoading || !parseInt(aiQuantity)}
                      onClick={() => handleRankOffers(parseInt(aiQuantity) || 1)}
                    >
                      {rankingLoading ? (
                        <>
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                          <span>Evaluating...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="h-3.5 w-3.5" />
                          <span>Ask AI to Choose</span>
                        </>
                      )}
                    </Button>
                  </div>

                  {aiExplanation && (
                    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="pt-1">
                      <div className="rounded-lg bg-background/80 border border-primary/20 p-3 text-xs text-primary font-medium flex items-start gap-2.5">
                        <Sparkles className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                        <div className="leading-relaxed">{aiExplanation}</div>
                      </div>
                    </motion.div>
                  )}
                </div>

                {/* Merchant Offers List */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground font-mono">
                      Verified Merchant Offers ({rankedOffers.length})
                    </h4>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {aiExplanation ? "Ordered by AI Confidence" : "Ordered by Unit Price"}
                    </span>
                  </div>

                  <div className="space-y-3">
                    {rankedOffers.map((offer) => {
                      const isAiPick = offer.is_recommended;
                      return (
                        <div
                          key={offer.product_id}
                          className={`rounded-xl border p-4 transition-all ${
                            isAiPick
                              ? "border-emerald-500/80 bg-emerald-500/5 ring-1 ring-emerald-500/30"
                              : "border-border/60 bg-card/60"
                          }`}
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                            <div className="space-y-2 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-sm text-foreground">{offer.merchant_name}</span>
                                {isAiPick && (
                                  <Badge className="bg-emerald-500 text-black text-[10px] font-bold">
                                    ★ BEST MATCH
                                  </Badge>
                                )}
                                <span className="text-[10px] font-mono text-muted-foreground bg-muted/40 px-1.5 py-0.5 rounded border border-border/40">
                                  {offer.sku}
                                </span>
                              </div>

                              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                                <span className="font-bold text-foreground font-mono text-sm">
                                  ₹{(offer.unit_price_minor / 100).toLocaleString("en-IN")}/unit
                                </span>
                                <span>•</span>
                                <span className={offer.stock > 0 ? "text-emerald-400 font-medium" : "text-destructive"}>
                                  {offer.stock} units available
                                </span>
                                {offer.negotiation_enabled && (
                                  <>
                                    <span>•</span>
                                    <span className="text-sky-400">Negotiable</span>
                                  </>
                                )}
                                {offer.bulk_enabled && (
                                  <>
                                    <span>•</span>
                                    <span className="text-amber-400">
                                      Bulk ({offer.bulk_discount_percent}% off for {offer.bulk_min_quantity}+)
                                    </span>
                                  </>
                                )}
                              </div>

                              {/* Justifications */}
                              {offer.reasons && offer.reasons.length > 0 && (
                                <div className="pt-1 flex flex-wrap gap-1.5">
                                  {offer.reasons.map((r, rIdx) => (
                                    <span
                                      key={rIdx}
                                      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-medium ${
                                        r.includes("Can fulfill") || r.includes("Lowest") || r.includes("Best")
                                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                          : r.includes("Insufficient")
                                          ? "bg-destructive/10 text-destructive border border-destructive/20"
                                          : "bg-secondary text-secondary-foreground"
                                      }`}
                                    >
                                      {r}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>

                            {/* Action Buttons */}
                            <div className="flex sm:flex-col items-center gap-2 shrink-0">
                              <Button
                                size="sm"
                                className="w-full sm:w-auto text-xs h-8 bg-primary hover:bg-primary/90 text-primary-foreground gap-1.5"
                                onClick={() => {
                                  setOffersModalOpen(false);
                                  onSelectRetailOffer(offer, activeProduct);
                                }}
                              >
                                <ShoppingCart className="h-3.5 w-3.5" /> Select Seller
                              </Button>

                              <Button
                                variant="outline"
                                size="sm"
                                className="w-full sm:w-auto text-xs h-8 border-border/60 hover:border-amber-500/40 text-muted-foreground hover:text-amber-400 gap-1.5"
                                onClick={() => {
                                  setOffersModalOpen(false);
                                  onSelectBulkOffer(offer, activeProduct);
                                }}
                              >
                                <Package className="h-3.5 w-3.5" /> Procure Bulk
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="border-t border-border/40 p-4 flex justify-end bg-muted/10">
                <Button variant="ghost" size="sm" onClick={() => setOffersModalOpen(false)} className="text-xs">
                  Close
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
