import { type NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// Typeahead: fails soft to an empty list already, so this stays short
// rather than making someone typing wait out a full cold-start wake (see
// score-batch's much longer BACKEND_TIMEOUT_MS for the primary workflow,
// where waiting through a wake-up is the point).
const BACKEND_TIMEOUT_MS = 10_000

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim() ?? ""

  if (q.length < 2) {
    return NextResponse.json({ suggestions: [] })
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/drug-search?q=${encodeURIComponent(q)}`, {
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    })
    if (!res.ok) {
      throw new Error(`Backend returned ${res.status}`)
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Drug search failed:", err instanceof Error ? err.message : err)
    return NextResponse.json({ suggestions: [] }, { status: 200 }) // fail soft: empty results, not a broken UI
  }
}