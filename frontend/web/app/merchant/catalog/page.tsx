"use client";

import { FormEvent, useEffect, useState, ChangeEvent, DragEvent } from "react";
import { motion } from "framer-motion";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Package, Plus, Eye, Bot, Loader2, Upload, FileText,
  Download, CheckCircle2, AlertCircle, Sparkles, Trash2, ArrowRight,
  FileType, FileCheck
} from "lucide-react";

interface ParsedProduct {
  sku: string;
  name: string;
  brand: string;
  category: string;
  price: number;
  floor_price?: number;
  stock?: number;
  color?: string;
  description?: string;
}

export default function CatalogPage() {
  const [merchantId, setMerchantId] = useState<string | null>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [previewProduct, setPreviewProduct] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [importText, setImportText] = useState("");
  const [parsedProducts, setParsedProducts] = useState<ParsedProduct[]>([]);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isParsingDoc, setIsParsingDoc] = useState(false);
  const [activeFileName, setActiveFileName] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("sp_merchant_id");
    if (stored) {
      setMerchantId(stored);
      loadProducts(stored);
    } else {
      const defaultId = "10000000-0000-0000-0000-000000000001";
      setMerchantId(defaultId);
      loadProducts(defaultId);
    }
  }, []);

  async function loadProducts(id: string) {
    try {
      const res = await apiFetch(`/api/merchants/${id}/products`);
      const data = await res.json();
      setProducts(Array.isArray(data) ? data : (data.products || []));
    } catch {}
    setLoading(false);
  }

  // Parse text content into structured product items
  function parseContent(content: string) {
    const text = content.trim();
    if (!text) {
      setParsedProducts([]);
      return;
    }

    try {
      // 1. Try parsing JSON
      if (text.startsWith("{") || text.startsWith("[")) {
        const json = JSON.parse(text);
        const list = Array.isArray(json) ? json : [json];
        const normalized: ParsedProduct[] = list.map((item, idx) => ({
          sku: String(item.sku || `SKU-${Date.now()}-${idx + 1}`),
          name: String(item.name || item.product_name || "New Product"),
          brand: String(item.brand || "Generic"),
          category: String(item.category || "General"),
          price: Number(item.price || item.base_price || 999),
          floor_price: item.floor_price ? Number(item.floor_price) : undefined,
          stock: item.stock || item.available_quantity ? Number(item.stock || item.available_quantity) : 50,
          color: String(item.color || item.variant || "Standard"),
          description: String(item.description || "")
        }));
        setParsedProducts(normalized);
        setImportStatus(`Successfully parsed ${normalized.length} product(s) from JSON.`);
        return;
      }
    } catch {}

    // 2. Key-Value & Block Text Parser (supports multiple blocks separated by '---' or double newlines)
    const blocks = text.split(/\n\s*---\s*\n|\n\s*\n(?=[A-Za-z0-9_-]+:)/).filter(b => b.trim());
    const extracted: ParsedProduct[] = [];

    for (let i = 0; i < blocks.length; i++) {
      const block = blocks[i];
      const lines = block.split("\n");
      const map: Record<string, string> = {};

      for (const line of lines) {
        const idx = line.indexOf(":");
        if (idx > -1) {
          const key = line.slice(0, idx).trim().toLowerCase().replace(/[\s_-]/g, "");
          const val = line.slice(idx + 1).trim();
          map[key] = val;
        }
      }

      if (map.name || map.productname || map.sku || map.price || map.baseprice) {
        const basePrice = Number(map.price || map.baseprice || map.mrp || 999);
        extracted.push({
          sku: map.sku || `SKU-${Date.now().toString().slice(-4)}-${i + 1}`,
          name: map.name || map.productname || `Imported Item ${i + 1}`,
          brand: map.brand || map.make || "Generic",
          category: map.category || map.type || "General",
          price: isNaN(basePrice) ? 999 : basePrice,
          floor_price: map.floorprice || map.minprice ? Number(map.floorprice || map.minprice) : undefined,
          stock: map.stock || map.qty || map.quantity ? Number(map.stock || map.qty || map.quantity) : 50,
          color: map.color || map.variant || "Standard",
          description: map.description || map.desc || ""
        });
      }
    }

    if (extracted.length > 0) {
      setParsedProducts(extracted);
      setImportStatus(`Successfully extracted ${extracted.length} product(s) from specification.`);
    } else {
      setParsedProducts([]);
      setImportStatus("No standard fields detected (Name, Brand, Price). You can edit the text directly.");
    }
  }

  async function processFile(file: File) {
    setActiveFileName(file.name);
    setIsParsingDoc(true);
    setImportStatus(`Extracting specifications from "${file.name}"...`);

    const isBinary = file.name.endsWith(".pdf") ||
      file.name.endsWith(".docx") ||
      file.name.endsWith(".doc") ||
      file.type.includes("pdf") ||
      file.type.includes("word") ||
      file.type.includes("officedocument");

    try {
      if (isBinary) {
        const formData = new FormData();
        formData.append("file", file);
        const res = await apiFetch("/api/merchants/parse-document", {
          method: "POST",
          body: formData
        });
        const data = await res.json();
        if (data.extracted_text) {
          setImportText(data.extracted_text);
        }
        if (Array.isArray(data.products) && data.products.length > 0) {
          setParsedProducts(data.products);
          setImportStatus(`Successfully parsed ${data.products.length} product(s) from "${file.name}".`);
        } else {
          setImportStatus(`Document text extracted. Please verify parsed fields below.`);
        }
      } else {
        const reader = new FileReader();
        reader.onload = (event) => {
          const text = String(event.target?.result || "");
          setImportText(text);
          parseContent(text);
        };
        reader.readAsText(file);
      }
    } catch (err: any) {
      console.error("Doc upload error:", err);
      setImportStatus(`Error parsing document: ${err.message || "Failed to process file"}`);
    } finally {
      setIsParsingDoc(false);
    }
  }

  function handleFileUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  }

  function handleDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  }

  function downloadSampleTemplate() {
    const sample = `SKU: APPL-MBP-16
Name: Apple MacBook Pro 16 M3 Max
Brand: Apple
Category: Laptops
Price: 349900
FloorPrice: 320000
Stock: 25
Color: Space Black
Description: Flagship performance laptop with Liquid Retina XDR display and M3 Max silicon.
---
SKU: NIKE-AIR-J1
Name: Nike Air Jordan 1 High OG
Brand: Nike
Category: Footwear
Price: 16995
FloorPrice: 15500
Stock: 40
Color: Chicago Red / White
Description: Iconic high-top basketball sneaker with premium leather upper.
---
SKU: SONY-WH-XM5
Name: Sony WH-1000XM5 Wireless Headphones
Brand: Sony
Category: Audio
Price: 24499
FloorPrice: 22000
Stock: 30
Color: Silver
Description: Industry-leading noise canceling headphones with dual processors.`;

    const blob = new Blob([sample], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sentinel_product_template.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function addProduct(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!merchantId) return;
    setIsSubmitting(true);
    const f = new FormData(e.currentTarget);
    const price = Number(f.get("price"));
    const floor = Number(f.get("floor_price")) || Math.round(price * 0.9);

    try {
      const res = await apiFetch(`/api/merchants/${merchantId}/products`, {
        method: "POST",
        body: JSON.stringify({
          sku: f.get("sku"),
          name: f.get("name"),
          brand: f.get("brand"),
          category: f.get("category"),
          description: f.get("description"),
          base_price_minor: price * 100,
          variants: [{ variant_key: "default", name: "Default", attributes: { color: String(f.get("color") || "Default") } }]
        })
      });
      const prod = await res.json();
      if (prod.id) {
        // Auto-seed policy
        await apiFetch(`/api/merchants/${merchantId}/policies`, {
          method: "POST",
          body: JSON.stringify({
            scope: "PRODUCT",
            scope_reference: prod.id,
            base_price_minor: price * 100,
            minimum_sale_price_minor: floor * 100,
            maximum_discount_percent: 15,
            negotiation_enabled: true,
            max_negotiation_rounds: 3,
            upsell_enabled: true,
            cross_sell_enabled: true,
            valid_from: new Date().toISOString(),
            status: "ACTIVE"
          })
        }).catch(() => {});
      }
      setShowForm(false);
      await loadProducts(merchantId);
    } catch (err) {
      console.error("Add product failed:", err);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function commitBatchImport() {
    if (!merchantId || parsedProducts.length === 0) return;
    setIsSubmitting(true);

    for (const item of parsedProducts) {
      try {
        const floorPrice = item.floor_price || Math.round(item.price * 0.9);
        const res = await apiFetch(`/api/merchants/${merchantId}/products`, {
          method: "POST",
          body: JSON.stringify({
            sku: item.sku,
            name: item.name,
            brand: item.brand,
            category: item.category,
            description: item.description || `Agent-verified ${item.name}`,
            base_price_minor: item.price * 100,
            variants: [{ variant_key: "default", name: "Default", attributes: { color: item.color || "Standard" } }]
          })
        });
        const prod = await res.json();
        if (prod.id) {
          // Inventory
          if (item.stock) {
            await apiFetch(`/api/merchants/${merchantId}/inventory/${prod.id}`, {
              method: "PUT",
              body: JSON.stringify({ available_quantity: item.stock, reserved_quantity: 0 })
            }).catch(() => {});
          }
          // Policy
          await apiFetch(`/api/merchants/${merchantId}/policies`, {
            method: "POST",
            body: JSON.stringify({
              scope: "PRODUCT",
              scope_reference: prod.id,
              base_price_minor: item.price * 100,
              minimum_sale_price_minor: floorPrice * 100,
              maximum_discount_percent: 15,
              negotiation_enabled: true,
              max_negotiation_rounds: 3,
              upsell_enabled: true,
              cross_sell_enabled: true,
              valid_from: new Date().toISOString(),
              status: "ACTIVE"
            })
          }).catch(() => {});
        }
      } catch (e) {
        console.error("Failed importing", item.sku, e);
      }
    }

    setIsSubmitting(false);
    setShowForm(false);
    setParsedProducts([]);
    setImportText("");
    setActiveFileName(null);
    await loadProducts(merchantId);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[40vh]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Product Catalog</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Machine-readable inventory with Z3 security policies for autonomous AI buyer discovery.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => setShowForm(!showForm)}
            className="gap-2 bg-blue-600 hover:bg-blue-700 text-white"
          >
            <Plus className="w-4 h-4" /> {showForm ? "Close Panel" : "Add or Import Products"}
          </Button>
        </div>
      </div>

      {/* Add / Import Panel */}
      {showForm && (
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="border-blue-500/30 bg-card/60 backdrop-blur-md">
            <CardHeader className="pb-3 border-b border-border/40">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-blue-400" /> Catalog Ingestion Hub
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Upload any document (<strong>PDF, Word DOCX, TXT, CSV, JSON</strong>) or enter manually.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={downloadSampleTemplate}
                  className="text-xs gap-1.5 h-8 border-border/60"
                >
                  <Download className="w-3.5 h-3.5" /> Sample TXT Template
                </Button>
              </div>
            </CardHeader>

            <CardContent className="pt-4">
              <Tabs defaultValue="document" className="space-y-4">
                <TabsList className="bg-background/80 border border-border/50">
                  <TabsTrigger value="document" className="gap-2 text-xs">
                    <FileType className="w-4 h-4 text-blue-400" /> Upload Any Document (PDF / DOCX / TXT / JSON)
                  </TabsTrigger>
                  <TabsTrigger value="manual" className="gap-2 text-xs">
                    <Plus className="w-4 h-4 text-emerald-400" /> Single Product Form
                  </TabsTrigger>
                </TabsList>

                {/* Tab 1: File / Spec Import */}
                <TabsContent value="document" className="space-y-4">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Left: Input & Dropzone */}
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <Label className="text-xs font-semibold">Upload Document or Paste Content</Label>
                        <span className="text-[11px] text-muted-foreground font-mono">Supports PDF, DOCX, TXT, JSON, CSV</span>
                      </div>

                      {/* Dropzone */}
                      <label
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={handleDrop}
                        className={`border-2 border-dashed rounded-xl p-5 flex flex-col items-center justify-center cursor-pointer transition-all ${
                          isDragging
                            ? "border-blue-400 bg-blue-500/15"
                            : "border-border/60 hover:border-blue-500/50 bg-background/30 hover:bg-blue-500/5"
                        }`}
                      >
                        {isParsingDoc ? (
                          <div className="flex flex-col items-center space-y-2">
                            <Loader2 className="w-7 h-7 text-blue-400 animate-spin" />
                            <span className="text-xs font-medium text-blue-300">Extracting specs from document...</span>
                          </div>
                        ) : activeFileName ? (
                          <div className="flex flex-col items-center space-y-1 text-center">
                            <FileCheck className="w-7 h-7 text-emerald-400 mb-1" />
                            <span className="text-xs font-semibold text-foreground">{activeFileName}</span>
                            <span className="text-[10px] text-muted-foreground">Click or drop another file to replace</span>
                          </div>
                        ) : (
                          <div className="flex flex-col items-center text-center">
                            <Upload className="w-7 h-7 text-blue-400 mb-2" />
                            <span className="text-xs font-semibold text-foreground">Click or Drag &amp; Drop Any Document</span>
                            <span className="text-[11px] text-muted-foreground mt-1">
                              Accepts <strong>.pdf</strong>, <strong>.docx</strong>, <strong>.txt</strong>, <strong>.json</strong>, <strong>.csv</strong>
                            </span>
                          </div>
                        )}
                        <input
                          type="file"
                          accept=".pdf,.docx,.doc,.txt,.json,.csv,.text,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                          onChange={handleFileUpload}
                          className="hidden"
                          disabled={isParsingDoc}
                        />
                      </label>

                      {/* Raw Text Box */}
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Or Paste Specification Text / Extracted Document Content:</Label>
                        <Textarea
                          value={importText}
                          onChange={(e) => {
                            setImportText(e.target.value);
                            parseContent(e.target.value);
                          }}
                          placeholder={`SKU: APPL-IPHONE-15\nName: Apple iPhone 15 Pro Max\nBrand: Apple\nCategory: Smartphones\nPrice: 159900\nFloorPrice: 145000\nStock: 25\nColor: Natural Titanium\nDescription: Titanium flagship with A17 Pro.`}
                          className="min-h-[160px] font-mono text-xs bg-background/50 leading-relaxed"
                        />
                      </div>

                      {importStatus && (
                        <div className="p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-xs text-blue-300 flex items-center gap-2">
                          <Sparkles className="w-4 h-4 shrink-0" />
                          <span>{importStatus}</span>
                        </div>
                      )}
                    </div>

                    {/* Right: Parsed Preview */}
                    <div className="space-y-3 flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <Label className="text-xs font-semibold">Extracted Structured Catalog ({parsedProducts.length})</Label>
                          {parsedProducts.length > 0 && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setParsedProducts([]);
                                setImportText("");
                                setActiveFileName(null);
                                setImportStatus(null);
                              }}
                              className="h-6 text-[11px] text-red-400 hover:text-red-300 gap-1 p-1"
                            >
                              <Trash2 className="w-3 h-3" /> Clear
                            </Button>
                          )}
                        </div>

                        {parsedProducts.length === 0 ? (
                          <div className="h-[240px] border border-border/40 rounded-xl bg-background/20 flex flex-col items-center justify-center p-6 text-center space-y-2">
                            <FileText className="w-8 h-8 text-muted-foreground/40" />
                            <p className="text-xs text-muted-foreground">
                              Upload a PDF, Word document, or TXT file on the left to see live structured preview.
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1">
                            {parsedProducts.map((p, idx) => (
                              <Card key={idx} className="border-border/60 bg-background/40">
                                <CardContent className="p-3 text-xs space-y-1.5">
                                  <div className="flex items-start justify-between">
                                    <div>
                                      <p className="font-semibold text-foreground">{p.name}</p>
                                      <p className="text-[11px] text-muted-foreground">{p.brand} • {p.category}</p>
                                    </div>
                                    <div className="text-right">
                                      <p className="font-bold text-emerald-400 font-mono">₹{p.price.toLocaleString("en-IN")}</p>
                                      {p.floor_price && (
                                        <p className="text-[10px] text-muted-foreground font-mono">Floor: ₹{p.floor_price.toLocaleString("en-IN")}</p>
                                      )}
                                    </div>
                                  </div>
                                  <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground pt-1 border-t border-border/30">
                                    <span>SKU: <strong className="text-foreground font-mono">{p.sku}</strong></span>
                                    <span>Stock: <strong className="text-foreground">{p.stock || 50} units</strong></span>
                                    <span>Color: <strong className="text-foreground">{p.color}</strong></span>
                                  </div>
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Action */}
                      <div className="pt-3 border-t border-border/40">
                        <Button
                          onClick={commitBatchImport}
                          disabled={parsedProducts.length === 0 || isSubmitting}
                          className="w-full bg-blue-600 hover:bg-blue-700 text-white gap-2"
                        >
                          {isSubmitting ? (
                            <><Loader2 className="w-4 h-4 animate-spin" /> Ingesting to Database...</>
                          ) : (
                            <><CheckCircle2 className="w-4 h-4" /> Import {parsedProducts.length} Product(s) into Live Catalog</>
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                </TabsContent>

                {/* Tab 2: Manual Form */}
                <TabsContent value="manual">
                  <form onSubmit={addProduct} className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="space-y-1.5">
                        <Label htmlFor="mSku">SKU</Label>
                        <Input id="mSku" name="sku" placeholder="SONY-XM5" required className="bg-background/50" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="mName">Product Name</Label>
                        <Input id="mName" name="name" placeholder="Sony WH-1000XM5" required className="bg-background/50" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="mBrand">Brand</Label>
                        <Input id="mBrand" name="brand" placeholder="Sony" className="bg-background/50" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="mCat">Category</Label>
                        <Input id="mCat" name="category" placeholder="Headphones" required className="bg-background/50" />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                      <div className="space-y-1.5">
                        <Label htmlFor="mPrice">Base Price (₹)</Label>
                        <Input id="mPrice" name="price" type="number" placeholder="24499" required className="bg-background/50" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="mFloor">Floor Price (₹)</Label>
                        <Input id="mFloor" name="floor_price" type="number" placeholder="22000" className="bg-background/50" />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="mCol">Color / Variant</Label>
                        <Input id="mCol" name="color" placeholder="Silver" className="bg-background/50" />
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="mDesc">Description</Label>
                      <Input id="mDesc" name="description" placeholder="Premium noise-cancelling headphones..." className="bg-background/50" />
                    </div>

                    <div className="flex gap-3 pt-2">
                      <Button type="submit" disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white">
                        {isSubmitting ? "Adding..." : "Add to Catalog & Initialize Policy"}
                      </Button>
                      <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
                        Cancel
                      </Button>
                    </div>
                  </form>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Products Table */}
      {products.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="pt-8 pb-8 text-center space-y-3">
            <Package className="w-8 h-8 text-muted-foreground mx-auto" />
            <p className="text-muted-foreground text-sm">No products in catalog yet.</p>
            <Button size="sm" onClick={() => setShowForm(true)} className="bg-blue-600 hover:bg-blue-700">
              Add or Import First Product
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-border/50 overflow-hidden">
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow>
                <TableHead className="pl-4">Product</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Base Price</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right pr-4">Agent Capabilities</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.map((p: any) => (
                <TableRow key={p.id}>
                  <TableCell className="pl-4">
                    <div>
                      <p className="font-semibold text-foreground">{p.name}</p>
                      <p className="text-xs text-muted-foreground">{p.brand || "Generic"}</p>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{p.sku}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">{p.category}</Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono font-semibold text-emerald-400">
                    ₹{((p.base_price_minor || p.current_price_minor) / 100).toLocaleString("en-IN")}
                  </TableCell>
                  <TableCell>
                    <Badge className="text-[10px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                      ACTIVE
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right pr-4">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setPreviewProduct(previewProduct?.id === p.id ? null : p)}
                      className="gap-1.5 text-xs text-blue-400 hover:text-blue-300 hover:bg-blue-500/10"
                    >
                      <Bot className="w-3.5 h-3.5" /> Agent DTO
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Agent-Readable DTO Drawer */}
      {previewProduct && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="border-emerald-500/30 bg-emerald-500/5">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2 text-emerald-400">
                  <Bot className="w-4 h-4" /> Agent-Readable Machine DTO ({previewProduct.name})
                </CardTitle>
                <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px]">
                  PROVENANCE: VERIFIED_DB
                </Badge>
              </div>
              <CardDescription className="text-xs">
                This structured schema is exposed to autonomous AI buyers without exposing your internal minimum floor prices.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <pre className="text-xs font-mono bg-black/50 p-4 rounded-lg overflow-x-auto border border-emerald-500/20 text-emerald-300">
{JSON.stringify({
  product_id: previewProduct.id,
  name: previewProduct.name,
  brand: previewProduct.brand,
  category: previewProduct.category,
  current_price_minor: previewProduct.base_price_minor || previewProduct.current_price_minor,
  currency: "INR",
  condition: "NEW",
  inventory_status: "IN_STOCK",
  negotiation_enabled: true,
  delivery_capability: "MERCHANT_DEFINED",
  provenance: "MERCHANT_CATALOG"
}, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </motion.div>
      )}
    </motion.div>
  );
}
