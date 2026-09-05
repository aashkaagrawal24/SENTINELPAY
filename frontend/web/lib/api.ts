import { supabase } from "./supabase";

export async function apiFetch(path: string, init: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token || (typeof window !== "undefined" && localStorage.getItem("demo_session") ? "demo_token" : undefined);
  let backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8001";
  if (backendUrl.includes("localhost")) {
    backendUrl = backendUrl.replace("localhost", "127.0.0.1");
  }
  if (backendUrl.endsWith(":8000")) {
    backendUrl = backendUrl.replace(":8000", ":8001");
  }

  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  const defaultHeaders: Record<string, string> = {};
  if (!isFormData) {
    defaultHeaders["Content-Type"] = "application/json";
  }
  if (token) {
    defaultHeaders["Authorization"] = `Bearer ${token}`;
  }

  const url = `${backendUrl}${path}`;
  console.log(`[apiFetch] Fetching: ${url}`);
  
  return fetch(url, {
    ...init,
    headers: {
      ...defaultHeaders,
      ...init.headers
    }
  });
}
