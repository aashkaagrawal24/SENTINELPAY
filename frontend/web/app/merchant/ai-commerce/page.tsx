"use client";

import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Cpu, Bot, Zap, Shield, Network, BarChart3, Eye, Scale } from "lucide-react";

export default function AICommercePage() {
  const capabilities = [
    {
      title: "Agent-Readable Catalog",
      icon: Bot,
      status: "ACTIVE",
      color: "emerald",
      description: "Products are structured for BuyerAgent consumption via MerchantAgent search tool.",
      detail: "MerchantAgent.search() → public_catalog(db, query)"
    },
    {
      title: "Deterministic Negotiation",
      icon: Scale,
      status: "ACTIVE",
      color: "blue",
      description: "NegotiationController enforces floor prices and ceiling budgets. Model output supplies wording, not authority.",
      detail: "NegotiationController.step() → bounded proposals"
    },
    {
      title: "Z3 Policy Solver",
      icon: Shield,
      status: "ACTIVE",
      color: "amber",
      description: "UnifiedPolicyService evaluates all constraints (buyer, merchant, campaign, inventory) in a single Z3 SAT check.",
      detail: "UnifiedPolicyService.evaluate() → SAT / UNSAT"
    },
    {
      title: "SecurityKernel Gate",
      icon: Shield,
      status: "ACTIVE",
      color: "red",
      description: "Sole authorization checkpoint. ALLOW, DENY, or REQUIRE_APPROVAL. Immutable mandate hashing ensures no mutation.",
      detail: "SecurityKernel.authorize() → {outcome, approved_hash}"
    },
    {
      title: "Multi-Provider Failover",
      icon: Cpu,
      status: "ACTIVE",
      color: "purple",
      description: "ModelGateway cascades between Groq → NVIDIA NIM → OpenAI with sub-50ms failover.",
      detail: "ModelGateway.call_structured() → provider cascade"
    },
    {
      title: "Campaign Intelligence",
      icon: BarChart3,
      status: "ACTIVE",
      color: "cyan",
      description: "Opportunity detector scans inventory pressure, conversion gaps, and demand signals to auto-generate campaigns.",
      detail: "CampaignServices.detect_opportunities()"
    },
    {
      title: "Provenance Tracking",
      icon: Eye,
      status: "ACTIVE",
      color: "pink",
      description: "Every product source is tagged (MERCHANT_CATALOG, EXTERNAL_MARKET). External sources are never trusted for payment.",
      detail: "ProvenanceService.verify_trust()"
    },
    {
      title: "Revenue Attribution",
      icon: Network,
      status: "ACTIVE",
      color: "orange",
      description: "Honest attribution labels: campaign-influenced, agent-negotiated, upsell, cross-sell, organic.",
      detail: "AnalyticsServices.revenue_decomposition()"
    },
  ];

  const colorMap: Record<string, string> = {
    emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    blue: "text-blue-400 bg-blue-500/10 border-blue-500/20",
    amber: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    red: "text-red-400 bg-red-500/10 border-red-500/20",
    purple: "text-purple-400 bg-purple-500/10 border-purple-500/20",
    cyan: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
    pink: "text-pink-400 bg-pink-500/10 border-pink-500/20",
    orange: "text-orange-400 bg-orange-500/10 border-orange-500/20",
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI Commerce Capabilities</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Everything that makes your merchant sellable to autonomous AI buyers.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {capabilities.map((cap, i) => {
          const colors = colorMap[cap.color] || colorMap.blue;
          return (
            <motion.div
              key={cap.title}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Card className="h-full border-border/50 bg-card/30">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className={`p-2 rounded-lg border ${colors}`}>
                      <cap.icon className="w-4 h-4" />
                    </div>
                    <Badge variant="outline" className={colors}>
                      {cap.status}
                    </Badge>
                  </div>
                  <CardTitle className="text-base">{cap.title}</CardTitle>
                  <CardDescription className="text-sm">{cap.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-xs font-mono text-muted-foreground bg-black/40 p-2 rounded-md border border-border/50">
                    <span className="text-blue-400">{'>'}</span> {cap.detail}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* Provider Status */}
      <Card className="border-border/50 bg-card/30">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Zap className="w-4 h-4 text-yellow-400" /> AI Provider Stack
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { name: "Groq", model: "GPT-OSS-20B / 120B", role: "Fast intent + reasoning", status: "PRIMARY" },
              { name: "NVIDIA NIM", model: "Nemotron 3.5 / Ultra", role: "Agent negotiation", status: "SECONDARY" },
              { name: "OpenAI", model: "GPT-4o", role: "Complex reasoning fallback", status: "FALLBACK" },
            ].map((provider) => (
              <div key={provider.name} className="p-3 rounded-lg bg-black/20 border border-border/50">
                <div className="flex items-center justify-between mb-2">
                  <p className="font-semibold text-sm">{provider.name}</p>
                  <Badge variant="outline" className="text-xs text-emerald-400 bg-emerald-500/10 border-emerald-500/20">
                    {provider.status}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">{provider.model}</p>
                <p className="text-xs text-muted-foreground mt-1">{provider.role}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
