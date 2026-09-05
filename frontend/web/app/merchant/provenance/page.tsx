"use client";

import { ProvenanceDrawer } from "../../../components/provenance";

export default function MerchantProvenancePage() {
  const now = new Date().toISOString();
  return <main>
    <nav className="topbar"><a href="/app">Home</a><a href="/merchant/analytics">Revenue Analytics</a><strong>MERCHANT PROVENANCE</strong></nav>
    <section className="card"><span className="badge">TRUST INSPECTOR</span><h1>Where money values come from</h1><p>These examples show the authority rules used by merchant and judge surfaces.</p></section>
    <section className="grid">
      <article className="card"><h2>Final captured amount</h2><ProvenanceDrawer label="Verified payment value" evidence={{value:"Transaction-specific",unit:"minor currency units",valueType:"REAL_DATA",trustClass:"RAZORPAY_VERIFIED",method:"Trusted backend API/webhook verification",source:"Razorpay Test Mode",financialAuthority:"ALLOWED",updatedAt:now}}/></article>
      <article className="card"><h2>Expected negotiated price</h2><ProvenanceDrawer label="Model estimate" evidence={{value:"Illustrative prediction",unit:"minor currency units",valueType:"MODEL_ESTIMATE",trustClass:"MODEL_INFERRED",method:"Model proposal",source:"ModelGateway",confidence:0.7,financialAuthority:"NONE",updatedAt:now}}/></article>
      <article className="card"><h2>Simulated campaign lift</h2><ProvenanceDrawer label="Evaluation-only metric" evidence={{value:"Synthetic cohort result",valueType:"SIMULATED",trustClass:"SYSTEM_DERIVED",method:"Seeded deterministic generator",source:"SentinelPay analytics evaluator",financialAuthority:"NONE",updatedAt:now}}/></article>
    </section>
  </main>;
}
