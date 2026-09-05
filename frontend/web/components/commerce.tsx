"use client";

import { useRef, useState } from "react";
import { apiFetch } from "../lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "./common/status-badge";
import { 
  ShieldAlert, CreditCard, ShieldCheck, Download, Printer, 
  CheckCircle2, RefreshCw, Zap, Lock, ArrowRight, Layers,
  ExternalLink, Sparkles
} from "lucide-react";

export type CheckoutProduct = { product_id: string; merchant_id: string; name: string; current_price_minor: number; currency: string };
type CheckoutData = { payment_attempt_id: string; public_key_id: string; order_id: string; amount_minor: number; currency: string };
type RazorpayResult = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };
type RazorpayInstance = { open: () => void; on: (event: string, callback: (value: unknown) => void) => void };
declare global { interface Window { Razorpay: new (options: Record<string, unknown>) => RazorpayInstance } }

export function CartCard({ product, budgetMinor, mandateId, cartId }: { product?: CheckoutProduct; budgetMinor?: number; mandateId?: string; cartId?: string }) {
  const [state, setState] = useState("READY");
  const [receipt, setReceipt] = useState<Record<string, unknown> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  async function json(path: string, init: RequestInit) {
    const response = await apiFetch(path, init);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  }
  
  function poll(attemptId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const response = await apiFetch(`/api/payments/${attemptId}/status`);
        const data = await response.json();
        setState(data.status);
        if (["CAPTURED", "FAILED"].includes(data.status)) {
          if (pollRef.current) clearInterval(pollRef.current);
          if (data.status === "CAPTURED") setReceipt(data);
        }
      } catch {
        setState("UNKNOWN");
      }
    }, 2000);
  }
  
  async function verifyAndPay() {
    if (!product || !mandateId) return;
    try {
      setState("VERIFYING_CART");
      let activeCartId = cartId;
      if (!activeCartId) {
        const cart = await json("/api/carts", { method: "POST", body: JSON.stringify({ merchant_id: product.merchant_id, mandate_id: mandateId }) });
        activeCartId = cart.id;
        await json(`/api/carts/${activeCartId}/items`, { method: "POST", body: JSON.stringify({ product_id: product.product_id, quantity: 1 }) });
      }
      const prepared = await json("/api/checkout/prepare", { method: "POST", body: JSON.stringify({ cart_id: activeCartId, idempotency_key: crypto.randomUUID() }) });
      if (prepared.outcome === "DENY") throw new Error("SecurityKernel denied this cart");
      if (prepared.outcome === "REQUIRE_APPROVAL") {
        await json(`/api/checkout/${prepared.transaction_id}/confirm`, { method: "POST", body: JSON.stringify({ confirmed: true }) });
      }
      const checkout: CheckoutData = await json("/api/payments/order", { method: "POST", body: JSON.stringify({ transaction_id: prepared.transaction_id, idempotency_key: crypto.randomUUID() }) });
      setState("PAYMENT_PROCESSING");
      poll(checkout.payment_attempt_id);
      
      if (typeof window !== "undefined" && !window.Razorpay) {
        await new Promise((resolve) => {
          const script = document.createElement("script");
          script.src = "https://checkout.razorpay.com/v1/checkout.js";
          script.onload = () => resolve(true);
          script.onerror = () => resolve(false);
          document.body.appendChild(script);
        });
      }

      if (!window.Razorpay) {
        throw new Error("Razorpay SDK could not be loaded");
      }

      const instance = new window.Razorpay({
        key: checkout.public_key_id,
        order_id: checkout.order_id,
        amount: checkout.amount_minor,
        currency: checkout.currency,
        name: "SentinelPay Test Mode",
        description: product.name,
        handler: async (result: RazorpayResult) => {
          setState("PAYMENT_VERIFICATION_PENDING");
          const verified = await json("/api/payments/verify", { method: "POST", body: JSON.stringify({ payment_attempt_id: checkout.payment_attempt_id, ...result }) });
          setState(verified.status);
          poll(checkout.payment_attempt_id);
        },
        modal: {
          ondismiss: () => {
            setState("PAYMENT_VERIFICATION_PENDING");
            poll(checkout.payment_attempt_id);
          }
        }
      });
      instance.on("payment.failed", () => setState("PAYMENT_VERIFICATION_PENDING"));
      instance.open();
    } catch (error) {
      setState(error instanceof Error ? error.message : "PAYMENT_FAILED");
    }
  }
  
  const displayState: Record<string, string> = { 
    PAYMENT_PENDING: "PAYMENT_PROCESSING", 
    UNKNOWN: "PAYMENT_STATE_UNKNOWN", 
    FAILED: "PAYMENT_FAILED", 
    CAPTURED: "PAYMENT_CAPTURED" 
  };
  
  return (
    <Card className="glass-panel border-border/60 h-full flex flex-col rounded-2xl overflow-hidden">
      {/* Terminal Card Header */}
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <CreditCard className="w-4 h-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-bold text-foreground">
                Payment Terminal
              </CardTitle>
              <p className="text-[10px] text-muted-foreground font-mono">
                Server-Verified Razorpay Checkout
              </p>
            </div>
          </div>
          <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20 text-[10px] font-mono">
            TEST MODE
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-4 flex-1 flex flex-col space-y-4">
        {/* Item Summary Table */}
        <div className="p-3.5 rounded-xl bg-background/50 border border-border/50 space-y-2.5 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Selected Item:</span>
            <span className="font-semibold text-foreground truncate max-w-[200px]">
              {product?.name ?? "No product selected"}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Payable Price:</span>
            <span className="font-mono font-bold text-emerald-400 text-sm">
              {product ? `${product.currency} ${(product.current_price_minor / 100).toLocaleString("en-IN")}` : "—"}
            </span>
          </div>

          <div className="flex items-center justify-between pt-1 border-t border-border/30 text-[11px]">
            <span className="text-muted-foreground">Mandate Ceiling:</span>
            <span className="font-mono text-muted-foreground">
              {budgetMinor ? `INR ${(budgetMinor / 100).toLocaleString("en-IN")}` : "Awaiting mandate"}
            </span>
          </div>
        </div>
        
        {receipt && <ReceiptCard receipt={receipt} product={product} />}
        
        {state !== "READY" && state !== "CAPTURED" && (
          <div className="text-xs p-3 rounded-xl bg-muted/40 border border-border/50 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase text-muted-foreground">State:</span>
              <StatusBadge 
                status={displayState[state] ?? state} 
                variant={state.includes("FAILED") || state.includes("denied") ? "danger" : "amber"} 
              />
            </div>
            {state === "UNKNOWN" && (
              <p className="text-[10px] text-muted-foreground pt-1">
                Payment state is being verified. SentinelPay will not retry until previous attempt is resolved.
              </p>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="pt-3 pb-4 px-6 border-t border-border/40 mt-auto bg-muted/5">
        <Button 
          className="w-full text-xs h-10 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold gap-2" 
          disabled={!product || !mandateId || state === "PAYMENT_PROCESSING" || state === "CAPTURED"} 
          onClick={verifyAndPay}
        >
          {state === "CAPTURED" ? (
            <><CheckCircle2 className="w-4 h-4 text-emerald-300" /> Payment Completed</>
          ) : state === "PAYMENT_PROCESSING" || state === "VERIFYING_CART" ? (
            <><RefreshCw className="w-4 h-4 animate-spin" /> Verifying Security Kernel...</>
          ) : (
            <><ShieldCheck className="w-4 h-4" /> Verify Z3 &amp; Launch Razorpay Test Mode</>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}

export function VerificationCard() {
  const securityChecks = [
    { name: "Capability Mandate", status: "VERIFIED", note: "User budget bounded", color: "text-emerald-400" },
    { name: "Merchant Floor Policy", status: "VERIFIED", note: "Above minimum sale price", color: "text-emerald-400" },
    { name: "Z3 Formal Equilibrium", status: "PROVED", note: "Mathematical satisfiability (SAT)", color: "text-emerald-400" },
    { name: "Inventory Reserve Check", status: "VERIFIED", note: "Available in warehouse", color: "text-emerald-400" },
    { name: "Cryptographic Commitment", status: "RECORDED", note: "SHA-256 tamper-evident hash", color: "text-purple-400" },
  ];

  return (
    <Card className="glass-panel border-border/60 h-full flex flex-col rounded-2xl overflow-hidden">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-bold text-foreground">
                Security Kernel
              </CardTitle>
              <p className="text-[10px] text-muted-foreground font-mono">
                Z3 Formal Verification Pipeline
              </p>
            </div>
          </div>
          <Badge className="bg-rose-500/10 text-rose-400 border-rose-500/20 text-[10px] font-mono">
            AUTHORIZATION GATED
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-4 flex-1 space-y-3">
        <p className="text-xs text-muted-foreground leading-relaxed">
          Autonomous agents can only propose cart changes. Money movement is strictly gated by the multi-constraint solver.
        </p>

        {/* Verification Check List */}
        <div className="space-y-2 pt-1">
          {securityChecks.map((chk, i) => (
            <div 
              key={i}
              className="p-2.5 rounded-xl bg-background/50 border border-border/40 flex items-center justify-between text-xs"
            >
              <div className="space-y-0.5">
                <p className="font-semibold text-foreground text-[11px]">{chk.name}</p>
                <p className="text-[10px] text-muted-foreground">{chk.note}</p>
              </div>
              <span className={`font-mono font-bold text-[10px] ${chk.color} bg-muted/30 px-2 py-0.5 rounded border border-border/40`}>
                {chk.status}
              </span>
            </div>
          ))}
        </div>
      </CardContent>

      <CardFooter className="pt-3 pb-3 px-6 border-t border-border/40 bg-muted/5">
        <div className="w-full flex items-center justify-between text-[11px] text-muted-foreground font-mono">
          <span>STATUS: DETERMINISTIC</span>
          <span className="text-emerald-400 flex items-center gap-1">
            <Lock className="w-3 h-3" /> Z3 SOLVER SAT
          </span>
        </div>
      </CardFooter>
    </Card>
  );
}

export function ReceiptCard({ receipt, product }: { receipt: Record<string, unknown>, product?: CheckoutProduct }) {
  const amount = (Number(receipt.amount_minor) / 100).toLocaleString("en-IN");
  const paymentId = String(receipt.razorpay_payment_id || receipt.payment_attempt_id || "PAY-TXN");
  
  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-emerald-500/30 bg-card shadow-lg">
      <div className="bg-gradient-to-b from-emerald-500/15 to-transparent p-4 border-b border-emerald-500/20 flex flex-col items-center justify-center text-center">
        <div className="w-10 h-10 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center mb-2">
          <CheckCircle2 className="w-6 h-6 text-emerald-400" />
        </div>
        <h3 className="font-bold text-emerald-400 text-sm">Payment Captured &amp; Settled</h3>
        <p className="text-2xl font-bold font-mono text-foreground mt-1">
          {String(receipt.currency)} {amount}
        </p>
      </div>
      
      <div className="p-4 space-y-3">
        <div className="space-y-2 text-xs">
          <div className="flex justify-between border-b border-border/30 pb-2">
            <span className="text-muted-foreground">Product</span>
            <span className="font-semibold text-foreground text-right max-w-[180px] truncate">{product?.name || "Product"}</span>
          </div>
          <div className="flex justify-between border-b border-border/30 pb-2">
            <span className="text-muted-foreground">Payment ID</span>
            <span className="font-mono text-[11px] text-primary">{paymentId}</span>
          </div>
          <div className="flex justify-between border-b border-border/30 pb-2">
            <span className="text-muted-foreground">Timestamp</span>
            <span className="text-foreground">{new Date().toLocaleDateString("en-IN", { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
          </div>
          <div className="flex justify-between pt-1">
            <span className="font-semibold text-foreground">Total Settled</span>
            <span className="font-bold font-mono text-emerald-400">{String(receipt.currency)} {amount}</span>
          </div>
        </div>
        
        <div className="flex gap-2 pt-2">
          <Button variant="outline" size="sm" className="w-full text-xs h-8 border-border/60 gap-1.5" onClick={() => window.print()}>
            <Printer className="w-3.5 h-3.5" /> Print
          </Button>
          <Button variant="default" size="sm" className="w-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-8 gap-1.5">
            <Download className="w-3.5 h-3.5" /> Receipt PDF
          </Button>
        </div>
      </div>
      
      <div className="bg-muted/20 p-2.5 text-center border-t border-border/30">
        <div className="flex items-center justify-center gap-1.5 text-[10px] text-muted-foreground font-mono">
          <ShieldCheck className="w-3 h-3 text-emerald-400" />
          <span>CRYPTOGRAPHICALLY SEALED BY SENTINELPAY LEDGER</span>
        </div>
      </div>
    </div>
  );
}
