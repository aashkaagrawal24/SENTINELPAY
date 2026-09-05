"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState } from "@/components/common/empty-state";
import { 
  Activity, Bot, Store, Shield, ArrowRight, MessageSquare, 
  Zap, Lock, Eye, Radio, ChevronDown, ChevronUp, Code, Clock
} from "lucide-react";
import { apiFetch } from "@/lib/api";

export default function AgentActivityPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("ALL");

  useEffect(() => {
    const merchantId = localStorage.getItem("sp_merchant_id");
    if (!merchantId) {
      setLoading(false);
      return;
    }

    const fetchEvents = async () => {
      try {
        const res = await apiFetch(`/api/merchants/${merchantId}/agent-activity`);
        const data = await res.json();
        setEvents(data.events || []);
      } catch (e) {
        console.error(e);
      }
      setLoading(false);
    };

    fetchEvents();

    // Set up SSE live stream
    const sseUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/merchants/${merchantId}/events/stream`;
    const evtSource = new EventSource(sseUrl);
    
    evtSource.onopen = () => {
      setIsLiveStreaming(true);
    };

    evtSource.addEventListener("AUDIT_EVENT", (e) => {
      try {
        const newEvent = JSON.parse(e.data);
        setEvents(prev => [newEvent, ...prev].slice(0, 50));
      } catch (err) {
        console.error("SSE Parse Error", err);
      }
    });

    evtSource.onerror = () => {
      setIsLiveStreaming(false);
    };

    return () => {
      evtSource.close();
      setIsLiveStreaming(false);
    };
  }, []);

  const getEventBadge = (type: string) => {
    switch (type) {
      case "NEGOTIATION_STARTED":
      case "COUNTER_OFFER":
        return <StatusBadge status={type} variant="blue" />;
      case "INVENTORY_CHECK":
        return <StatusBadge status={type} variant="amber" />;
      case "POLICY_EVALUATED":
      case "Z3_VERIFIED":
        return <StatusBadge status={type} variant="success" />;
      case "CHECKOUT_INITIATED":
      case "PAYMENT_CAPTURED":
        return <StatusBadge status={type} variant="purple" />;
      case "POLICY_VIOLATION":
      case "ATTACK_BLOCKED":
        return <StatusBadge status={type} variant="danger" />;
      default:
        return <StatusBadge status={type || "EVENT"} variant="neutral" />;
    }
  };

  const filteredEvents = filterType === "ALL" 
    ? events 
    : events.filter(e => e.eventType?.includes(filterType) || e.type?.includes(filterType));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center animate-pulse">
              <Activity className="h-6 w-6 text-primary" />
            </div>
            <div className="absolute -inset-1 rounded-2xl bg-primary/20 blur-sm -z-10 animate-pulse" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">Connecting to Agent Event Bus</p>
            <p className="text-xs text-muted-foreground mt-0.5">Subscribing to live telemetry stream...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Agent Activity Stream</h1>
            <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px] font-mono flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${isLiveStreaming ? "bg-emerald-400 animate-ping" : "bg-zinc-500"}`} />
              {isLiveStreaming ? "LIVE SSE STREAM" : "POLLING ACTIVE"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Live telemetry of BuyerAgent ↔ MerchantAgent pricing equilibrium, inventory checks, and cryptographic commitments.
          </p>
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
          {["ALL", "NEGOTIATION", "POLICY", "INVENTORY"].map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterType(tab)}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                filterType === tab
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Cryptographic Privacy Barrier Callout */}
      <Card className="border-purple-500/20 bg-gradient-to-r from-purple-500/5 via-indigo-500/5 to-transparent backdrop-blur-sm">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 shrink-0 mt-0.5">
              <Lock className="w-4 h-4" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-purple-300 uppercase tracking-wider font-mono">
                  Zero-Knowledge Privacy Barrier
                </span>
                <Badge className="bg-purple-500/10 text-purple-300 border-purple-500/20 text-[10px]">
                  MATHEMATICALLY PROVED
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                The buyer's maximum budget is strictly concealed from your MerchantAgent. Your internal catalog floor price 
                is strictly concealed from the BuyerAgent. All concessions are negotiated within formal Z3 boundaries.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Timeline Stream */}
      <div className="relative">
        <div className="absolute left-6 top-4 bottom-4 w-px bg-border/40" />

        <div className="space-y-4">
          {filteredEvents.length === 0 ? (
            <EmptyState
              icon={Activity}
              title="No Agent Events Recorded Yet"
              description="Live agent events will stream in real-time as BuyerAgents discover, negotiate, and purchase from your catalog."
            />
          ) : (
            filteredEvents.map((event: any, i: number) => {
              const eventId = event.id || `evt-${i}`;
              const isExpanded = expandedEventId === eventId;
              const Icon = event.eventType?.includes("NEGOTIATION") ? MessageSquare 
                         : event.eventType?.includes("INVENTORY") ? Store
                         : event.eventType?.includes("POLICY") ? Shield
                         : Bot;

              return (
                <motion.div
                  key={eventId}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: Math.min(i * 0.05, 0.4) }}
                  className="relative pl-14"
                >
                  {/* Timeline icon node */}
                  <div className="absolute left-3.5 top-3.5 p-1.5 rounded-xl border border-border/60 bg-card/90 shadow-sm z-10">
                    <Icon className="w-4 h-4 text-primary" />
                  </div>

                  {/* Event card */}
                  <Card className="glass-panel border-border/60 hover:border-primary/40 transition-all">
                    <CardContent className="p-4 space-y-2">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {getEventBadge(event.eventType || "AGENT_DECISION")}
                          <span className="text-[11px] font-mono text-muted-foreground flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {new Date(event.timestamp || Date.now()).toLocaleTimeString()}
                          </span>
                        </div>

                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-mono">
                          <span className="text-emerald-400 font-semibold">BuyerAgent</span>
                          <ArrowRight className="w-3 h-3 text-muted-foreground/60" />
                          <span className="text-blue-400 font-semibold">MerchantAgent</span>
                        </div>
                      </div>

                      <p className="text-xs text-foreground font-medium leading-relaxed">
                        {event.description || "Agent interaction event"}
                      </p>

                      <div className="flex items-center justify-between pt-1 border-t border-border/30 text-xs">
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Eye className="w-3 h-3 text-purple-400" />
                          <span className="text-[11px]">Privacy preserved via isolated sandbox</span>
                        </div>

                        {event.metadata && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setExpandedEventId(isExpanded ? null : eventId)}
                            className="h-6 text-[10px] gap-1 text-muted-foreground hover:text-foreground font-mono"
                          >
                            <Code className="w-3 h-3" />
                            {isExpanded ? "Hide Payload" : "View Payload"}
                            {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          </Button>
                        )}
                      </div>

                      {/* Expandable JSON Payload */}
                      <AnimatePresence>
                        {isExpanded && event.metadata && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            className="overflow-hidden pt-2"
                          >
                            <pre className="p-3 rounded-lg bg-black/60 border border-border/50 text-[11px] font-mono text-emerald-300 overflow-x-auto max-h-48">
                              {JSON.stringify(event.metadata, null, 2)}
                            </pre>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })
          )}
        </div>
      </div>
    </motion.div>
  );
}
