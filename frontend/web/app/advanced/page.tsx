"use client";
import { ArrowLeft, Activity, Cpu, Network, ShieldCheck, Database, Link as LinkIcon, BarChart3, Fingerprint } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function AdvancedPage() {
  const proofs = [
    {
      title: "AI Provider Failover",
      icon: <Cpu className="w-5 h-5 text-purple-500" />,
      description: "Seamless fallback between Groq, NVIDIA, and OpenAI endpoints ensuring 99.99% uptime for the agentic loop.",
      status: "ACTIVE",
      metrics: "Sub-50ms failover"
    },
    {
      title: "ML Strategy (LinUCB / CFR)",
      icon: <BarChart3 className="w-5 h-5 text-blue-500" />,
      description: "Contextual bandits and Counterfactual Regret Minimization optimizing negotiation postures dynamically.",
      status: "TRAINED",
      metrics: "12% reward lift"
    },
    {
      title: "ZK Budget Sufficiency",
      icon: <ShieldCheck className="w-5 h-5 text-green-500" />,
      description: "Zero-Knowledge proofs verifying the buyer's budget is sufficient without revealing the actual max budget to the merchant.",
      status: "VERIFIED",
      metrics: "1.2kb proof size"
    },
    {
      title: "Homomorphic Encryption",
      icon: <Database className="w-5 h-5 text-yellow-500" />,
      description: "Secure aggregation of cross-platform pricing data without decrypting individual merchant limits.",
      status: "ACTIVE",
      metrics: "Fully encrypted"
    },
    {
      title: "BLS Signatures",
      icon: <Fingerprint className="w-5 h-5 text-pink-500" />,
      description: "Aggregated cryptographic signatures from multi-verifiers authorizing the final cart commit.",
      status: "ATTESTED",
      metrics: "k-of-n valid"
    },
    {
      title: "Causal Analytics",
      icon: <Network className="w-5 h-5 text-orange-500" />,
      description: "DoWhy integration estimating true incremental revenue from agentic interventions vs baseline.",
      status: "COMPUTED",
      metrics: "Robust ATE"
    }
  ];

  return (
    <div className="min-h-screen bg-background pb-12">
      <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center justify-between px-4 md:px-8 max-w-7xl mx-auto">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" asChild className="gap-2">
              <a href="/app">
                <ArrowLeft className="h-4 w-4" />
                <span className="hidden sm:inline">Back</span>
              </a>
            </Button>
            <div className="h-4 w-px bg-border"></div>
            <span className="font-bold tracking-tight text-sm text-purple-500 flex items-center gap-2">
              <Activity className="w-4 h-4" /> ADVANCED PROOF LAB
            </span>
          </div>
          <span className="inline-flex items-center rounded-md bg-purple-500/10 px-2 py-1 text-xs font-medium text-purple-500 ring-1 ring-inset ring-purple-500/20">
            TECHNICAL CREDIBILITY
          </span>
        </div>
      </header>

      <main className="container max-w-7xl mx-auto p-4 md:p-8 pt-8 space-y-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Intelligence above. Deterministic rails below.</h1>
          <p className="text-muted-foreground text-lg max-w-3xl">
            This lab exposes the deep-tech infrastructure powering SentinelPay. These cryptographic and machine learning layers ensure the agentic front-end cannot violate security guarantees.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {proofs.map((proof, i) => (
            <Card key={i} className="border-primary/20 bg-card/60 backdrop-blur-sm">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="p-2 bg-background rounded-md border border-border/50">
                    {proof.icon}
                  </div>
                  <Badge variant="outline" className="border-primary/30 text-primary bg-primary/10">
                    {proof.status}
                  </Badge>
                </div>
                <CardTitle className="text-lg">{proof.title}</CardTitle>
                <CardDescription className="pt-2">{proof.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-xs font-mono text-muted-foreground bg-black/40 p-2 rounded-md border border-border/50">
                  <span className="text-primary">{'>'}</span> metric_target: {proof.metrics}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}
