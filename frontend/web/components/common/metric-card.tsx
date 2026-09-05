import React from "react";
import { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { motion } from "framer-motion";

export interface MetricCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  subtitle?: string;
  icon?: LucideIcon;
  badge?: string;
  colorTheme?: "blue" | "emerald" | "amber" | "indigo" | "purple" | string;
  theme?: "blue" | "emerald" | "amber" | "indigo" | "purple" | string;
  delay?: number;
  className?: string;
}

export function MetricCard({
  title,
  value,
  change,
  changeType = "positive",
  subtitle,
  icon: Icon,
  badge,
  colorTheme,
  theme,
  delay = 0,
  className = "",
}: MetricCardProps) {
  const selectedTheme = (theme || colorTheme || "blue") as "blue" | "emerald" | "amber" | "indigo" | "purple";
  
  const themeClasses: Record<string, { border: string; iconBg: string; glow: string }> = {
    blue: {
      border: "border-blue-500/20 hover:border-blue-500/40",
      iconBg: "bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20",
      glow: "hover:shadow-[0_0_25px_rgba(59,130,246,0.15)]",
    },
    emerald: {
      border: "border-emerald-500/20 hover:border-emerald-500/40",
      iconBg: "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20",
      glow: "hover:shadow-[0_0_25px_rgba(16,185,129,0.15)]",
    },
    amber: {
      border: "border-amber-500/20 hover:border-amber-500/40",
      iconBg: "bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20",
      glow: "hover:shadow-[0_0_25px_rgba(245,158,11,0.15)]",
    },
    indigo: {
      border: "border-indigo-500/20 hover:border-indigo-500/40",
      iconBg: "bg-indigo-500/10 text-indigo-400 ring-1 ring-indigo-500/20",
      glow: "hover:shadow-[0_0_25px_rgba(99,102,241,0.15)]",
    },
    purple: {
      border: "border-purple-500/20 hover:border-purple-500/40",
      iconBg: "bg-purple-500/10 text-purple-400 ring-1 ring-purple-500/20",
      glow: "hover:shadow-[0_0_25px_rgba(168,85,247,0.15)]",
    },
  };

  const currentTheme = themeClasses[selectedTheme] || themeClasses.blue;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="h-full"
    >
      <Card className={`glass-panel h-full ${currentTheme.border} ${currentTheme.glow} transition-all duration-300 ${className}`}>
        <CardContent className="p-5">
          <div className="flex items-center justify-between gap-2 mb-3">
            <span className="text-xs font-medium text-muted-foreground tracking-wide uppercase">
              {title}
            </span>
            <div className="flex items-center gap-2">
              {badge && (
                <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-muted/60 text-muted-foreground border border-border/40">
                  {badge}
                </span>
              )}
              {Icon && (
                <div className={`p-2 rounded-lg ${currentTheme.iconBg}`}>
                  <Icon className="w-4 h-4" />
                </div>
              )}
            </div>
          </div>

          <div className="flex items-baseline justify-between gap-2">
            <div className="text-2xl font-bold tracking-tight text-foreground font-mono">
              {value}
            </div>
            {change && (
              <span
                className={`text-xs font-semibold ${
                  changeType === "positive"
                    ? "text-emerald-400"
                    : changeType === "negative"
                    ? "text-rose-400"
                    : "text-muted-foreground"
                }`}
              >
                {change}
              </span>
            )}
          </div>

          {subtitle && (
            <p className="text-[11px] text-muted-foreground mt-1.5 line-clamp-1">
              {subtitle}
            </p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
