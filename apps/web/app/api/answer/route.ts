// Proxy serveur vers l'API : le jeton d'accès reste côté serveur et n'est
// jamais exposé au navigateur.
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const MAX_QUESTION = 4000;

export async function POST(request: Request): Promise<Response> {
  const apiUrl = process.env.AVX_API_URL;
  const apiToken = process.env.AVX_API_TOKEN;
  if (!apiUrl || !apiToken) {
    return NextResponse.json({ detail: "service non configuré" }, { status: 503 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "requête invalide" }, { status: 400 });
  }
  const { question, as_of } = (body ?? {}) as { question?: unknown; as_of?: unknown };
  if (typeof question !== "string" || question.trim().length < 3 || question.length > MAX_QUESTION) {
    return NextResponse.json({ detail: "question invalide" }, { status: 400 });
  }
  if (as_of !== undefined && as_of !== "" && (typeof as_of !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(as_of))) {
    return NextResponse.json({ detail: "date invalide" }, { status: 400 });
  }
  const upstream = await fetch(new URL("/v1/answer", apiUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiToken}` },
    body: JSON.stringify({ question, as_of: as_of || undefined }),
    cache: "no-store",
  });
  const payload: unknown = await upstream.json().catch(() => ({ detail: "réponse illisible" }));
  return NextResponse.json(payload, { status: upstream.status });
}
