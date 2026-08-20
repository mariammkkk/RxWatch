import { type NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim() ?? ""

  if (q.length < 2) {
    return NextResponse.json({ suggestions: [] })
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/drug-search?q=${encodeURIComponent(q)}`)
    if (!res.ok) {
      throw new Error(`Backend returned ${res.status}`)
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Drug search failed:", err instanceof Error ? err.message : err)
    return NextResponse.json({ suggestions: [] }, { status: 200 }) // fail soft — empty results, not a broken UI
  }
}