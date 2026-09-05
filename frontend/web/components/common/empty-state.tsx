import React from "react";
import { LucideIcon, PackageOpen } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: LucideIcon;
  actionLabel?: string;
  onAction?: () => void;
  actionHref?: string;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon: Icon = PackageOpen,
  actionLabel,
  onAction,
  actionHref,
  className = "",
}: EmptyStateProps) {
  return (
    <div className={`glass-panel rounded-2xl p-10 text-center flex flex-col items-center justify-center border border-border/40 ${className}`}>
      <div className="p-4 rounded-2xl bg-muted/30 border border-border/40 text-muted-foreground mb-4">
        <Icon className="w-8 h-8 opacity-70" />
      </div>
      <h3 className="text-base font-semibold text-foreground tracking-tight">
        {title}
      </h3>
      <p className="text-sm text-muted-foreground max-w-sm mt-1 mb-6 leading-relaxed">
        {description}
      </p>
      {actionLabel && (
        actionHref ? (
          <Button size="sm" asChild className="gap-2">
            <a href={actionHref}>{actionLabel}</a>
          </Button>
        ) : (
          <Button size="sm" onClick={onAction} className="gap-2">
            {actionLabel}
          </Button>
        )
      )}
    </div>
  );
}
