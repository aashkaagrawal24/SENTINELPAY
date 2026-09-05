"use client";

import { useState } from "react";

export type ProvenanceEvidence = {
  value: string;
  unit?: string;
  valueType: string;
  trustClass: string;
  method: string;
  source: string;
  confidence?: number;
  financialAuthority: "ALLOWED" | "NONE";
  updatedAt: string;
};

export function ProvenanceDrawer({ label, evidence }: { label: string; evidence: ProvenanceEvidence }) {
  const [open, setOpen] = useState(false);
  return <div className="provenance">
    <button className="info-button" aria-expanded={open} onClick={() => setOpen(value => !value)}>i</button>
    <strong>{label}</strong>
    {open && <aside className="provenance-drawer">
      <h3>Value provenance</h3>
      <dl>
        <dt>Value</dt><dd>{evidence.value} {evidence.unit}</dd>
        <dt>Type / trust</dt><dd>{evidence.valueType} / {evidence.trustClass}</dd>
        <dt>Method</dt><dd>{evidence.method}</dd>
        <dt>Source</dt><dd>{evidence.source}</dd>
        <dt>Confidence</dt><dd>{evidence.confidence == null ? "Not applicable" : `${Math.round(evidence.confidence * 100)}%`}</dd>
        <dt>Financial authority</dt><dd className={evidence.financialAuthority === "ALLOWED" ? "safe" : "blocked"}>{evidence.financialAuthority}</dd>
        <dt>Updated</dt><dd>{new Date(evidence.updatedAt).toLocaleString()}</dd>
      </dl>
    </aside>}
  </div>;
}
