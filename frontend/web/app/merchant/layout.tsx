"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Shield, LayoutDashboard, Package, Database, Cpu, Scale,
  Megaphone, Activity, ShoppingCart, BarChart3, LogOut,
  ArrowLeft, ChevronRight, Bot, Menu, X, Boxes
} from "lucide-react";
import { apiFetch } from "@/lib/api";

const merchantNav = [
  { name: "Dashboard", href: "/merchant/dashboard", icon: LayoutDashboard },
  { name: "Catalog", href: "/merchant/catalog", icon: Package },
  { name: "Inventory", href: "/merchant/inventory", icon: Database },
  { name: "AI Commerce", href: "/merchant/ai-commerce", icon: Cpu },
  { name: "Policies", href: "/merchant/policies", icon: Scale },
  { name: "Campaigns", href: "/merchant/campaigns", icon: Megaphone },
  { name: "Agent Activity", href: "/merchant/agent-activity", icon: Activity },
  { name: "Orders", href: "/merchant/orders", icon: ShoppingCart },
  { name: "Revenue", href: "/merchant/revenue", icon: BarChart3 },
  { name: "Bulk Commerce", href: "/merchant/bulk", icon: Boxes },
];


export default function MerchantLayout({ children }: { children: React.ReactNode }) {
  const [email, setEmail] = useState<string>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [merchants, setMerchants] = useState<any[]>([]);
  const [activeMerchantId, setActiveMerchantId] = useState<string>("");
  const pathname = usePathname();

  useEffect(() => {
    if (localStorage.getItem("demo_session")) {
      setEmail(localStorage.getItem("demo_session") || "demo@sentinelpay.com");
      fetchMerchants();
      return;
    }
    supabase.auth.getUser().then(({ data }) => {
      if (!data.user) location.assign("/login");
      else {
        setEmail(data.user.email);
        fetchMerchants();
      }
    });
  }, []);

  async function fetchMerchants() {
    try {
      const res = await apiFetch("/api/merchants");
      const data = await res.json();
      if (data.merchants) {
        setMerchants(data.merchants);
        const stored = localStorage.getItem("sp_merchant_id");
        if (stored && data.merchants.find((m: any) => m.id === stored)) {
          setActiveMerchantId(stored);
        } else if (data.merchants.length > 0) {
          setActiveMerchantId(data.merchants[0].id);
          localStorage.setItem("sp_merchant_id", data.merchants[0].id);
        }
      }
    } catch (e) {
      console.error(e);
    }
  }

  function handleMerchantChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const newId = e.target.value;
    setActiveMerchantId(newId);
    localStorage.setItem("sp_merchant_id", newId);
    window.dispatchEvent(new Event("storage"));
    window.location.reload();
  }

  async function logout() {
    localStorage.removeItem("demo_session");
    await supabase.auth.signOut();
    location.assign("/login");
  }

  if (!email) return (
    <div className="flex h-screen w-full items-center justify-center">
      <div className="animate-pulse flex flex-col items-center gap-4">
        <Shield className="h-12 w-12 text-blue-400/50" />
        <p className="text-muted-foreground">Loading Merchant Console...</p>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/75 backdrop-blur-sm md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-64 glass-panel border-r border-border/50
        transform transition-transform duration-300 ease-in-out
        md:relative md:translate-x-0
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
      `}>
        <div className="flex flex-col h-full">
          {/* Brand & Identity */}
          <div className="flex items-center justify-between h-16 px-4 border-b border-border/40 bg-card/30">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 bg-blue-500/10 rounded-lg ring-1 ring-blue-500/20 text-blue-400">
                <Shield className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-sm tracking-tight text-foreground">SENTINELPAY</span>
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-blue-400 font-semibold">
                    Merchant Console
                  </span>
                  <span className="h-1 w-1 rounded-full bg-blue-400/80" />
                  <span className="text-[9px] font-mono text-muted-foreground">TENANT SCOPED</span>
                </div>
              </div>
            </div>
            <button className="md:hidden p-1 rounded-md hover:bg-muted" onClick={() => setSidebarOpen(false)}>
              <X className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
            <div className="px-3 pb-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70">
              Operations
            </div>
            {merchantNav.map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={`
                    flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200
                    ${isActive
                      ? "bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/30 font-semibold shadow-[0_0_15px_rgba(59,130,246,0.12)]"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                    }
                  `}
                  onClick={() => setSidebarOpen(false)}
                >
                  <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-blue-400" : "text-muted-foreground"}`} />
                  <span>{item.name}</span>
                  {isActive && <ChevronRight className="w-3.5 h-3.5 ml-auto text-blue-400/80" />}
                </a>
              );
            })}
          </nav>

          {/* Quick Switch to Global AI Buyer */}
          <div className="px-3 pb-3 space-y-2 border-t border-border/40 pt-3">
            <a 
              href="/buyer" 
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium text-emerald-400/90 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/15 transition-all border border-emerald-500/20 group"
            >
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-emerald-400" />
                <span>Global Marketplace & Buyer</span>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-emerald-400/60 group-hover:translate-x-0.5 transition-transform" />
            </a>
          </div>

          {/* User Footer */}
          <div className="border-t border-border/40 p-3 bg-card/20">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-mono text-foreground truncate font-medium">{email}</p>
                <p className="text-[10px] text-muted-foreground truncate">Merchant Administrator</p>
              </div>
              <Button variant="ghost" size="sm" onClick={logout} className="h-8 w-8 p-0 shrink-0 text-muted-foreground hover:text-foreground">
                <LogOut className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between h-14 px-4 md:px-6 border-b border-border/40 bg-background/90 backdrop-blur-md shrink-0">
          <div className="flex items-center">
            <button className="md:hidden mr-3 p-1.5 rounded-md hover:bg-accent" onClick={() => setSidebarOpen(true)}>
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="sm" asChild className="gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                <a href="/app"><ArrowLeft className="h-3.5 w-3.5" /> Hub</a>
              </Button>
              <div className="h-4 w-px bg-border" />
              <span className="text-sm font-semibold text-foreground">
                {merchantNav.find((n) => pathname === n.href)?.name || "Merchant Console"}
              </span>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {/* Cmd+K trigger hint */}
            <button
              onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
              className="hidden lg:flex items-center gap-2 text-xs text-muted-foreground bg-muted/40 hover:bg-muted px-2.5 py-1 rounded-md border border-border/40 transition-colors"
            >
              <span>Quick jump</span>
              <kbd className="text-[10px] font-mono bg-black/40 px-1 py-0.5 rounded border border-border/40">⌘K</kbd>
            </button>

            <span className="hidden sm:inline-flex items-center gap-1.5 rounded-md bg-yellow-500/10 px-2.5 py-1 text-[11px] font-medium text-yellow-400 ring-1 ring-inset ring-yellow-500/20">
              <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
              RAZORPAY TEST MODE
            </span>

            {merchants.length > 0 && (
              <div className="flex items-center gap-1.5 bg-card/60 px-2 py-1 rounded-lg border border-border/60">
                <span className="text-xs text-muted-foreground font-mono hidden sm:inline">Active:</span>
                <select 
                  value={activeMerchantId} 
                  onChange={handleMerchantChange}
                  className="bg-transparent text-xs font-semibold text-foreground outline-none cursor-pointer"
                >
                  {merchants.map(m => (
                    <option key={m.id} value={m.id} className="bg-card text-foreground">{m.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="container max-w-7xl mx-auto p-4 md:p-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
