"use client";

import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { apiFetch } from "@/lib/api";
import {
  Card, CardContent, CardHeader, CardTitle
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  TrendingDown, TrendingUp, Zap, ShieldCheck, Brain, AlertTriangle,
  Package, Loader2, ChevronDown, ChevronUp, Edit3, CheckCircle2,
  BarChart3, Target, Sparkles, Plus, X
} from "lucide-react";

interface SimRow {
  discount_percent: number;
  new_price_inr: number;
  predicted_sales: number;
  profit_per_unit_inr: number;
  expected_total_profit_inr: number;
  stock_cleared_percent: number;
  is_margin_safe: boolean;
  is_optimal: boolean;
}

interface AIPolicy {
  policy_code: string;
  objective: string;
  recommended_discount_percent: number;
  recommended_price_inr: number;
  recommended_price_minor: number;
  floor_price_inr: number;
  floor_price_minor: number;
  duration_days: number;
  order_limit: number;
  target_segment: string;
  minimum_margin_percent: number;
  why_reason: string;
  expected_sales: number;
  expected_sales_lift_percent: number;
  stock_cleared_percent: number;
  expected_total_profit_inr: number;
  adaptive_rules: Record<string, string>;
}

interface ProductIntelligence {
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  base_price_inr: number;
  base_price_minor: number;
  cost_price_inr: number;
  cost_price_minor: number;
  available_quantity: number;
  inventory_pressure: number;
  has_excess_inventory: boolean;
  overstock_probability: number;
  forecast_30d_demand: number;
  elasticity: number;
  active_policy: Record<string, any> | null;
  recommended_policy: AIPolicy;
  simulation_matrix: SimRow[];
}

interface SimResult {
  proposed_discount_percent: number;
  proposed_price_inr: number;
  predicted_sales: number;
  expected_total_profit_inr: number;
  stock_cleared_percent: number;
  remaining_stock: number;
  overstock_risk_after_percent: number;
  safety_status: string;
  safety_message: string;
  is_safe: boolean;
}

