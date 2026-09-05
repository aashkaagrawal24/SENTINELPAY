"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ShoppingCart, CheckCircle2, Clock, XCircle, Package, Boxes } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Order = {
  id: string;
  product: string;
  sku: string;
  amount: number;
  status: string;
  date: number;
  order_type: string;
  bulk_rfq_id?: string;
  quantity: number;
  unit_price_inr?: number;
  strategy?: string;
  campaign?: string;
};

import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState } from "@/components/common/empty-state";
import { RefreshCw } from "lucide-react";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchOrders = async (showRefresh = false) => {
    const merchantId = localStorage.getItem("sp_merchant_id");
    if (!merchantId) { setLoading(false); return; }
    if (showRefresh) setRefreshing(true);
    try {
      const res = await apiFetch(`/api/merchants/${merchantId}/orders`);
      const data = await res.json();
      setOrders(data.orders || []);
    } catch (e) { console.error(e); }
    setLoading(false);
    if (showRefresh) setRefreshing(false);
  };

  useEffect(() => {
    fetchOrders();
    const merchantId = localStorage.getItem("sp_merchant_id");
    if (!merchantId) return;
    const evtSource = new EventSource(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/merchants/${merchantId}/events/stream`);
    evtSource.addEventListener("AUDIT_EVENT", () => fetchOrders());
    return () => evtSource.close();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <ShoppingCart className="h-10 w-10 text-blue-400/50" />
          <p className="text-muted-foreground text-sm font-mono">Loading canonical orders...</p>
        </div>
      </div>
    );
  }

  const retailOrders = orders.filter(o => o.order_type !== "BULK");
  const bulkOrders = orders.filter(o => o.order_type === "BULK");

  const OrderTable = ({ rows }: { rows: Order[] }) => (
    rows.length === 0 ? (
      <EmptyState
        title="No Orders Found"
        description="Orders appear here in real time as AI buyers discover your catalog, negotiate bounds, and complete Razorpay transactions."
        icon={ShoppingCart}
      />
    ) : (
      <div className="overflow-x-auto">
        <Table>
          <TableHeader className="bg-card/40">
            <TableRow className="border-border/40 hover:bg-transparent">
              <TableHead className="font-mono text-xs text-muted-foreground">Order ID</TableHead>
              <TableHead className="font-mono text-xs text-muted-foreground">Product & SKU</TableHead>
              <TableHead className="font-mono text-xs text-muted-foreground text-right">Qty</TableHead>
              <TableHead className="font-mono text-xs text-muted-foreground text-right">Unit Price</TableHead>
              <TableHead className="font-mono text-xs text-muted-foreground text-right">Settled Amount</TableHead>
              <TableHead className="font-mono text-xs text-muted-foreground">Commerce Mode</TableHead>
              <TableHead className="font-mono text-xs text-muted-foreground">Status</TableHead>
              <TableHead className="font-mono text-xs text-muted-foreground text-right">Timestamp</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((order) => (
              <TableRow key={order.id} className="border-border/30 hover:bg-accent/40 transition-colors">
                <TableCell className="font-mono text-xs text-primary font-medium">
                  {order.id.slice(0, 8)}…
                </TableCell>
                <TableCell>
                  <div className="font-medium text-sm text-foreground">{order.product}</div>
                  <div className="text-[11px] font-mono text-muted-foreground">{order.sku}</div>
                </TableCell>
                <TableCell className="text-right font-mono text-xs font-semibold">{order.quantity}</TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">
                  {order.unit_price_inr ? `₹${order.unit_price_inr.toLocaleString("en-IN")}` : "—"}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-bold text-foreground">
                  ₹{order.amount.toLocaleString("en-IN")}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={`text-[10px] font-mono flex items-center gap-1 w-fit ${
                    order.order_type === "BULK" 
                      ? "text-purple-400 bg-purple-500/10 border-purple-500/20" 
                      : "text-blue-400 bg-blue-500/10 border-blue-500/20"
                  }`}>
                    {order.order_type === "BULK" ? <Boxes className="w-2.5 h-2.5" /> : <ShoppingCart className="w-2.5 h-2.5" />}
                    {order.order_type}
                  </Badge>
                </TableCell>
                <TableCell>
                  <StatusBadge status={order.status} />
                </TableCell>
                <TableCell className="text-right font-mono text-[11px] text-muted-foreground">
                  {new Date(order.date).toLocaleDateString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    )
  );

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <span>Authoritative Orders</span>
            <span className="text-xs font-mono font-normal px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20">
              {orders.length} TOTAL
            </span>
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Real-time verified transactions scoped to this merchant authenticated tenant.
          </p>
        </div>

        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => fetchOrders(true)} 
          disabled={refreshing}
          className="gap-2 text-xs font-mono"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-primary" : ""}`} />
          <span>Refresh Feed</span>
        </Button>
      </div>

      <Tabs defaultValue="all" className="space-y-4">
        <TabsList className="bg-card/60 p-1 border border-border/40">
          <TabsTrigger value="all" className="text-xs font-mono">All Orders ({orders.length})</TabsTrigger>
          <TabsTrigger value="retail" className="gap-1.5 text-xs font-mono">
            <ShoppingCart className="h-3 w-3" /> Retail ({retailOrders.length})
          </TabsTrigger>
          <TabsTrigger value="bulk" className="gap-1.5 text-xs font-mono">
            <Boxes className="h-3 w-3" /> Bulk Procurement ({bulkOrders.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all">
          <Card className="glass-panel border-border/50 overflow-hidden">
            <OrderTable rows={orders} />
          </Card>
        </TabsContent>
        <TabsContent value="retail">
          <Card className="glass-panel border-border/50 overflow-hidden">
            <OrderTable rows={retailOrders} />
          </Card>
        </TabsContent>
        <TabsContent value="bulk">
          <Card className="glass-panel border-border/50 overflow-hidden">
            <OrderTable rows={bulkOrders} />
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
