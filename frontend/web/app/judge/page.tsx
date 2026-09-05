"use client";
import { ArrowLeft, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { JudgeSimulator } from "../../components/judge-simulator";

export default function JudgePage() {
  return (
    <div className="min-h-screen bg-background pb-12">
      {/* Top Navigation */}
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
            <span className="font-bold tracking-tight text-sm text-destructive flex items-center gap-2">
              <Terminal className="w-4 h-4" /> BREAK SENTINELPAY
            </span>
          </div>
          <span className="inline-flex items-center rounded-md bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive ring-1 ring-inset ring-destructive/20 animate-pulse">
            CONTROLLED JUDGE MODE
          </span>
        </div>
      </header>

      <main className="container max-w-7xl mx-auto p-4 md:p-8 pt-8 space-y-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Adversarial Control Room</h1>
          <p className="text-muted-foreground text-lg max-w-3xl">
            Try to make the money boundary blink. Simulate malicious vectors to test the Z3 Security Kernel and Provenance Verifier in real-time.
          </p>
        </div>

        <JudgeSimulator />
      </main>
    </div>
  );
}
