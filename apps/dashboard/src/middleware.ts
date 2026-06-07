import { NextResponse, type NextRequest } from "next/server"

function hasSessionCookie(request: NextRequest) {
  return Boolean(
    request.cookies.get("better-auth.session_token") ??
      request.cookies.get("__Secure-better-auth.session_token") ??
      request.cookies.get("better-auth-session_token") ??
      request.cookies.get("__Secure-better-auth-session_token"),
  )
}

export function middleware(request: NextRequest) {
  if (!hasSessionCookie(request)) {
    const url = new URL("/sign-in", request.url)
    return NextResponse.redirect(url)
  }
  return NextResponse.next()
}

export const config = {
  matcher: ["/keys/:path*", "/projects/:path*", "/settings/:path*"],
}
