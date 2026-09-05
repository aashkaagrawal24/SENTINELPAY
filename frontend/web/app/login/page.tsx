"use client";

import { FormEvent, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Shield, Sparkles } from "lucide-react";

export default function Login() { 
  const [email,setEmail]=useState(""); 
  const [password,setPassword]=useState(""); 
  const [message,setMessage]=useState(""); 
  const [loading,setLoading]=useState(false); 

  async function submit(e:FormEvent<HTMLFormElement>) { 
    e.preventDefault(); 
    setLoading(true); 
    setMessage("");
    
    if (email.startsWith("demo")) { 
      localStorage.setItem("demo_session", email); 
      location.assign("/app"); 
      return; 
    } 
    
    const {error}=await supabase.auth.signInWithPassword({email,password}); 
    setLoading(false); 
    
    if(error) setMessage(error.message); 
    else location.assign("/app"); 
  } 

  async function signUp() { 
    setLoading(true); 
    setMessage("");
    
    if (email.startsWith("demo")) { 
      localStorage.setItem("demo_session", email); 
      location.assign("/app"); 
      return; 
    } 
    
    const {data, error}=await supabase.auth.signUp({email,password}); 
    setLoading(false); 
    
    if(error) setMessage(error.message); 
    else if(data.session) location.assign("/app"); 
    else setMessage("Check your email to confirm your account."); 
  } 

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[500px] bg-primary/20 blur-[120px] rounded-full -z-10" />
      
      <div className="mb-8 text-center space-y-4">
        <div className="flex justify-center">
          <div className="p-3 bg-primary/10 rounded-2xl ring-1 ring-primary/20">
            <Shield className="w-10 h-10 text-primary" />
          </div>
        </div>
        <h1 className="text-4xl font-bold tracking-tight">SentinelPay</h1>
        <p className="text-muted-foreground text-lg">Secure agentic commerce gateway</p>
      </div>

      <Card className="w-full max-w-md border-border/50 bg-background/60 backdrop-blur-xl">
        <form onSubmit={submit}>
          <CardHeader>
            <CardTitle className="text-2xl">Authentication</CardTitle>
            <CardDescription>Enter your credentials to access the gateway</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input 
                id="email" 
                type="email" 
                placeholder="agent@sentinelpay.com"
                value={email} 
                onChange={e=>setEmail(e.target.value)} 
                required 
                disabled={loading} 
                className="bg-background/50"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input 
                id="password" 
                type="password" 
                value={password} 
                onChange={e=>setPassword(e.target.value)} 
                required 
                disabled={loading} 
                className="bg-background/50"
              />
            </div>
            
            {message && (
              <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md border border-destructive/20">
                {message}
              </div>
            )}
            
            <div className="pt-2 flex flex-col gap-3">
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? 'Authenticating...' : 'Log In'}
              </Button>
              <Button type="button" variant="outline" onClick={signUp} disabled={loading} className="w-full">
                {loading ? 'Creating...' : 'Create Account'}
              </Button>
            </div>
          </CardContent>
          <CardFooter className="flex flex-col border-t border-border/50 bg-muted/20 px-6 py-4">
            <p className="text-sm text-muted-foreground mb-3 text-center">
              Having Supabase connection issues?
            </p>
            <Button 
              type="button" 
              variant="secondary" 
              className="w-full gap-2"
              onClick={() => { setEmail("demo@sentinelpay.com"); setPassword("demo123"); }}
            >
              <Sparkles className="w-4 h-4" />
              Use Demo Account
            </Button>
          </CardFooter>
        </form>
      </Card>
    </main>
  );
}
