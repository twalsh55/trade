import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getSession } from "@/lib/api";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";

export async function POST(request: Request) {
  const payload = (await request.json().catch(() => null)) as { sessionToken?: string } | null;
  const sessionToken = payload?.sessionToken?.trim();
  if (!sessionToken) {
    return NextResponse.json({ error: "Missing session token." }, { status: 400 });
  }

  try {
    const session = await getSession({ sessionToken });
    if (!session.authenticated) {
      return NextResponse.json({ error: "Authentication failed." }, { status: 401 });
    }

    const response = NextResponse.json({ authenticated: true, user: session.user });
    response.cookies.set(BRIVOLY_SESSION_COOKIE, sessionToken, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
    });
    response.cookies.set(LEGACY_TRADE_SESSION_COOKIE, sessionToken, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
    });
    return response;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to bootstrap session.";
    return NextResponse.json({ error: message }, { status: 401 });
  }
}

export async function DELETE() {
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set(BRIVOLY_SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  response.cookies.set(LEGACY_TRADE_SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return response;
}

export async function GET() {
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value;
  if (!sessionToken) {
    return NextResponse.json({ authenticated: false, user: null });
  }

  try {
    const session = await getSession({ sessionToken });
    if (!session.authenticated) {
      return NextResponse.json({ authenticated: false, user: null });
    }
    return NextResponse.json(session);
  } catch {
    return NextResponse.json({ authenticated: false, user: null });
  }
}
