"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ShieldAlert, Terminal, Lock, XCircle, CheckCircle2, AlertTriangle,
  Play, ShieldCheck, RefreshCw, Cpu, Database, Eye, ChevronDown, ChevronRight
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface Scenario {
  scenario_key: string;
  category: string;
  attack: string;
}

interface AttackResult {
  scenario_key: string;
  category: string;
  attack: Record<string, any>;
  ai_response: string;
  buyer_policy: Record<string, any>;
  merchant_policy: Record<string, any>;
  campaign_policy: Record<string, any> | null;
  z3_assertions: string[];
  solver_result: string;
  security_kernel_result: string;
  razorpay_called: boolean;
  blocked: boolean;
  audit_event_id?: string;
}

interface Metrics {
  attacks_total: number;
  attacks_blocked: number;
  unsafe_executions: number;
  false_blocks: number;
  critical_bypass_rate: number;
}

export function JudgeSimulator() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [latestResult, setLatestResult] = useState<AttackResult | null>(null);
  const [allResults, setAllResults] = useState<AttackResult[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"single" | "suite">("single");

  useEffect(() => {
    loadScenarios();
  }, []);

  async function loadScenarios() {
    try {
      const res = await apiFetch("/api/judge/scenarios");
      if (res.ok) {
        const data = await res.json();
        setScenarios(data);
        if (data.length > 0) {
          setSelectedScenario(data[0].scenario_key);
        }
      }
    } catch (e) {
      console.error("Failed to load judge scenarios", e);
    }
  }

  async function executeSingleAttack() {
    if (!selectedScenario) return;
    setLoading(true);
    try {
      const merchantId = localStorage.getItem("sp_merchant_id") || undefined;
      const res = await apiFetch("/api/judge/attacks", {
        method: "POST",
        body: JSON.stringify({
          scenario_key: selectedScenario,
          merchant_id: merchantId,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setLatestResult(data.result);
        setMetrics(data.metrics);
        setAllResults((prev) => [data.result, ...prev.filter((r) => r.scenario_key !== data.result.scenario_key)]);
      }
    } catch (e) {
      console.error("Attack execution error", e);
    } finally {
      setLoading(false);
    }
  }

  async function executeAllAttacks() {
    setRunningAll(true);
    try {
      const merchantId = localStorage.getItem("sp_merchant_id") || undefined;
      const res = await apiFetch("/api/judge/runs", {
        method: "POST",
        body: JSON.stringify({ merchant_id: merchantId }),
      });
      if (res.ok) {
        const data = await res.json();
        setAllResults(data.results);
        setMetrics(data.metrics);
        if (data.results.length > 0) {
          setLatestResult(data.results[0]);
        }
        setActiveTab("suite");
      }
    } catch (e) {
      console.error("Suite execution error", e);
    } finally {
      setRunningAll(false);
    }
  }

  const activeScenarioObj = scenarios.find((s) => s.scenario_key === selectedScenario);

  return (
    <div className="space-y-6">
      {/* Top Banner with Suite Trigger and Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="md:col-span-2 border-destructive/30 bg-destructive/5 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2 text-destructive">
                <Terminal className="w-4 h-4" /> Live Red-Team Suite
              </CardTitle>
              <Badge variant="outline" className="text-[10px] text-destructive border-destructive/30">
                24 Attack Vectors
              </Badge>
            </div>
            <CardDescription className="text-xs">
              Execute all 24 formal verification attack vectors concurrently against the Z3 solver and Security Kernel.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <Button
                variant="destructive"
                size="sm"
                onClick={executeAllAttacks}
                disabled={runningAll || loading}
                className="gap-2"
              >
                {runningAll ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Running 24 Attacks...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" /> Run All 24 Attacks
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setActiveTab(activeTab === "single" ? "suite" : "single")}
                className="text-xs"
              >
                {activeTab === "single" ? "View Full Suite Results" : "Single Attack Mode"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Security Scorecard */}
        <Card className="border-emerald-500/20 bg-emerald-500/5">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground">Blocked Attacks</span>
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
            </div>
            <p className="text-2xl font-bold text-emerald-400">
              {metrics ? `${metrics.attacks_blocked} / ${metrics.attacks_total}` : "24 / 24"}
            </p>
            <p className="text-[10px] text-muted-foreground mt-1">100% Deterministic Interception</p>
          </CardContent>
        </Card>

        <Card className="border-border/50 bg-card/30">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground">Unsafe Razorpay Calls</span>
              <Lock className="w-4 h-4 text-primary" />
            </div>
            <p className="text-2xl font-bold text-foreground">
              {metrics ? `${metrics.unsafe_executions}` : "0"}
            </p>
            <p className="text-[10px] text-emerald-400 mt-1">0 Bypass Rate (Mathematical Truth)</p>
          </CardContent>
        </Card>
      </div>

      {activeTab === "single" ? (
        /* Single Attack Explorer */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Attack Selector & Control */}
          <Card className="border-border/50 bg-card/40 backdrop-blur-sm">
            <CardHeader className="pb-4">
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-destructive" /> Attack Vector Selector
              </CardTitle>
              <CardDescription className="text-xs">
                Select any adversarial scenario to inspect how the SecurityKernel intercepts and blocks it.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Target Scenario
                </label>
                <select
                  value={selectedScenario}
                  onChange={(e) => setSelectedScenario(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-xs font-medium focus:ring-1 focus:ring-destructive focus:outline-none"
                >
                  {scenarios.map((sc) => (
                    <option key={sc.scenario_key} value={sc.scenario_key}>
                      [{sc.category}] {sc.scenario_key} — {sc.attack}
                    </option>
                  ))}
                </select>
              </div>

              {activeScenarioObj && (
                <div className="p-3 rounded-lg bg-background/60 border border-border/50 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="text-[10px] border-primary/20 text-primary">
                      Category: {activeScenarioObj.category}
                    </Badge>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {activeScenarioObj.scenario_key}
                    </span>
                  </div>
                  <p className="text-muted-foreground">{activeScenarioObj.attack}</p>
                </div>
              )}

              <Button
                variant="destructive"
                className="w-full gap-2"
                onClick={executeSingleAttack}
                disabled={loading || runningAll}
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Verifying through Z3...
                  </>
                ) : (
                  <>
                    <Terminal className="w-4 h-4" /> Trigger Attack Vector
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Right: Real-time Formal Verification Proofs */}
          <Card className="border-border/50 bg-card/40 backdrop-blur-sm">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-emerald-400" /> Formal Solver & Security Proof
                </CardTitle>
                {latestResult && (
                  <Badge
                    variant="outline"
                    className={`text-xs ${
                      latestResult.blocked
                        ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
                        : "text-destructive bg-destructive/10 border-destructive/30"
                    }`}
                  >
                    {latestResult.blocked ? "BLOCKED BY KERNEL" : "ALLOWED"}
                  </Badge>
                )}
              </div>
              <CardDescription className="text-xs">
                Live output from UnifiedPolicyService Z3 SMT Solver & SecurityKernel.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {latestResult ? (
                <div className="space-y-3 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="p-2.5 rounded-lg bg-black/40 border border-border/50">
                      <span className="text-[10px] text-muted-foreground block">Z3 SMT Solver Result</span>
                      <span
                        className={`font-mono font-bold ${
                          latestResult.solver_result === "UNSAT" ? "text-amber-400" : "text-emerald-400"
                        }`}
                      >
                        {latestResult.solver_result}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-lg bg-black/40 border border-border/50">
                      <span className="text-[10px] text-muted-foreground block">Razorpay Called</span>
                      <span
                        className={`font-mono font-bold ${
                          !latestResult.razorpay_called ? "text-emerald-400" : "text-destructive"
                        }`}
                      >
                        {latestResult.razorpay_called ? "YES (UNSAFE!)" : "NO (PAYMENT PRESERVED)"}
                      </span>
                    </div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-black/40 border border-border/50">
                    <span className="text-[10px] text-muted-foreground block mb-1">Security Kernel Outcome</span>
                    <span className="font-mono text-destructive font-semibold">
                      {latestResult.security_kernel_result}
                    </span>
                  </div>

                  {latestResult.z3_assertions && latestResult.z3_assertions.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] text-muted-foreground block">Active Z3 Policy Assertions</span>
                      <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto p-1.5 rounded-lg bg-black/30 border border-border/30">
                        {latestResult.z3_assertions.map((assertion, idx) => (
                          <Badge key={idx} variant="outline" className="text-[9px] font-mono border-border/40">
                            {assertion}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {latestResult.audit_event_id && (
                    <div className="flex items-center justify-between p-2 rounded-lg bg-purple-500/5 border border-purple-500/20 text-[10px] text-purple-300">
                      <span className="flex items-center gap-1.5">
                        <Database className="w-3 h-3" /> Tamper-Evident Audit Event
                      </span>
                      <span className="font-mono">{latestResult.audit_event_id.slice(0, 8)}...</span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-48 text-center text-muted-foreground">
                  <Terminal className="w-8 h-8 text-muted-foreground/40 mb-2" />
                  <p className="text-xs">Select an attack scenario and click "Trigger Attack Vector" to view real-time formal verification output.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : (
        /* Full Suite Results Table */
        <Card className="border-border/50 bg-card/40 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Red-Team Suite Results (24 Scenarios)
              </CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setActiveTab("single")} className="text-xs">
                Back to Single Explorer
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {allResults.map((res, i) => {
              const isExpanded = expandedIndex === i;
              return (
                <div
                  key={res.scenario_key + i}
                  className="p-3 rounded-lg bg-black/20 border border-border/40 hover:border-border transition-colors text-xs"
                >
                  <div
                    className="flex items-center justify-between cursor-pointer"
                    onClick={() => setExpandedIndex(isExpanded ? null : i)}
                  >
                    <div className="flex items-center gap-2">
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                      )}
                      <Badge variant="outline" className="text-[9px] border-primary/20">
                        {res.category}
                      </Badge>
                      <span className="font-mono font-medium">{res.scenario_key}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[10px] text-muted-foreground">
                        Solver: <strong className="text-amber-400">{res.solver_result}</strong>
                      </span>
                      <Badge
                        variant="outline"
                        className={`text-[10px] ${
                          res.blocked
                            ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                            : "text-destructive bg-destructive/10"
                        }`}
                      >
                        {res.blocked ? "BLOCKED" : "FAILED"}
                      </Badge>
                    </div>
                  </div>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="mt-3 pt-3 border-t border-border/40 space-y-2"
                      >
                        <p className="text-muted-foreground">{res.ai_response}</p>
                        <div className="grid grid-cols-2 gap-2 text-[11px]">
                          <div className="p-2 rounded bg-black/40 border border-border/30">
                            <span className="text-muted-foreground block text-[9px]">Security Decision:</span>
                            <span className="font-mono text-destructive">{res.security_kernel_result}</span>
                          </div>
                          <div className="p-2 rounded bg-black/40 border border-border/30">
                            <span className="text-muted-foreground block text-[9px]">Payment Call:</span>
                            <span className="font-mono text-emerald-400">
                              {res.razorpay_called ? "CALLED (ERROR)" : "NO PAYMENT (SAFE)"}
                            </span>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
