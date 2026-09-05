import { supabase } from "./supabase";

function getBaseBackendUrl(): string {
  let backendUrl = (process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001")
    .replace(/['"]/g, "")
    .trim();

  if (backendUrl.endsWith(":8000")) {
    backendUrl = backendUrl.replace(":8000", ":8001");
  }

  // In the browser, align hostname with window.location to prevent Chrome PNA & cross-origin blocking
  if (typeof window !== "undefined") {
    const currentHost = window.location.hostname;
    if (currentHost === "localhost") {
      backendUrl = backendUrl.replace("127.0.0.1", "localhost");
    } else if (currentHost === "127.0.0.1") {
      backendUrl = backendUrl.replace("localhost", "127.0.0.1");
    }
  }

  return backendUrl;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  let token: string | undefined;
  try {
    const { data } = await supabase.auth.getSession();
    token = data.session?.access_token || (typeof window !== "undefined" && localStorage.getItem("demo_session") ? "demo_token" : undefined);
  } catch {
    if (typeof window !== "undefined" && localStorage.getItem("demo_session")) {
      token = "demo_token";
    }
  }

  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  const defaultHeaders: Record<string, string> = {};
  if (!isFormData) {
    defaultHeaders["Content-Type"] = "application/json";
  }
  if (token) {
    defaultHeaders["Authorization"] = `Bearer ${token}`;
  }

  const baseBackend = getBaseBackendUrl();
  const primaryUrl = `${baseBackend}${path}`;

  const requestOptions: RequestInit = {
    ...init,
    headers: {
      ...defaultHeaders,
      ...init.headers
    }
  };

  try {
    return await fetch(primaryUrl, requestOptions);
  } catch (primaryErr) {
    // If primary failed, try alternate loopback host (swap localhost <-> 127.0.0.1)
    let alternateUrl: string | null = null;
    if (primaryUrl.includes("localhost")) {
      alternateUrl = primaryUrl.replace("localhost", "127.0.0.1");
    } else if (primaryUrl.includes("127.0.0.1")) {
      alternateUrl = primaryUrl.replace("127.0.0.1", "localhost");
    }

    if (alternateUrl) {
      try {
        console.warn(`[apiFetch] Retrying on alternate host: ${alternateUrl}`);
        return await fetch(alternateUrl, requestOptions);
      } catch {
        // Fall through to graceful error response
      }
    }

    console.warn(`[apiFetch] Failed to connect to ${primaryUrl}:`, primaryErr);

    // Return safe synthetic 503 response instead of crashing with uncaught TypeError
    return new Response(
      JSON.stringify({
        error: "Backend unavailable",
        detail: `Could not connect to SentinelPay API at ${primaryUrl}`,
        merchants: [],
        products: [],
        results: [],
        orders: [],
        metrics: {}
      }),
      {
        status: 503,
        statusText: "Service Unavailable",
        headers: { "Content-Type": "application/json" }
      }
    );
  }
}

