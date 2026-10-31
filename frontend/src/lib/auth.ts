import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";

export type { User };
export const LOGIN_REQUIRED_MESSAGE = "GitHub로 로그인한 뒤 검사할 수 있습니다.";

// NEXT_PUBLIC 값은 Next.js 빌드 때 브라우저 코드에 들어갑니다. 비밀키를 넣지 않습니다.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
let client: SupabaseClient | null = null;

export function isAuthEnabled(): boolean {
  return Boolean(supabaseUrl && publishableKey);
}

function sessionWithoutProviderTokens(value: string): string {
  try {
    const session = JSON.parse(value);
    if (session && typeof session === "object" && !Array.isArray(session)) {
      delete session.provider_token;
      delete session.provider_refresh_token;
      return JSON.stringify(session);
    }
  } catch { /* PKCE verifier is a plain string, not a session JSON. */ }
  return value;
}

function authClient(): SupabaseClient | null {
  if (!isAuthEnabled() || typeof window === "undefined") return null;
  if (!client) {
    client = createClient(supabaseUrl!, publishableKey!, {
      auth: {
        flowType: "pkce",
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
        // SDK 기본 저장은 provider 토큰도 포함합니다. Supabase 세션과 PKCE verifier만 보관합니다.
        storage: {
          getItem: key => window.localStorage.getItem(key),
          setItem: (key, value) => window.localStorage.setItem(key, sessionWithoutProviderTokens(value)),
          removeItem: key => window.localStorage.removeItem(key),
        },
      },
    });
  }
  return client;
}

export async function signInWithGitHub(): Promise<void> {
  const supabase = authClient();
  if (!supabase) return;
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "github",
    options: { redirectTo: window.location.href },
  });
  if (error) throw new Error("GitHub 로그인을 시작하지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
}

export async function signOut(): Promise<void> {
  const supabase = authClient();
  if (!supabase) return;
  const { error } = await supabase.auth.signOut({ scope: "local" });
  if (error) throw new Error("로그아웃하지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
}

export async function getCurrentUser(): Promise<User | null> {
  const supabase = authClient();
  if (!supabase) return null;
  const { data, error } = await supabase.auth.getSession();
  if (error) throw new Error(LOGIN_REQUIRED_MESSAGE);
  return data.session?.user ?? null;
}

export function subscribeAuth(callback: (user: User | null) => void): () => void {
  const supabase = authClient();
  if (!supabase) return () => {};
  // INITIAL_SESSION도 SDK가 보냅니다. 콜백 안에서는 다른 async auth 호출을 기다리지 않습니다.
  const { data } = supabase.auth.onAuthStateChange((_event, session) => callback(session?.user ?? null));
  return () => data.subscription.unsubscribe();
}

export function getGitHubUsername(user: User): string {
  for (const field of ["preferred_username", "user_name"]) {
    const value = user.user_metadata[field];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

export async function getAccessToken(): Promise<string | null> {
  const supabase = authClient();
  if (!supabase) return null;
  const { data, error } = await supabase.auth.getSession();
  if (error) throw new Error(LOGIN_REQUIRED_MESSAGE);
  return data.session?.access_token ?? null;
}

/** 상대 /api 경로에만 Supabase 토큰을 붙입니다. 외부 주소는 인증 상태도 읽지 않습니다. */
export async function apiFetch(path: string, options?: RequestInit): Promise<Response> {
  const relativeApi = /^\/api(?:\/|\?|$)/.test(path) && !path.includes("\\");
  const pathname = relativeApi ? new URL(path, "https://local.invalid").pathname : "";
  if (!relativeApi || !(pathname === "/api" || pathname.startsWith("/api/"))) return fetch(path, options);
  let token: string | null = null;
  try {
    token = await getAccessToken();
  } catch { /* 토큰 조회가 실패해도 요청을 보내고, 인증 필요 여부는 서버의 401로 판단합니다. */ }
  if (!token) return fetch(path, options);
  const headers = new Headers(options?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return fetch(path, { ...options, headers });
}
