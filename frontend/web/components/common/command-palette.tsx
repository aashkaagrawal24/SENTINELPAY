"use client";

import React, { useState, useEffect } from "react";
import { 
  Store, Bot, ShoppingCart, BarChart3, Database, Scale, 
  Terminal, Shield, Search, X, ArrowRight, Package, Cpu 
} from "lucide-react";

interface CommandItem {
  name: string;
  category: "Merchant System" | "AI Buyer & Marketplace" | "Safety & Proofs";
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

const commands: CommandItem[] = [
  { name: "Global Marketplace", category: "AI Buyer & Marketplace", href: "/buyer", icon: Store, badge: "Multi-Seller" },
  { name: "AI Buyer Agent Command", category: "AI Buyer & Marketplace", href: "/ai", icon: Bot, badge: "Autonomous" },
  { name: "Merchant Dashboard", category: "Merchant System", href: "/merchant/dashboard", icon: Store },
  { name: "Merchant Orders", category: "Merchant System", href: "/merchant/orders", icon: ShoppingCart },
  { name: "Revenue Analytics", category: "Merchant System", href: "/merchant/revenue", icon: BarChart3 },
  { name: "Product Catalog", category: "Merchant System", href: "/merchant/catalog", icon: Package },
  { name: "Inventory & ATP", category: "Merchant System", href: "/merchant/inventory", icon: Database },
  { name: "Autonomous Policies", category: "Merchant System", href: "/merchant/policies", icon: Scale },
  { name: "AI Commerce Engine", category: "Merchant System", href: "/merchant/ai-commerce", icon: Cpu },
  { name: "Bulk Commerce RFQ", category: "Merchant System", href: "/merchant/bulk", icon: Package },
  { name: "Adversarial Judge Mode", category: "Safety & Proofs", href: "/judge", icon: Terminal, badge: "Z3 Kernel" },
  { name: "Advanced Proof Lab", category: "Safety & Proofs", href: "/advanced", icon: Shield, badge: "Cryptographic" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(prev => !prev);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  if (!open) return null;

  const filtered = commands.filter(c => 
    c.name.toLowerCase().includes(search.toLowerCase()) || 
    c.category.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/75 backdrop-blur-md px-4">
      <div 
        className="w-full max-w-lg glass-panel rounded-2xl border border-border/60 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={e => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center px-4 py-3.5 border-b border-border/40 gap-3">
          <Search className="w-5 h-5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Type a command or jump to page... (ESC to exit)"
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
            className="flex-1 bg-transparent border-none outline-none text-sm text-foreground placeholder:text-muted-foreground/60"
          />
          <button 
            onClick={() => setOpen(false)}
            className="p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto p-2 space-y-1">
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              No matching destinations found
            </div>
          ) : (
            filtered.map((item, i) => {
              const Icon = item.icon;
              return (
                <a
                  key={i}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium hover:bg-accent/60 transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-1.5 rounded-lg bg-muted/40 text-muted-foreground group-hover:text-primary group-hover:bg-primary/10 transition-colors">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-foreground group-hover:text-primary transition-colors">
                        {item.name}
                      </div>
                      <span className="text-[10px] text-muted-foreground/70 font-mono">
                        {item.category}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.badge && (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                        {item.badge}
                      </span>
                    )}
                    <ArrowRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </a>
              );
            })
          )}
        </div>

        <div className="px-4 py-2 bg-muted/20 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground font-mono">
          <span>Navigate with mouse or arrows</span>
          <span className="bg-muted/40 px-1.5 py-0.5 rounded border border-border/40">ESC</span>
        </div>
      </div>
    </div>
  );
}
