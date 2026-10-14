import { type NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// Render's free tier sleeps the backend after inactivity and can take up to
// about a minute to wake on the next request. This must stay comfortably
// under this route's own maxDuration below, so a genuinely slow-but-waking
// backend gets a friendly message instead of Vercel abruptly killing the
// function first.
const BACKEND_TIMEOUT_MS = 65_000

// Allows this route up to 70s of execution on Vercel (default limits are
// much shorter on some plans/runtimes) -- must stay above BACKEND_TIMEOUT_MS
// so our own timeout fires first, with a clean message, not a platform 504.
export const maxDuration = 70

export async function POST(req: NextRequest) {
  let body: { names?: string[] }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 })
  }

  if (!body.names || !Array.isArray(body.names) || body.names.length === 0) {
    return NextResponse.json({ error: "A list of drug names is required." }, { status: 400 })
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/score-batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names: body.names }),
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    })

    if (!res.ok) {
      throw new Error(`Backend returned ${res.status}`)
    }

    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    const isTimeoutOrNetworkError =
      (err instanceof Error && err.name === "TimeoutError") ||
      (err instanceof DOMException && err.name === "AbortError") ||
      (err instanceof TypeError) // fetch's own network-failure type (e.g. connection refused)

    console.error("Batch scoring failed:", err instanceof Error ? err.message : err)

    if (isTimeoutOrNetworkError) {
      return NextResponse.json(
        {
          error:
            "The server is waking up. This can take up to a minute on the first request. Please try again.",
        },
        { status: 503 }
      )
    }

    return NextResponse.json(
      { error: "Could not score your inventory right now. Is the backend running?" },
      { status: 502 }
    )
  }
}