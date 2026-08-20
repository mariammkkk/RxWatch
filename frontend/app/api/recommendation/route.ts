import { generateText } from "ai"

export const maxDuration = 30

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

interface RecommendationRequest {
  name?: string
}

export async function POST(req: Request) {
  let body: RecommendationRequest
  try {
    body = await req.json()
  } catch {
    return Response.json({ error: "Invalid request body." }, { status: 400 })
  }

  const { name } = body
  if (!name) {
    return Response.json({ error: "Drug name is required." }, { status: 400 })
  }

  // Fetch the REAL computed features from the trained model, rather than
  // trusting whatever the client already had — this is the source of truth.
  let scored: {
    manufacturers?: number
    drugClass?: string
    dosageForm?: string
    cause?: string
    score?: number
    activeShortage?: boolean
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/drug-features?name=${encodeURIComponent(name)}`)
    if (!res.ok) throw new Error(`Backend returned ${res.status}`)
    scored = await res.json()
  } catch (err) {
    console.error("Feature lookup failed:", err instanceof Error ? err.message : err)
    return Response.json({ error: "Could not look up this drug right now. Please try again." }, { status: 502 })
  }

  const facts = [
    `Drug: ${name}`,
    `Risk score: ${typeof scored.score === "number" ? `${scored.score}/100` : "unknown"}`,
    `Predicted cause: ${scored.cause ?? "unclear"}`,
    `Active FDA shortage: ${scored.activeShortage ? "yes, currently listed" : "not currently listed"}`,
    `Manufacturer count: ${typeof scored.manufacturers === "number" ? scored.manufacturers : "unknown"}`,
    `Drug class: ${scored.drugClass ?? "unknown"}`,
    `Dosage form: ${scored.dosageForm ?? "unknown"}`,
  ].join("\n")

  try {
    const { text } = await generateText({
      model: "openai/gpt-4.1-mini",
      instructions:
        "You are a pharmacy supply-chain advisor helping an independent community pharmacy respond to drug-shortage risk. " +
        "You are given a set of computed facts about one drug. Give concise, practical guidance in 2-3 short sentences. " +
        "Base your advice ONLY on the facts provided; do not invent statistics, prices, or shortage dates, or specific " +
        "supplier or company names. Do not give clinical or medical advice — this is inventory/purchasing guidance only. " +
        "If the cause is supply-side, lean toward diversifying suppliers and buying ahead; if demand-side, lean toward " +
        "watching allocation limits and protecting existing patients. Speak plainly to a busy pharmacist. " +
        "Do not repeat the raw numbers back verbatim; interpret what they mean and what to do. Do not use markdown or headings.",
      prompt: `Here are the computed facts for this drug:\n\n${facts}\n\nGive the pharmacy a short, actionable recommendation.`,
    })

    return Response.json({ recommendation: text.trim() })
  } catch (err) {
    console.error("Recommendation generation failed:", err instanceof Error ? err.message : err)
    return Response.json({ error: "Could not generate a recommendation right now. Please try again." }, { status: 500 })
  }
}