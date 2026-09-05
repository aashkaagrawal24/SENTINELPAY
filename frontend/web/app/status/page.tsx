"use client";
import { useEffect, useState } from "react";
export default function Status(){const [status,setStatus]=useState("Checking backend...");useEffect(()=>{fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/health`).then(r=>r.json()).then(x=>setStatus(x.status)).catch(()=>setStatus("Backend unavailable"));},[]);return <main><h1>Local status</h1><p>{status}</p></main>}
