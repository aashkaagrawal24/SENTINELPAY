import React from "react";
import { motion } from "framer-motion";
import { 
  Bot, Search, Store, Scale, ShieldCheck, CreditCard, FileCheck, AlertCircle, CheckCircle2, Loader2, Sparkles
} from "lucide-react";

export interface TimelineStep {
  id: string;
  label?: string;
  title?: string;
  description: string;
  icon?: React.ComponentType<{ className?: string }>;
  status: "pending" | "processing" | "running" | "completed" | "success" | "warning" | "failed" | "blocked" | "skipped";
  timestamp?: string;
  detail?: string;
}

export type ExecutionStep = TimelineStep;

interface AgentExecutionTimelineProps {
  steps: TimelineStep[];
  className?: string;
}

export function AgentExecutionTimeline({ steps, className = "" }: AgentExecutionTimelineProps) {
  const defaultIcons = [Search, Store, Sparkles, Scale, CreditCard, FileCheck];

  return (
    <div className={`glass-panel rounded-2xl p-5 border border-border/60 ${className}`}>
      <div className="flex items-center justify-between pb-4 border-b border-border/40 mb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-xl bg-primary/10 text-primary border border-primary/20">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-foreground tracking-tight">
              Autonomous Agent Execution Pipeline
            </h4>
            <p className="text-[11px] text-muted-foreground">
              Real-time multi-merchant discovery, Z3 policy equilibrium, and server-side payment gating
            </p>
          </div>
        </div>
        <span className="text-[10px] font-mono uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
          Agentic Flow
        </span>
      </div>

      <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-[1.5px] before:bg-gradient-to-b before:from-primary/40 before:via-emerald-500/30 before:to-border/20">
        {steps.map((step, idx) => {
          const StepIcon = step.icon || defaultIcons[idx % defaultIcons.length] || Bot;
          const isRunning = step.status === "running" || step.status === "processing";
          const isCompleted = step.status === "completed" || step.status === "success";
          const isFailed = step.status === "failed" || step.status === "blocked";

          let nodeBg = "bg-muted/80 border-border/60 text-muted-foreground";
          let statusBadge = null;

          if (isCompleted) {
            nodeBg = "bg-emerald-500/20 border-emerald-500/40 text-emerald-400";
            statusBadge = (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-emerald-400 font-medium">
                <CheckCircle2 className="w-3 h-3" /> VERIFIED
              </span>
            );
          } else if (isRunning) {
            nodeBg = "bg-primary/20 border-primary text-primary animate-pulse-glow";
            statusBadge = (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-primary font-medium">
                <Loader2 className="w-3 h-3 animate-spin" /> ACTIVE
              </span>
            );
          } else if (isFailed) {
            nodeBg = "bg-rose-500/20 border-rose-500 text-rose-400";
            statusBadge = (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-rose-400 font-medium">
                <AlertCircle className="w-3 h-3" /> DENIED
              </span>
            );
          }

          const displayTitle = step.title || step.label || "Step";

          return (
            <motion.div
              key={step.id || idx}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.05 }}
              className="relative flex items-start justify-between gap-4"
            >
              {/* Dot Icon */}
              <div
                className={`absolute -left-6 top-0.5 h-5 w-5 rounded-full border flex items-center justify-center ${nodeBg}`}
              >
                <StepIcon className="w-2.5 h-2.5" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold ${isRunning ? "text-primary" : isCompleted ? "text-foreground" : "text-muted-foreground"}`}>
                    {displayTitle}
                  </span>
                  {statusBadge}
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                  {step.description}
                </p>
                {step.detail && (
                  <p className="text-[10px] font-mono text-primary/80 mt-1 bg-black/40 px-2 py-0.5 rounded border border-primary/20 inline-block">
                    {step.detail}
                  </p>
                )}
              </div>

              {step.timestamp && (
                <span className="text-[10px] font-mono text-muted-foreground/60 whitespace-nowrap">
                  {step.timestamp}
                </span>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
