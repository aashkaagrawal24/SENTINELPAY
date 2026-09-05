"use client";
import { FormEvent, useState, useEffect } from "react";
import { apiFetch } from "../../lib/api";
import { motion } from "framer-motion";
import { ArrowLeft, Store, Package, Database, ShieldAlert, Code, Target, TrendingUp, Zap, CheckCircle2, SearchX, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type MarketDemandItem = {
  id: string;
  product_query: string;
  search_count: number;
  estimated_price_inr: number | null;
  currency: string;
  last_searched_at: string | null;
};

export default function MerchantPage() {
  const [merchantId, setMerchantId] = useState("");
  const [productId, setProductId] = useState("");
  const [output, setOutput] = useState("Create a merchant to begin.");
  const [isAiReady, setIsAiReady] = useState(false);
  const [demands, setDemands] = useState<MarketDemandItem[]>([]);
  const [demandLoading, setDemandLoading] = useState(false);
  const [demandError, setDemandError] = useState("");

  // Auto-fetch demand whenever merchantId changes
  useEffect(() => {
    if (!merchantId) return;
    fetchDemand();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merchantId]);

  async function fetchDemand() {
    if (!merchantId) return;
    setDemandLoading(true);
    setDemandError("");
    try {
      const r = await apiFetch(`/api/merchants/${merchantId}/market-demand`);
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Failed to load demand");
      setDemands(data.demands || []);
    } catch (err) {
      setDemandError(err instanceof Error ? err.message : "Failed to load demand");
    } finally {
      setDemandLoading(false);
    }
  }

  async function dismissDemand(demandId: string) {
    try {
      await apiFetch(`/api/merchants/${merchantId}/market-demand/${demandId}`, { method: "DELETE" });
      setDemands(prev => prev.filter(d => d.id !== demandId));
    } catch {
      // ignore
    }
  }
  
  async function call(path: string, init: RequestInit = {}) {
    const r = await apiFetch(path, init);
    const data = await r.json();
    setOutput(JSON.stringify(data, null, 2));
    return data;
  }
  
  async function merchant(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const d = await call("/api/merchants", {
      method: "POST",
      body: JSON.stringify({ name: f.get("name") })
    });
    setMerchantId(d.id);
  }
  
  async function product(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const d = await call(`/api/merchants/${merchantId}/products`, {
      method: "POST",
      body: JSON.stringify({
        sku: f.get("sku"),
        name: f.get("name"),
        brand: f.get("brand"),
        category: f.get("category"),
        description: f.get("description"),
        base_price_minor: Number(f.get("price")) * 100,
        variants: [{ variant_key: "default", name: "Default", attributes: { color: String(f.get("color")) } }]
      })
    });
    setProductId(d.id);
  }
  
  async function inventory(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await call(`/api/merchants/${merchantId}/inventory/${productId}`, {
      method: "PUT",
      body: JSON.stringify({ available_quantity: Number(f.get("available")), reserved_quantity: 0 })
    });
  }
  
  async function policy(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await call(`/api/merchants/${merchantId}/policies`, {
      method: "POST",
      body: JSON.stringify({
        scope: "PRODUCT",
        scope_reference: productId,
        base_price_minor: Number(f.get("base")) * 100,
        minimum_sale_price_minor: Number(f.get("floor")) * 100,
        maximum_discount_percent: Number(f.get("discount")),
        negotiation_enabled: f.get("negotiation") === "on",
        max_negotiation_rounds: 3,
        upsell_enabled: true,
        cross_sell_enabled: true,
        valid_from: new Date().toISOString(),
        status: "ACTIVE"
      })
    });
    setIsAiReady(true);
  }
  
  return (
    <div className="min-h-screen bg-background pb-12">
      <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center gap-4 px-4 md:px-8 max-w-7xl mx-auto">
          <Button variant="ghost" size="sm" asChild className="gap-2">
            <a href="/app">
              <ArrowLeft className="h-4 w-4" />
              <span>Back to Dashboard</span>
            </a>
          </Button>
          <div className="h-4 w-px bg-border"></div>
          <span className="font-bold tracking-tight text-sm">MERCHANT STUDIO</span>
          
          {isAiReady && (
            <Badge className="ml-auto bg-green-500/20 text-green-500 border-green-500/30 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> AI-READY
            </Badge>
          )}
        </div>
      </header>

      <main className="container max-w-7xl mx-auto p-4 md:p-8 pt-8">
        <Tabs defaultValue="catalog" className="space-y-6">
          <TabsList className="bg-muted/50 border border-border/50">
            <TabsTrigger value="catalog">Catalog & Policies</TabsTrigger>
            <TabsTrigger value="campaigns">Opportunity Detector (Campaigns)</TabsTrigger>
            <TabsTrigger value="demand" className="relative">
              Market Demand
              {demands.length > 0 && (
                <span className="ml-1.5 inline-flex items-center justify-center w-4 h-4 text-[10px] font-bold rounded-full bg-rose-500 text-white">
                  {demands.length > 9 ? "9+" : demands.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="catalog">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
                  <Card>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-xl flex items-center gap-2">
                          <Store className="h-5 w-5 text-primary" /> Create Merchant
                        </CardTitle>
                        <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20">STEP 1</span>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <form onSubmit={merchant} className="space-y-4">
                        <div className="space-y-2">
                          <Label htmlFor="name">Merchant Name</Label>
                          <Input id="name" name="name" placeholder="Sentinel Audio" required />
                        </div>
                        <Button type="submit" className="w-full">Initialize Merchant</Button>
                      </form>
                    </CardContent>
                  </Card>
                </motion.div>

                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                  <Card className={!merchantId ? "opacity-50 pointer-events-none transition-opacity" : "transition-opacity"}>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-xl flex items-center gap-2">
                          <Package className="h-5 w-5 text-primary" /> Catalog
                        </CardTitle>
                        <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20">STEP 2</span>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <form onSubmit={product} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label>SKU</Label>
                            <Input name="sku" defaultValue="SONY-XM4" required />
                          </div>
                          <div className="space-y-2">
                            <Label>Product Name</Label>
                            <Input name="name" defaultValue="Sony WH-1000XM4" required />
                          </div>
                          <div className="space-y-2">
                            <Label>Brand</Label>
                            <Input name="brand" defaultValue="Sony" />
                          </div>
                          <div className="space-y-2">
                            <Label>Category</Label>
                            <Input name="category" defaultValue="Headphones" required />
                          </div>
                          <div className="space-y-2">
                            <Label>Base Price (INR)</Label>
                            <Input name="price" type="number" defaultValue="29990" required />
                          </div>
                          <div className="space-y-2">
                            <Label>Variant Color</Label>
                            <Input name="color" defaultValue="Midnight Blue" />
                          </div>
                        </div>
                        <Button type="submit" className="w-full" disabled={!merchantId}>Add Product</Button>
                      </form>
                    </CardContent>
                  </Card>
                </motion.div>
              </div>

              <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                  <Card className={!productId ? "opacity-50 pointer-events-none transition-opacity" : "transition-opacity"}>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-xl flex items-center gap-2">
                          <Database className="h-5 w-5 text-primary" /> Inventory
                        </CardTitle>
                        <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20">STEP 3</span>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <form onSubmit={inventory} className="space-y-4">
                        <div className="space-y-2">
                          <Label>Available Quantity</Label>
                          <Input name="available" type="number" min="0" defaultValue="150" required />
                        </div>
                        <Button type="submit" className="w-full" disabled={!productId}>Commit Stock Level</Button>
                      </form>
                    </CardContent>
                  </Card>
                </motion.div>

                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
                  <Card className={`border-destructive/50 ${!productId ? "opacity-50 pointer-events-none transition-opacity" : "transition-opacity"}`}>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-xl flex items-center gap-2 text-destructive">
                          <ShieldAlert className="h-5 w-5 text-destructive" /> Policy Boundaries
                        </CardTitle>
                        <span className="inline-flex items-center rounded-md bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive ring-1 ring-inset ring-destructive/20">STEP 4</span>
                      </div>
                      <CardDescription>These constraints are cryptographically bound. Agents cannot violate them.</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <form onSubmit={policy} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label>Base Price (INR)</Label>
                            <Input name="base" type="number" defaultValue="29990" required />
                          </div>
                          <div className="space-y-2">
                            <Label>Absolute Floor Price (INR)</Label>
                            <Input name="floor" type="number" defaultValue="18900" required className="border-destructive/30 focus-visible:ring-destructive" />
                          </div>
                          <div className="space-y-2">
                            <Label>Max Discount (%)</Label>
                            <Input name="discount" type="number" step="0.01" defaultValue="40" required />
                          </div>
                        </div>
                        <div className="flex items-center space-x-2 pt-2 pb-4">
                          <input type="checkbox" id="negotiation" name="negotiation" className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary" defaultChecked />
                          <Label htmlFor="negotiation">Enable AI Negotiation (Max 3 rounds)</Label>
                        </div>
                        <Button type="submit" variant="destructive" className="w-full" disabled={!productId}>
                          Activate Immutable Policy
                        </Button>
                      </form>
                    </CardContent>
                  </Card>
                </motion.div>
              </div>
            </div>
            
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="mt-6">
              <Card className="bg-black/40 border-primary/20 backdrop-blur-sm">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-mono flex items-center gap-2 text-primary/80">
                      <Code className="h-4 w-4" /> Agent-Readable Data Transfer Object
                    </CardTitle>
                    <Button size="sm" variant="outline" className="h-7 text-xs border-primary/30 text-primary hover:bg-primary/10" disabled={!merchantId} onClick={() => call(`/api/merchants/${merchantId}/catalog`)}>
                      Fetch Current State
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <pre className="p-4 rounded-lg bg-black/60 border border-primary/10 text-xs font-mono text-green-400 overflow-auto max-h-[300px]">
                    {output}
                  </pre>
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>

          <TabsContent value="campaigns">
            <Card className="border-primary/20 bg-card/60 backdrop-blur-sm">
              <CardHeader>
                <div className="flex items-center gap-2 text-primary">
                  <Target className="w-5 h-5" />
                  <CardTitle>Opportunity Detector</CardTitle>
                </div>
                <CardDescription>AI proactively identifies revenue opportunities in your catalog.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 border border-primary/30 rounded-lg bg-primary/5 flex items-start gap-4">
                  <div className="p-2 bg-primary/10 rounded-full">
                    <TrendingUp className="w-6 h-6 text-primary" />
                  </div>
                  <div className="flex-1">
                    <h4 className="font-semibold text-lg flex items-center gap-2">
                      High Inventory Alert: SONY-XM4
                      <Badge className="bg-blue-500/20 text-blue-500 border-blue-500/30">Action Recommended</Badge>
                    </h4>
                    <p className="text-muted-foreground mt-1">You have 150 units of Sony WH-1000XM4. Conversion rate dropped by 12% in the last 48 hours.</p>
                    <div className="mt-4 p-3 bg-background/50 rounded-md border border-border/50">
                      <p className="font-mono text-sm"><span className="text-primary">Agent Proposal:</span> Enable a dynamic discount up to 35% for premium buyers to clear 50 units. Expected GMV lift: ₹945,000.</p>
                    </div>
                    <div className="mt-4 flex gap-3">
                      <Button className="gap-2" disabled={!isAiReady}>
                        <Zap className="w-4 h-4" /> Approve Campaign
                      </Button>
                      <Button variant="outline">Dismiss</Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Market Demand Tab ─────────────────────────────────────────── */}
          <TabsContent value="demand">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="border-rose-500/20 bg-card/60 backdrop-blur-sm">
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-rose-400">
                      <SearchX className="w-5 h-5" />
                      <CardTitle>Market Demand Intelligence</CardTitle>
                    </div>
                    <div className="flex items-center gap-2">
                      {demands.length > 0 && (
                        <Badge className="bg-rose-500/20 text-rose-400 border-rose-500/30">
                          {demands.length} missed {demands.length === 1 ? "search" : "searches"}
                        </Badge>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs border-rose-500/30 text-rose-400 hover:bg-rose-500/10"
                        disabled={!merchantId || demandLoading}
                        onClick={fetchDemand}
                      >
                        {demandLoading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
                        Refresh
                      </Button>
                    </div>
                  </div>
                  <CardDescription>
                    Products buyers searched for but weren&apos;t found in your catalog — ranked by demand.
                    AI price estimates are indicative (not live scraped).
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  {!merchantId && (
                    <div className="p-8 text-center text-muted-foreground text-sm">
                      Create a merchant first to see demand data.
                    </div>
                  )}

                  {merchantId && demandLoading && (
                    <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground text-sm">
                      <Loader2 className="w-4 h-4 animate-spin" /> Loading demand data…
                    </div>
                  )}

                  {merchantId && !demandLoading && demandError && (
                    <div className="p-6 text-center text-rose-400 text-sm">{demandError}</div>
                  )}

                  {merchantId && !demandLoading && !demandError && demands.length === 0 && (
                    <div className="p-10 text-center">
                      <SearchX className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
                      <p className="text-muted-foreground text-sm">No missed searches yet.</p>
                      <p className="text-muted-foreground/60 text-xs mt-1">When buyers search for products not in your catalog, they&apos;ll appear here.</p>
                    </div>
                  )}

                  {merchantId && !demandLoading && demands.length > 0 && (
                    <Table>
                      <TableHeader className="bg-muted/30">
                        <TableRow className="text-xs">
                          <TableHead className="pl-4 w-[40%]">Product Query</TableHead>
                          <TableHead className="text-center">Searches</TableHead>
                          <TableHead>AI Est. Price</TableHead>
                          <TableHead>Last Searched</TableHead>
                          <TableHead className="text-right pr-4">Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody className="text-xs">
                        {demands.map((item, i) => (
                          <TableRow key={item.id} className={i === 0 ? "bg-rose-500/5" : ""}>
                            <TableCell className="pl-4 font-medium capitalize">
                              <div className="flex items-center gap-2">
                                {i === 0 && <Badge className="text-[9px] bg-rose-500/20 text-rose-400 border-rose-500/30 px-1 py-0">HOT</Badge>}
                                {item.product_query}
                              </div>
                            </TableCell>
                            <TableCell className="text-center">
                              <span className="font-bold text-foreground">{item.search_count}</span>
                            </TableCell>
                            <TableCell className="font-mono">
                              {item.estimated_price_inr
                                ? `₹${item.estimated_price_inr.toLocaleString("en-IN")}`
                                : <span className="text-muted-foreground">—</span>}
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {item.last_searched_at
                                ? new Date(item.last_searched_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
                                : "—"}
                            </TableCell>
                            <TableCell className="text-right pr-4">
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 text-xs text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10"
                                onClick={() => dismissDemand(item.id)}
                                title="Dismiss once you've added this product"
                              >
                                <Trash2 className="w-3 h-3 mr-1" /> Dismiss
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
