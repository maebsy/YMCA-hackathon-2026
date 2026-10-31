import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const enabledEnv = { NEXT_PUBLIC_SUPABASE_URL: "https://auth.example.invalid", NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "test-publishable" };
const user = { id: "user-id", user_metadata: { preferred_username: "octocat", user_name: "legacy" } };

function harness({ env = enabledEnv, browser = true, initialSession = { access_token: "supabase-session-a", user } } = {}) {
  let session = initialSession, callback, authOptions, redirect, logout, unsubscribed = false, created = 0, reads = 0;
  const requests = [], stored = new Map();
  let reply = () => new Response("{}"), authError = null;
  const sdk = { auth: {
    getSession: async () => { reads++; return { data: { session }, error: authError }; },
    signInWithOAuth: async options => { redirect = options; return { error: authError }; },
    signOut: async options => { logout = options; session = null; callback?.("SIGNED_OUT", null); return { error: authError }; },
    onAuthStateChange: listener => { callback = listener; return { data: { subscription: { unsubscribe: () => { unsubscribed = true; } } } }; },
  } };
  const window = { location: { href: "https://app.example.invalid/repository?tab=findings#current" }, localStorage: {
    getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key),
  } };
  const context = { URL, Headers, Response, AbortSignal, setTimeout, process: { env },
    fetch: async (path, options) => { requests.push({ path, options }); return reply(path, options); },
    ...(browser ? { window } : {}),
  };
  function load(relative, imports) {
    const compiled = ts.transpileModule(readFileSync(new URL(relative, import.meta.url), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    const loaded = { exports: {} };
    vm.runInNewContext(compiled, { ...context, module: loaded, exports: loaded.exports, require: name => {
      assert.ok(name in imports, `Unexpected import ${name}`);
      return imports[name];
    } });
    return loaded.exports;
  }
  const auth = load("../src/lib/auth.ts", { "@supabase/supabase-js": { createClient: (url, key, options) => {
    created++; assert.equal(url, enabledEnv.NEXT_PUBLIC_SUPABASE_URL); assert.equal(key, enabledEnv.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
    authOptions = options.auth; return sdk;
  } } });
  return { auth, requests, stored, window,
    get options() { return authOptions; }, get created() { return created; }, get reads() { return reads; },
    get redirect() { return redirect; }, get logout() { return logout; }, get unsubscribed() { return unsubscribed; },
    set session(value) { session = value; }, set error(value) { authError = value; }, set reply(value) { reply = value; },
    emit: value => callback?.("SIGNED_IN", value),
    api: () => load("../src/lib/api.ts", { "./auth": auth }),
    verify: () => load("../src/lib/verify.ts", { "./auth": auth }),
  };
}

test("missing either public setting leaves auth disabled and requests unchanged", async () => {
  for (const env of [{}, { NEXT_PUBLIC_SUPABASE_URL: enabledEnv.NEXT_PUBLIC_SUPABASE_URL }, { NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "test-publishable" }]) {
    const h = harness({ env });
    const options = { headers: { "content-type": "application/json" }, cache: "no-store" };
    assert.equal(h.auth.isAuthEnabled(), false);
    await h.auth.signInWithGitHub(); await h.auth.signOut();
    assert.equal(await h.auth.getAccessToken(), null);
    assert.equal(await h.auth.getCurrentUser(), null);
    await h.auth.apiFetch("/api/scans", options);
    assert.equal(h.requests[0].options, options);
    assert.equal(new Headers(h.requests[0].options.headers).has("Authorization"), false);
    assert.equal(h.created, 0);
  }
});

test("server rendering with configured auth never constructs a browser client", async () => {
  const h = harness({ browser: false });
  assert.equal(h.auth.isAuthEnabled(), true);
  assert.equal(await h.auth.getAccessToken(), null);
  assert.equal(h.created, 0);
});

test("internal requests retain signal, cache, body and every existing header", async () => {
  const h = harness(), signal = new AbortController().signal;
  for (const headers of [{ "content-type": "application/json", "x-request-id": "one" }, [["x-request-id", "one"]], new Headers({ "x-request-id": "one" })]) {
    const options = { method: "POST", headers, signal, cache: "no-store", body: "{}", credentials: "same-origin" };
    await h.auth.apiFetch("/api/scans", options);
    const sent = h.requests.at(-1).options;
    assert.equal(sent.headers.get("Authorization"), "Bearer supabase-session-a");
    assert.equal(sent.headers.get("x-request-id"), "one");
    assert.equal(sent.signal, signal); assert.equal(sent.cache, "no-store"); assert.equal(sent.body, "{}");
    assert.equal(sent.credentials, "same-origin");
    assert.equal(new Headers(headers).has("Authorization"), false);
  }
  assert.equal(h.created, 1);
});

test("external and non-API destinations never receive or even read the session", async () => {
  const h = harness();
  for (const path of ["https://external.invalid/api/scans", "//external.invalid/api/scans", "/api-other", "api/scans", "/api/../outside", "/api\\external", "/api/%2e%2e/outside"]) {
    const options = { cache: "no-store" };
    await h.auth.apiFetch(path, options);
    assert.equal(h.requests.at(-1).options, options);
  }
  assert.equal(h.created, 0); assert.equal(h.reads, 0);
});

test("each request uses the current Supabase session, including refresh and logout", async () => {
  const h = harness();
  await h.auth.apiFetch("/api/verify");
  h.session = { access_token: "supabase-session-b", user };
  await h.auth.apiFetch("/api/verify/job");
  h.session = null;
  await h.auth.apiFetch("/api/verify/job");
  assert.equal(h.requests[0].options.headers.get("Authorization"), "Bearer supabase-session-a");
  assert.equal(h.requests[1].options.headers.get("Authorization"), "Bearer supabase-session-b");
  assert.equal(h.requests[2].options, undefined);
});

test("GitHub login uses PKCE and the current page; auth changes and local logout propagate", async () => {
  const h = harness(), seen = [];
  const unsubscribe = h.auth.subscribeAuth(value => seen.push(value));
  assert.equal(h.options.flowType, "pkce"); assert.equal(h.options.detectSessionInUrl, true);
  await h.auth.signInWithGitHub();
  assert.equal(h.redirect.provider, "github");
  assert.equal(h.redirect.options.redirectTo, h.window.location.href);
  h.emit({ user, access_token: "supabase-session-a" });
  assert.equal(seen[0], user); assert.equal(await h.auth.getCurrentUser(), user);
  await h.auth.signOut();
  assert.equal(h.logout.scope, "local"); assert.equal(seen[1], null);
  unsubscribe(); assert.equal(h.unsubscribed, true);
});

test("storage excludes GitHub provider credentials while preserving Supabase refresh and PKCE", async () => {
  const h = harness();
  await h.auth.getAccessToken();
  const storage = h.options.storage;
  storage.setItem("session", JSON.stringify({ access_token: "supabase-session-a", refresh_token: "supabase-refresh", provider_token: "github-provider", provider_refresh_token: "github-refresh", user }));
  const saved = JSON.parse(storage.getItem("session"));
  assert.equal(saved.access_token, "supabase-session-a"); assert.equal(saved.refresh_token, "supabase-refresh");
  assert.equal(saved.user.id, user.id);
  assert.equal("provider_token" in saved, false); assert.equal("provider_refresh_token" in saved, false);
  storage.setItem("pkce-verifier", "plain-pkce-verifier");
  assert.equal(storage.getItem("pkce-verifier"), "plain-pkce-verifier");
  storage.removeItem("session"); assert.equal(storage.getItem("session"), null);
});

test("GitHub ID comes from the actual provider metadata without inventing it from email", () => {
  const h = harness();
  assert.equal(h.auth.getGitHubUsername(user), "octocat");
  assert.equal(h.auth.getGitHubUsername({ user_metadata: { user_name: "legacy" } }), "legacy");
  assert.equal(h.auth.getGitHubUsername({ user_metadata: { full_name: "Person" }, email: "person@example.invalid" }), "");
});

test("scan and verify 401 responses explain how to log in instead of exposing backend codes", async () => {
  const h = harness({ env: {} });
  for (const detail of ["BEARER_REQUIRED", { code: "INVALID_ACCESS_TOKEN", message: "Token expired" }]) {
    h.reply = () => new Response(JSON.stringify({ detail }), { status: 401 });
    await assert.rejects(h.api().startScan("https://github.com/demo/site"), error => error.message === h.auth.LOGIN_REQUIRED_MESSAGE);
    await assert.rejects(h.verify().runVerify(), error => error.message === h.auth.LOGIN_REQUIRED_MESSAGE);
  }
});

test("auth errors do not expose provider messages or credentials", async () => {
  const h = harness(); h.error = { message: "private-provider-detail" };
  for (const action of [h.auth.signInWithGitHub, h.auth.signOut, h.auth.getAccessToken]) {
    await assert.rejects(action(), error => !error.message.includes("private-provider-detail") && /GitHub|로그아웃/.test(error.message));
  }
});