export default function PoliciesPage() {
  const [merchantId, setMerchantId] = useState<string | null>(null);
  const [intelligence, setIntelligence] = useState<{
    summary: any;
    products: ProductIntelligence[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedProduct, setExpandedProduct] = useState<string | null>(null);
  const [editingProduct, setEditingProduct] = useState<ProductIntelligence | null>(null);
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [appliedIds, setAppliedIds] = useState<Set<string>>(new Set());
  const simTimeout = useRef<NodeJS.Timeout | null>(null);

  // Edit form state
  const [editDiscount, setEditDiscount] = useState<number>(0);
  const [editDuration, setEditDuration] = useState<number>(5);
  const [editOrderLimit, setEditOrderLimit] = useState<number>(100);

  useEffect(() => {
    const stored = localStorage.getItem("sp_merchant_id");
    if (stored) {
      setMerchantId(stored);
      loadIntelligence(stored);
    } else {
      setLoading(false);
    }
  }, []);

  async function loadIntelligence(id: string) {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/merchants/${id}/pricing-intelligence`, { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setIntelligence(data);
        // Auto-expand first product with excess inventory
        const first = data.products.find((p: ProductIntelligence) => p.has_excess_inventory);
        if (first) setExpandedProduct(first.product_id);
      }
    } finally {
      setLoading(false);
    }
  }

  function openEdit(product: ProductIntelligence) {
    setEditingProduct(product);
    setEditDiscount(product.recommended_policy.recommended_discount_percent);
    setEditDuration(product.recommended_policy.duration_days);
    setEditOrderLimit(product.recommended_policy.order_limit);
    setSimResult(null);
  }

  function closeEdit() {
    setEditingProduct(null);
    setSimResult(null);
  }

  function onEditChange(discount: number, duration: number, orderLimit: number) {
    setEditDiscount(discount);
    setEditDuration(duration);
    setEditOrderLimit(orderLimit);
    if (simTimeout.current) clearTimeout(simTimeout.current);
    simTimeout.current = setTimeout(() => runSimulation(discount, duration, orderLimit), 400);
  }

  async function runSimulation(discount: number, duration: number, orderLimit: number) {
    if (!merchantId || !editingProduct) return;
    setSimLoading(true);
    try {
      const res = await apiFetch(`/api/merchants/${merchantId}/pricing-intelligence/simulate`, {
        method: "POST",
        body: JSON.stringify({
          base_price_minor: editingProduct.base_price_minor,
          cost_price_minor: editingProduct.cost_price_minor,
          available_quantity: editingProduct.available_quantity,
          forecast_30d_demand: editingProduct.forecast_30d_demand,
          category: editingProduct.category,
          discount_percent: discount,
          duration_days: duration,
          order_limit: orderLimit,
        }),
      });
      if (res.ok) {
        setSimResult(await res.json());
      }
    } finally {
      setSimLoading(false);
    }
  }

  async function applyPolicy(product: ProductIntelligence, useCustom = false) {
    if (!merchantId) return;
    const policy = product.recommended_policy;
    setApplyingId(product.product_id);
    try {
      const discountPct = useCustom ? editDiscount : policy.recommended_discount_percent;
      const floorMinor = useCustom
        ? Math.round(product.base_price_minor * (1 - discountPct / 100))
        : policy.floor_price_minor;
      const res = await apiFetch(`/api/merchants/${merchantId}/pricing-intelligence/apply`, {
        method: "POST",
        body: JSON.stringify({
          product_id: product.product_id,
          base_price_minor: product.base_price_minor,
          floor_price_minor: floorMinor,
          discount_percent: discountPct,
          order_limit: useCustom ? editOrderLimit : policy.order_limit,
        }),
      });
      if (res.ok) {
        setAppliedIds(prev => new Set([...prev, product.product_id]));
        if (useCustom) closeEdit();
        await loadIntelligence(merchantId);
      }
    } finally {
      setApplyingId(null);
    }
  }

  const pressureColor = (p: number) => {
    if (p >= 4) return "text-red-400 bg-red-500/10 border-red-500/20";
    if (p >= 2) return "text-amber-400 bg-amber-500/10 border-amber-500/20";
    return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="relative">
          <Brain className="w-12 h-12 text-blue-400 animate-pulse" />
          <Sparkles className="w-4 h-4 text-amber-400 absolute -top-1 -right-1 animate-spin" />
        </div>
        <p className="text-muted-foreground text-sm animate-pulse">
          Running Autonomous Pricing Intelligence Engine...
        </p>
      </div>
    );
  }

  if (!merchantId) {
    return (
      <div className="text-center pt-16 space-y-4">
        <Brain className="w-10 h-10 text-muted-foreground mx-auto" />
        <h2 className="text-xl font-bold">No merchant configured</h2>
        <p className="text-muted-foreground">Go to <a href="/merchant/dashboard" className="text-blue-400 hover:underline">Dashboard</a> first.</p>
      </div>
    );
  }

  const summary = intelligence?.summary;
  const products = intelligence?.products || [];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Brain className="w-6 h-6 text-blue-400" />
            Autonomous Pricing Engine
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            5-engine AI determines optimal discounts via demand forecasting, elasticity modelling, and profit optimization.
          </p>
        </div>
        <Button onClick={() => loadIntelligence(merchantId)} variant="outline" className="gap-2 text-xs">
          <Zap className="w-3 h-3" /> Re-analyse
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Monitored Products", value: summary.total_products, icon: Package, color: "blue" },
            { label: "Excess Inventory Alerts", value: summary.excess_inventory_products, icon: AlertTriangle, color: "red" },
            { label: "Avg Inventory Pressure", value: `${summary.average_inventory_pressure}x`, icon: BarChart3, color: "amber" },
            { label: "Optimization Potential", value: `₹${(summary.potential_expected_profit_inr || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`, icon: Target, color: "emerald" },
          ].map((item) => (
            <Card key={item.label} className="border-border/50 bg-card/50">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <item.icon className={`w-4 h-4 text-${item.color}-400`} />
                  <span className="text-xs text-muted-foreground">{item.label}</span>
                </div>
                <p className={`text-2xl font-bold text-${item.color}-400`}>{item.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Per-Product Intelligence Cards */}
      <div className="space-y-4">
        {products.length === 0 && (
          <Card className="border-dashed">
            <CardContent className="py-12 text-center">
              <Package className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground">No inventory products found. Add products to your catalog first.</p>
            </CardContent>
          </Card>
        )}

        {products.map((product) => {
          const isExpanded = expandedProduct === product.product_id;
          const aiPolicy = product.recommended_policy;
          const isApplied = appliedIds.has(product.product_id);
          const hasActivePolicy = !!product.active_policy;

          return (
            <motion.div key={product.product_id} layout>
              <Card className={`overflow-hidden border transition-all duration-300 ${
                product.has_excess_inventory
                  ? "border-red-500/20 hover:border-red-500/40"
                  : "border-border/50 hover:border-blue-500/20"
              } bg-card/60 backdrop-blur`}>

                {/* Card Header */}
                <div
                  className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-5 cursor-pointer group"
                  onClick={() => setExpandedProduct(isExpanded ? null : product.product_id)}
                >
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                      product.has_excess_inventory ? "bg-red-500/10" : "bg-blue-500/10"
                    }`}>
                      {product.has_excess_inventory
                        ? <TrendingDown className="w-5 h-5 text-red-400" />
                        : <TrendingUp className="w-5 h-5 text-blue-400" />
                      }
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-bold text-lg leading-tight truncate">{product.product_name}</h3>
                      <p className="text-xs text-muted-foreground">{product.sku} · {product.category}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap mt-3 sm:mt-0">
                    {/* Stock badge */}
                    <Badge variant="outline" className="text-xs px-2 py-0.5">
                      <Package className="w-3 h-3 mr-1" />
                      {product.available_quantity} units
                    </Badge>

                    {/* Pressure badge */}
                    <Badge variant="outline" className={`text-xs px-2 py-0.5 ${pressureColor(product.inventory_pressure)}`}>
                      {product.inventory_pressure}x pressure
                    </Badge>

                    {/* AI Recommendation badge */}
                    {aiPolicy.recommended_discount_percent > 0 ? (
                      <Badge className="bg-blue-600/20 text-blue-300 border border-blue-500/30 text-xs px-2 py-0.5">
                        <Brain className="w-3 h-3 mr-1" />
                        AI: {aiPolicy.recommended_discount_percent}% off
                      </Badge>
                    ) : (
                      <Badge className="bg-emerald-600/20 text-emerald-300 border border-emerald-500/30 text-xs px-2 py-0.5">
                        <CheckCircle2 className="w-3 h-3 mr-1" />
                        No discount needed
                      </Badge>
                    )}

                    {hasActivePolicy && (
                      <Badge variant="outline" className="text-emerald-400 bg-emerald-500/10 border-emerald-500/20 text-xs px-2 py-0.5">
                        <ShieldCheck className="w-3 h-3 mr-1" />
                        Policy Active
                      </Badge>
                    )}

                    {isExpanded
                      ? <ChevronUp className="w-4 h-4 text-muted-foreground ml-1" />
                      : <ChevronDown className="w-4 h-4 text-muted-foreground ml-1" />
                    }
                  </div>
                </div>

                {/* Expanded Content */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      <div className="border-t border-border/50 p-5 space-y-6">

                        {/* Pricing Overview */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          {[
                            { label: "Base Price", value: `₹${product.base_price_inr.toFixed(2)}`, color: "blue" },
                            { label: "Est. Cost Price", value: `₹${product.cost_price_inr.toFixed(2)}`, color: "muted-foreground" },
                            { label: "AI Floor Price", value: `₹${aiPolicy.floor_price_inr.toFixed(2)}`, color: "amber" },
                            { label: "Overstock Risk", value: `${product.overstock_probability}%`, color: product.overstock_probability > 60 ? "red" : "emerald" },
                          ].map((item) => (
                            <div key={item.label} className="bg-muted/20 rounded-lg p-3 border border-border/30">
                              <p className="text-xs text-muted-foreground mb-1">{item.label}</p>
                              <p className={`font-bold text-lg text-${item.color}`}>{item.value}</p>
                            </div>
                          ))}
                        </div>

                        {/* Inventory Pressure Bar */}
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-muted-foreground">Inventory Pressure</span>
                            <span className={`font-bold ${product.inventory_pressure >= 4 ? "text-red-400" : product.inventory_pressure >= 2 ? "text-amber-400" : "text-emerald-400"}`}>
                              {product.inventory_pressure}x ({product.available_quantity} units ÷ {product.forecast_30d_demand}/mo forecast)
                            </span>
                          </div>
                          <div className="h-3 bg-muted/30 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-1000 ${
                                product.inventory_pressure >= 4 ? "bg-gradient-to-r from-red-500 to-orange-500" :
                                product.inventory_pressure >= 2 ? "bg-gradient-to-r from-amber-500 to-yellow-500" :
                                "bg-gradient-to-r from-emerald-500 to-teal-500"
                              }`}
                              style={{ width: `${Math.min(100, (product.inventory_pressure / 6) * 100)}%` }}
                            />
                          </div>
                        </div>

                        {/* AI Policy Recommendation */}
                        {aiPolicy.recommended_discount_percent > 0 && (
                          <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-4 space-y-3">
                            <div className="flex items-center gap-2">
                              <Brain className="w-4 h-4 text-blue-400" />
                              <span className="font-semibold text-blue-300 text-sm">
                                AI Policy {aiPolicy.policy_code} — {aiPolicy.recommended_discount_percent}% Optimal Discount
                              </span>
                            </div>
                            <p className="text-xs text-muted-foreground italic">{aiPolicy.why_reason}</p>
                            <div className="grid grid-cols-3 gap-2 text-xs">
                              {[
                                { label: "Duration", value: `${aiPolicy.duration_days} days` },
                                { label: "Max Orders", value: aiPolicy.order_limit },
                                { label: "Expected Sales Lift", value: `+${aiPolicy.expected_sales_lift_percent}%` },
                                { label: "Expected Profit", value: `₹${aiPolicy.expected_total_profit_inr.toLocaleString('en-IN', { maximumFractionDigits: 0 })}` },
                                { label: "Stock Cleared", value: `${aiPolicy.stock_cleared_percent}%` },
                                { label: "Target", value: aiPolicy.target_segment },
                              ].map(item => (
                                <div key={item.label} className="bg-blue-500/5 rounded-lg p-2 border border-blue-500/10">
                                  <p className="text-muted-foreground mb-0.5">{item.label}</p>
                                  <p className="font-semibold text-blue-200">{item.value}</p>
                                </div>
                              ))}
                            </div>
                            {/* Adaptive Rules */}
                            <div className="space-y-1 border-t border-blue-500/10 pt-3 mt-2">
                              {Object.entries(aiPolicy.adaptive_rules).map(([key, val]) => (
                                <p key={key} className="text-xs text-muted-foreground">
                                  <span className="text-blue-400 font-medium capitalize">{key.replace(/_/g, " ")}: </span>
                                  {val}
                                </p>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Simulation Table */}
                        <div className="space-y-2">
                          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                            <BarChart3 className="w-3.5 h-3.5" /> Discount Optimization Matrix
                          </h4>
                          <div className="overflow-x-auto rounded-lg border border-border/50">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b border-border/50 bg-muted/20">
                                  {["Discount", "Price", "Predicted Sales", "Profit/Unit", "Total Profit", "Stock Cleared"].map(h => (
                                    <th key={h} className="text-left px-3 py-2 font-semibold text-muted-foreground">{h}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {product.simulation_matrix.map((row) => (
                                  <tr
                                    key={row.discount_percent}
                                    className={`border-b border-border/30 transition-colors ${
                                      row.is_optimal
                                        ? "bg-emerald-500/10 text-emerald-300 font-semibold"
                                        : !row.is_margin_safe
                                        ? "bg-red-500/5 text-red-400/60"
                                        : "hover:bg-muted/20"
                                    }`}
                                  >
                                    <td className="px-3 py-2 flex items-center gap-1">
                                      {row.is_optimal && <Sparkles className="w-3 h-3 text-emerald-400" />}
                                      {row.discount_percent}%
                                    </td>
                                    <td className="px-3 py-2">₹{row.new_price_inr}</td>
                                    <td className="px-3 py-2">{row.predicted_sales}</td>
                                    <td className="px-3 py-2">₹{row.profit_per_unit_inr.toFixed(2)}</td>
                                    <td className="px-3 py-2">₹{row.expected_total_profit_inr.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</td>
                                    <td className="px-3 py-2">{row.stock_cleared_percent}%</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex gap-3 pt-2 border-t border-border/50">
                          {aiPolicy.recommended_discount_percent > 0 && (
                            <Button
                              className="bg-emerald-600 hover:bg-emerald-700 gap-2 text-sm"
                              onClick={() => applyPolicy(product, false)}
                              disabled={applyingId === product.product_id || isApplied}
                            >
                              {applyingId === product.product_id
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : isApplied
                                ? <CheckCircle2 className="w-4 h-4" />
                                : <Zap className="w-4 h-4" />
                              }
                              {isApplied ? "AI Policy Applied!" : "Approve AI Policy"}
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            className="gap-2 text-sm hover:bg-blue-500/10 hover:text-blue-400 hover:border-blue-500/30"
                            onClick={(e) => { e.stopPropagation(); openEdit(product); }}
                          >
                            <Edit3 className="w-4 h-4" /> Edit Everything & Re-simulate
                          </Button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* Edit & Re-simulate Modal */}
      <AnimatePresence>
        {editingProduct && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={closeEdit}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-background border border-border rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
              onClick={e => e.stopPropagation()}
            >
              <div className="p-6 space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-bold">Edit Policy Parameters</h2>
                    <p className="text-sm text-muted-foreground">{editingProduct.product_name}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={closeEdit}>
                    <X className="w-4 h-4" />
                  </Button>
                </div>

                {/* Parameter Inputs */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold">Discount %</Label>
                    <Input
                      type="number"
                      min={0}
                      max={40}
                      value={editDiscount}
                      onChange={e => onEditChange(Number(e.target.value), editDuration, editOrderLimit)}
                      className="text-center font-bold text-lg"
                    />
                    <p className="text-xs text-muted-foreground text-center">
                      AI: {editingProduct.recommended_policy.recommended_discount_percent}%
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold">Duration (days)</Label>
                    <Input
                      type="number"
                      min={1}
                      max={30}
                      value={editDuration}
                      onChange={e => onEditChange(editDiscount, Number(e.target.value), editOrderLimit)}
                      className="text-center font-bold text-lg"
                    />
                    <p className="text-xs text-muted-foreground text-center">
                      AI: {editingProduct.recommended_policy.duration_days} days
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold">Max Orders</Label>
                    <Input
                      type="number"
                      min={1}
                      value={editOrderLimit}
                      onChange={e => onEditChange(editDiscount, editDuration, Number(e.target.value))}
                      className="text-center font-bold text-lg"
                    />
                    <p className="text-xs text-muted-foreground text-center">
                      AI: {editingProduct.recommended_policy.order_limit}
                    </p>
                  </div>
                </div>

                {/* Live Simulation Comparison */}
                <div className="bg-muted/20 rounded-xl border border-border/50 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-blue-400" />
                    <span className="text-sm font-semibold">Live Re-simulation</span>
                    {simLoading && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    {/* AI Proposal */}
                    <div className="space-y-2">
                      <p className="text-xs font-semibold text-blue-400 uppercase tracking-wider">AI Recommendation</p>
                      {[
                        { label: "Discount", value: `${editingProduct.recommended_policy.recommended_discount_percent}%` },
                        { label: "Expected Sales", value: editingProduct.recommended_policy.expected_sales },
                        { label: "Total Profit", value: `₹${editingProduct.recommended_policy.expected_total_profit_inr.toLocaleString('en-IN', { maximumFractionDigits: 0 })}` },
                        { label: "Stock Cleared", value: `${editingProduct.recommended_policy.stock_cleared_percent}%` },
                      ].map(item => (
                        <div key={item.label} className="flex justify-between text-xs py-1 border-b border-border/30">
                          <span className="text-muted-foreground">{item.label}</span>
                          <span className="font-semibold text-blue-300">{item.value}</span>
                        </div>
                      ))}
                    </div>

                    {/* Merchant Proposal */}
                    <div className="space-y-2">
                      <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Your Proposal</p>
                      {simResult ? [
                        { label: "Discount", value: `${simResult.proposed_discount_percent}%` },
                        { label: "Expected Sales", value: simResult.predicted_sales },
                        { label: "Total Profit", value: `₹${simResult.expected_total_profit_inr.toLocaleString('en-IN', { maximumFractionDigits: 0 })}` },
                        { label: "Stock Cleared", value: `${simResult.stock_cleared_percent}%` },
                      ].map(item => (
                        <div key={item.label} className="flex justify-between text-xs py-1 border-b border-border/30">
                          <span className="text-muted-foreground">{item.label}</span>
                          <span className="font-semibold text-amber-300">{item.value}</span>
                        </div>
                      )) : (
                        <p className="text-xs text-muted-foreground py-4 text-center">Adjust parameters to see simulation...</p>
                      )}
                    </div>
                  </div>

                  {/* Safety Check */}
                  {simResult && (
                    <div className={`rounded-lg p-3 text-xs border flex items-start gap-2 ${
                      simResult.safety_status === "PASSED"
                        ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
                        : simResult.safety_status === "VIOLATION"
                        ? "bg-red-500/10 border-red-500/20 text-red-300"
                        : "bg-amber-500/10 border-amber-500/20 text-amber-300"
                    }`}>
                      <ShieldCheck className="w-4 h-4 flex-shrink-0 mt-0.5" />
                      <span>{simResult.safety_message}</span>
                    </div>
                  )}
                </div>

                {/* Apply Buttons */}
                <div className="flex gap-3">
                  <Button
                    className="flex-1 bg-amber-600 hover:bg-amber-700 gap-2"
                    onClick={() => applyPolicy(editingProduct, true)}
                    disabled={applyingId === editingProduct.product_id || (!!simResult && !simResult.is_safe)}
                  >
                    {applyingId === editingProduct.product_id
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <CheckCircle2 className="w-4 h-4" />
                    }
                    Apply Custom Policy
                  </Button>
                  <Button variant="outline" onClick={closeEdit}>Cancel</Button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
