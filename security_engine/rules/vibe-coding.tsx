'use client';
// Semgrep 규칙 테스트용 파일 (브라우저 컴포넌트 예시)
import { createClient } from "@supabase/supabase-js";

// ruleid: supabase-service-role-in-client
const admin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
// ok: supabase-service-role-in-client
const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export function Unsafe({ html }: { html: string }) {
  // ruleid: react-dangerously-set-inner-html
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

export function Safe({ html }: { html: string }) {
  // ok: react-dangerously-set-inner-html
  return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }} />;
}

// ---- Next.js API 라우트 (app/api/.../route.ts 예시)
// ruleid: nextjs-api-mutation-without-auth
export async function POST(req: Request) {
  const body = await req.json();
  const { data } = await supabase.from("posts").insert(body);
  return Response.json(data);
}

// ok: nextjs-api-mutation-without-auth
export async function DELETE(req: Request) {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return new Response("unauthorized", { status: 401 });
  await supabase.from("posts").delete().eq("owner", user.id);
  return new Response(null, { status: 204 });
}

// ok: nextjs-api-mutation-without-auth
export async function GET() {
  return Response.json(await prisma.post.findMany());
}

// ---- Stripe 웹훅
// 이벤트 이름 목록(상수)은 처리 코드가 아니므로 잡으면 안 됨 (vercel/nextjs-subscription-payments 실검사에서 발견한 오탐)
// ok: stripe-webhook-without-signature
const relevantEvents = new Set(["checkout.session.completed", "customer.subscription.updated"]);
export async function handleUnsafe(req: Request) {
  const event = await req.json();
  switch (event.type) {
    // ruleid: stripe-webhook-without-signature
    case "checkout.session.completed":
      await markPaid(event.data.object.id);
      break;
  }
}

export async function handleSafe(req: Request) {
  const sig = req.headers.get("stripe-signature");
  const event = stripe.webhooks.constructEvent(await req.text(), sig, process.env.STRIPE_WEBHOOK_SECRET);
  switch (event.type) {
    // ok: stripe-webhook-without-signature
    case "checkout.session.completed":
      await markPaid(event.data.object.id);
      break;
  }
}

export async function handleSafeTry(req: Request) {
  let event;
  try {
    event = stripe.webhooks.constructEvent(await req.text(), req.headers.get("stripe-signature"), whsec);
  } catch (err) {
    return new Response("bad signature", { status: 400 });
  }
  // ok: stripe-webhook-without-signature
  if (event.type === "payment_intent.succeeded") {
    await markPaid(event.data.object.id);
  }
}

export async function handleUnsafeIf(req: Request) {
  const event = JSON.parse(await req.text());
  // ruleid: stripe-webhook-without-signature
  if (event.type === "invoice.paid") {
    await markPaid(event.data.object.id);
  }
}
