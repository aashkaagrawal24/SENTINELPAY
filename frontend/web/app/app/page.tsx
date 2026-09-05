"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Shield, LayoutDashboard, Settings, BarChart3, MessageSquare, Terminal, Activity, LogOut } from "lucide-react";

export default function AppShell() {
  const [email, setEmail] = useState<string>();
  
  useEffect(() => { 
    if (localStorage.getItem("demo_session")) {
      setEmail(localStorage.getItem("demo_session") || "demo@sentinelpay.com");
      return;
    }
    supabase.auth.getUser().then(({ data }) => { if (!data.user) location.assign("/login"); else setEmail(data.user.email); }); 
  }, []);
  
  async function logout() { 
    localStorage.removeItem("demo_session");
    await supabase.auth.signOut(); 
    location.assign("/login"); 
  }
  
  if (!email) return (
    <div className="flex h-screen w-full items-center justify-center">
      <div className="animate-pulse flex flex-col items-center gap-4">
        <Shield className="h-12 w-12 text-primary/50" />
        <p className="text-muted-foreground">Checking secure session...</p>
      </div>
    </div>
  );
  
  const navItems = [
    { name: "Merchant Console", href: "/merchant/dashboard", icon: LayoutDashboard },
    { name: "Catalog", href: "/merchant/catalog", icon: Settings },
    { name: "AI Buyer Workspace", href: "/ai", icon: MessageSquare },
    { name: "Adversarial Judge", href: "/judge", icon: Terminal },
    { name: "Advanced Proofs", href: "/advanced", icon: Activity },
    { name: "System Status", href: "/status", icon: Shield },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navigation */}
      <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 items-center justify-between px-4 md:px-8 max-w-7xl mx-auto">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-primary/10 rounded-lg ring-1 ring-primary/20">
              <Shield className="h-5 w-5 text-primary" />
            </div>
            <span className="font-bold tracking-tight">SENTINELPAY / 4.2</span>
          </div>
          
          <nav className="hidden md:flex items-center gap-1 text-sm font-medium">
            {navItems.map((item) => (
              <a 
                key={item.href}
                href={item.href}
                className="transition-colors hover:text-foreground/80 text-foreground/60 px-3 py-2 rounded-md hover:bg-accent"
              >
                {item.name}
              </a>
            ))}
          </nav>

          <Button variant="ghost" size="sm" onClick={logout} className="gap-2">
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">Log out</span>
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <main className="container max-w-7xl mx-auto p-4 md:p-8 pt-10">
        <motion.div 
          initial={{ opacity: 0, y: 20 }} 
          animate={{ opacity: 1, y: 0 }} 
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <Card className="border-border/50 bg-card/50 backdrop-blur-sm overflow-hidden relative">
            <div className="absolute top-0 right-0 w-[400px] h-[400px] bg-primary/10 blur-[100px] rounded-full -z-10 translate-x-1/3 -translate-y-1/3" />
            
            <CardHeader>
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20">
                  AUTHENTICATED
                </span>
              </div>
              <CardTitle className="text-3xl font-bold tracking-tight">
                Agentic commerce, bounded by code.
              </CardTitle>
              <CardDescription className="text-base mt-2">
                Signed in as <strong className="text-foreground">{email}</strong>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground leading-relaxed max-w-3xl">
                Welcome to your command center. Select your system below to begin the live agentic commerce demonstration.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
                <a href="/merchant/dashboard">
                  <Card className="h-full transition-all hover:bg-accent/50 hover:border-primary/50 group cursor-pointer border-l-4 border-l-blue-500">
                    <CardHeader className="p-4">
                      <div className="flex items-center gap-4 mb-2">
                        <div className="p-2 bg-background rounded-md group-hover:bg-primary/10 transition-colors">
                          <LayoutDashboard className="w-5 h-5 text-blue-500" />
                        </div>
                        <CardTitle className="text-lg">System A: Sentinel Merchant</CardTitle>
                      </div>
                      <CardDescription>
                        Make merchant AI-ready, view opportunity detectors, manage inventory and configure mathematical price boundaries.
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </a>

                <a href="/ai">
                  <Card className="h-full transition-all hover:bg-accent/50 hover:border-primary/50 group cursor-pointer border-l-4 border-l-green-500">
                    <CardHeader className="p-4">
                      <div className="flex items-center gap-4 mb-2">
                        <div className="p-2 bg-background rounded-md group-hover:bg-primary/10 transition-colors">
                          <MessageSquare className="w-5 h-5 text-green-500" />
                        </div>
                        <CardTitle className="text-lg">System B: Sentinel AI Buyer</CardTitle>
                      </div>
                      <CardDescription>
                        The main wow factor: 3-column workspace with natural language intent, market intelligence, agent-to-agent negotiation, and Razorpay checkout.
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </a>

                <a href="/judge">
                  <Card className="h-full transition-all hover:bg-accent/50 hover:border-primary/50 group cursor-pointer border-l-4 border-l-destructive">
                    <CardHeader className="p-4">
                      <div className="flex items-center gap-4 mb-2">
                        <div className="p-2 bg-background rounded-md group-hover:bg-primary/10 transition-colors">
                          <Terminal className="w-5 h-5 text-destructive" />
                        </div>
                        <CardTitle className="text-lg text-destructive">Adversarial Judge Mode</CardTitle>
                      </div>
                      <CardDescription>
                        Main safety demo. Simulate price tampering and provenance injection to prove the Z3 Security Kernel blocks attacks.
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </a>

                <a href="/advanced">
                  <Card className="h-full transition-all hover:bg-accent/50 hover:border-primary/50 group cursor-pointer border-l-4 border-l-purple-500">
                    <CardHeader className="p-4">
                      <div className="flex items-center gap-4 mb-2">
                        <div className="p-2 bg-background rounded-md group-hover:bg-primary/10 transition-colors">
                          <Activity className="w-5 h-5 text-purple-500" />
                        </div>
                        <CardTitle className="text-lg text-purple-500">Advanced Proof Lab</CardTitle>
                      </div>
                      <CardDescription>
                        Deep-tech credibility layer: ZK budget sufficiency, Contextual Bandit (LinUCB / CFR), and cryptographic BLS multi-verifiers.
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </a>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </main>
    </div>
  );
}
