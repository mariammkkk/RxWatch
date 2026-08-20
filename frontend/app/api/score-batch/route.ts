import { type NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

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
    })

    if (!res.ok) {
      throw new Error(`Backend returned ${res.status}`)
    }

    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    console.error("Batch scoring failed:", err instanceof Error ? err.message : err)
    return NextResponse.json(
      { error: "Could not score your inventory right now. Is the backend running?" },
      { status: 502 }
    )
  }
}