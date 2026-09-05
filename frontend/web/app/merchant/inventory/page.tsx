"use client";

import { FormEvent, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Database, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

export default function InventoryPage() {
  const [merchantId, setMerchantId] = useState<string | null>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("sp_merchant_id");
    if (stored) {
      setMerchantId(stored);
      loadProducts(stored);
    } else {
      setLoading(false);
    }
  }, []);

  async function loadProducts(id: string) {
    try {
      const res = await apiFetch(`/api/merchants/${id}/products`, { cache: "no-store" });
      const data = await res.json();
      setProducts(Array.isArray(data) ? data : (data.products || []));
    } catch {}
    setLoading(false);
  }

  async function updateStock(productId: string, e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!merchantId) return;
    setUpdating(productId);
    const f = new FormData(e.currentTarget);
    try {
      await apiFetch(`/api/merchants/${merchantId}/inventory/${productId}`, {
        method: "PUT",
        body: JSON.stringify({
          available_quantity: Number(f.get("qty")),
          reserved_quantity: 0
        })
      });
      await loadProducts(merchantId);
    } catch (err) {
      console.error("Update stock failed:", err);
    }
    setUpdating(null);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[40vh]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!merchantId) {
    return (
      <div className="text-center pt-16 space-y-4">
        <Database className="w-10 h-10 text-muted-foreground mx-auto" />
        <h2 className="text-xl font-bold">No merchant configured</h2>
        <p className="text-muted-foreground">Go to <a href="/merchant/dashboard" className="text-blue-400 hover:underline">Dashboard</a> to set up first.</p>
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Inventory Management</h1>
        <p className="text-muted-foreground text-sm mt-1">Track stock levels — low inventory triggers campaign opportunity signals.</p>
      </div>

      {products.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="pt-8 pb-8 text-center">
            <Database className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No products to manage. <a href="/merchant/catalog" className="text-blue-400 hover:underline">Add products first.</a></p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {products.map((p: any) => {
            const qty = p.available_quantity ?? 0;
            const isLow = qty <= 15;
            const isOut = qty === 0;
            return (
              <Card key={p.id} className={`border-border/50 ${isOut ? "border-red-500/30" : isLow ? "border-amber-500/30" : ""}`}>
                <CardContent className="pt-6">
                  <div className="flex flex-col md:flex-row md:items-center gap-4 justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold">{p.name}</h3>
                        {isOut ? (
                          <Badge className="bg-red-500/10 text-red-400 border-red-500/20">OUT OF STOCK</Badge>
                        ) : isLow ? (
                          <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20">
                            <AlertTriangle className="w-3 h-3 mr-1" /> LOW STOCK
                          </Badge>
                        ) : (
                          <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                            <CheckCircle2 className="w-3 h-3 mr-1" /> IN STOCK
                          </Badge>
                        )}
                      </div>
                      <div className="flex gap-6 text-sm text-muted-foreground">
                        <span>SKU: <span className="font-mono">{p.sku}</span></span>
                        <span>Available: <span className="font-bold text-foreground">{qty}</span></span>
                        <span>Reserved: <span className="font-mono">{p.reserved_quantity ?? 0}</span></span>
                      </div>
                      {isLow && !isOut && (
                        <p className="text-xs text-amber-400 mt-2 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" />
                          Low inventory may trigger campaign opportunity suggestions
                        </p>
                      )}
                    </div>
                    <form onSubmit={(e) => updateStock(p.id, e)} className="flex items-end gap-2">
                      <div className="space-y-1">
                        <Label className="text-xs">New Quantity</Label>
                        <Input name="qty" type="number" min="0" defaultValue={qty} className="w-24" />
                      </div>
                      <Button type="submit" size="sm" disabled={updating === p.id} className="bg-blue-600 hover:bg-blue-700">
                        {updating === p.id ? <Loader2 className="w-3 h-3 animate-spin" /> : "Update"}
                      </Button>
                    </form>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
