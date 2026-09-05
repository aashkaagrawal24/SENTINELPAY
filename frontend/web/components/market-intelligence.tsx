"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Globe, CheckCircle2, Search, Zap, AlertCircle, PlusCircle, ExternalLink } from "lucide-react";
import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { apiFetch } from "../lib/api";

interface MarketIntelligenceProps {
  query?: string;
  budgetMinor?: number;
  hasNativeStock?: boolean;
  nativePriceMinor?: number;
  onInstantList?: (productInfo: { name: string; brand: string; category: string; price: number }) => void;
}

export function MarketIntelligence({
  query = "Product",
  budgetMinor,
  hasNativeStock = false,
  nativePriceMinor,
  onInstantList
}: MarketIntelligenceProps) {
  const baseBudget = budgetMinor ? budgetMinor / 100 : 20000;
  const nativePrice = nativePriceMinor ? nativePriceMinor / 100 : Math.round(baseBudget * 0.95);
  
  const referencePrice = nativePriceMinor ? nativePrice / 0.95 : baseBudget;



  const formattedQuery = query.charAt(0).toUpperCase() + query.slice(1);

  const [platforms, setPlatforms] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchIntel() {
      try {
        setIsLoading(true);
        const res = await apiFetch(`/api/market-intelligence?query=${encodeURIComponent(query)}`);
        const data = await res.json();
        
        const apiPlatforms = data.results.map((p: any) => ({
          source: p.source,
          price: `₹${Math.round(p.price_minor / 100).toLocaleString("en-IN")}`,
          match: p.capability === "NEGOTIATION_ONLY" ? "94%" : "99%", 
          negotiable: p.capability === "NEGOTIATION_ONLY" ? "Yes" : "No",
          capability: p.capability === "NEGOTIATION_ONLY" ? "Manual / Unverified" : "Scout / External",
          tier: "external",
          url: p.url,
          rawPrice: p.price_minor
        }));
        
        apiPlatforms.push({
          source: "Sentinel Merchant",
          price: hasNativeStock ? `₹${nativePrice.toLocaleString("en-IN")}` : "Unstocked in Network",
          match: hasNativeStock ? "100%" : "0%",
          negotiable: hasNativeStock ? "Yes" : "N/A",
          capability: hasNativeStock ? "Full Agentic" : "Instant Listing Ready",
          tier: "native",
          rawPrice: hasNativeStock ? nativePriceMinor : 999999999
        });
        
        // Sort by rawPrice ascending
        apiPlatforms.sort((a: any, b: any) => (a.rawPrice || 0) - (b.rawPrice || 0));
        
        setPlatforms(apiPlatforms);
      } catch (err) {
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    }
    fetchIntel();
  }, [query, hasNativeStock, nativePrice, nativePriceMinor]);

  const amazonPrice = platforms.find(p => p.source === "Amazon")?.rawPrice ? Math.round(platforms.find(p => p.source === "Amazon").rawPrice / 100) : 0;


  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
      <Card className="border-blue-500/30 bg-card/60 backdrop-blur-sm overflow-hidden mt-4">
        <CardHeader className="bg-blue-500/5 pb-3 border-b border-blue-500/10">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4 text-blue-400" /> Universal Market Intelligence & Competitor Index
            </CardTitle>
            <Badge variant="outline" className="border-blue-500/30 text-blue-400 bg-blue-500/10 flex items-center gap-1 text-[11px]">
              <Search className="w-3 h-3" /> Sentinel Scout Live
            </Badge>
          </div>
          <CardDescription className="text-xs">
            Cross-platform price mapping for <strong>&quot;{formattedQuery}&quot;</strong> across primary Indian retailers.
          </CardDescription>
        </CardHeader>

        <CardContent className="p-0">
          {!hasNativeStock && (
            <div className="p-3 bg-amber-500/10 border-b border-amber-500/20 text-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-amber-300">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
                <span>
                  <strong>Sentinel Merchant</strong> currently doesn&apos;t stock &quot;{formattedQuery}&quot;, but competitor market prices are mapped below.
                </span>
              </div>
              {onInstantList && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="text-xs h-7 gap-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/30 shrink-0"
                  onClick={() => onInstantList({
                    name: formattedQuery,
                    brand: query.split(" ")[0]?.toUpperCase() || "Universal",
                    category: "General",
                    price: nativePrice
                  })}
                >
                  <PlusCircle className="w-3.5 h-3.5" /> Instant Stock in Sentinel
                </Button>
              )}
            </div>
          )}

          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow className="text-xs">
                <TableHead className="w-[180px] pl-4">Platform</TableHead>
                <TableHead>Market Price</TableHead>
                <TableHead>Match</TableHead>
                <TableHead>Negotiable</TableHead>
                <TableHead className="text-right pr-4">Execution Protocol</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="text-xs">
              {platforms.map((p, i) => (
                <TableRow key={i} className={p.tier === "native" ? "bg-blue-500/10 hover:bg-blue-500/15 border-blue-500/20" : ""}>
                  <TableCell className="font-medium flex items-center gap-2 pl-4">
                    {p.tier === "native" ? (
                      <Zap className="w-3.5 h-3.5 text-blue-400 fill-blue-400/20" />
                    ) : (
                      <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                    )}
                    <span>{p.source}</span>
                  </TableCell>
                  <TableCell className="font-mono">{p.price}</TableCell>
                  <TableCell>
                    <Badge variant={p.match === "100%" ? "default" : "secondary"} className="font-mono text-[10px]">
                      {p.match}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {p.negotiable === "Yes" ? (
                      <span className="text-emerald-400 font-medium flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Yes
                      </span>
                    ) : (
                      <span className="text-muted-foreground">{p.negotiable}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right pr-4">
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${
                      p.capability === "Full Agentic"
                        ? "bg-blue-600 text-white"
                        : p.capability === "Instant Listing Ready"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                        : "bg-muted text-muted-foreground"
                    }`}>
                      {p.capability}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="p-3 px-4 bg-muted/20 text-xs flex flex-col gap-1.5 border-t border-border/40">
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="text-blue-400 font-mono">↳</span>
              <p>
                <strong>Competitive Analysis:</strong> Lowest external retail price is on Amazon at ₹{amazonPrice.toLocaleString("en-IN")}.
              </p>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="text-emerald-400 font-mono">↳</span>
              <p>
                <strong>Sentinel Autonomous Advantage:</strong> Sentinel merchants support mathematical Z3 bounded negotiation and cryptographic checkout without redirecting to third-party web forms.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
