import React from "react";

export interface StatusBadgeProps {
  status?: string;
  variant?: "success" | "danger" | "amber" | "blue" | "purple" | "neutral" | string;
  className?: string;
}

export function StatusBadge({ status = "UNKNOWN", variant, className = "" }: StatusBadgeProps) {
  const s = status.toUpperCase();

  let dotColor = "bg-muted-foreground";
  let badgeStyle = "bg-muted/40 text-muted-foreground border-border/40";
  let label = status;

  if (variant) {
    switch (variant) {
      case "success":
        dotColor = "bg-emerald-400";
        badgeStyle = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
        break;
      case "danger":
        dotColor = "bg-rose-500";
        badgeStyle = "bg-rose-500/10 text-rose-400 border-rose-500/20";
        break;
      case "amber":
        dotColor = "bg-amber-400 animate-pulse";
        badgeStyle = "bg-amber-500/10 text-amber-300 border-amber-500/20";
        break;
      case "blue":
        dotColor = "bg-blue-400";
        badgeStyle = "bg-blue-500/10 text-blue-400 border-blue-500/20";
        break;
      case "purple":
        dotColor = "bg-purple-400";
        badgeStyle = "bg-purple-500/10 text-purple-300 border-purple-500/20";
        break;
      default:
        dotColor = "bg-muted-foreground";
        badgeStyle = "bg-muted/40 text-muted-foreground border-border/40";
    }
  } else {
    if (["CAPTURED", "SUCCESS", "COMPLETED", "ACTIVE", "CONVERTED", "ALLOW"].includes(s)) {
      dotColor = "bg-emerald-400";
      badgeStyle = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      label = s === "CAPTURED" ? "Captured" : s === "ACTIVE" ? "Active" : s === "COMPLETED" ? "Completed" : "Success";
    } else if (["FAILED", "DENIED", "REJECTED", "CANCELLED", "DENY"].includes(s)) {
      dotColor = "bg-rose-500";
      badgeStyle = "bg-rose-500/10 text-rose-400 border-rose-500/20";
      label = s === "FAILED" ? "Failed" : s === "DENIED" ? "Denied" : "Rejected";
    } else if (["PROCESSING", "POLICY_CHECKING", "PAYMENT_PROCESSING", "RUNNING", "CONFIRMATION_REQUIRED", "REQUIRE_APPROVAL"].includes(s)) {
      dotColor = "bg-amber-400 animate-pulse";
      badgeStyle = "bg-amber-500/10 text-amber-300 border-amber-500/20";
      label = s === "POLICY_CHECKING" ? "Policy Checking" : s === "REQUIRE_APPROVAL" ? "Approval Required" : "Processing";
    } else if (["READY", "PENDING", "CREATED"].includes(s)) {
      dotColor = "bg-blue-400";
      badgeStyle = "bg-blue-500/10 text-blue-400 border-blue-500/20";
      label = s === "READY" ? "Ready" : "Pending";
    }
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${badgeStyle} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      <span>{label}</span>
    </span>
  );
}
