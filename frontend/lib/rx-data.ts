// RxWatch: types for the real /api/score-batch and /api/drug-search backend
// responses, plus inventory-file parsing. All scoring/matching logic lives
// in the Python backend (backend/main.py) -- nothing here is mock data.

export type ShortageStatus = "current" | "to_be_discontinued" | "resolved" | "not_listed"
export type MatchType = "exact" | "approximate" | null

export interface MatchedShortageEntry {
  name: string
  status: ShortageStatus
}

export interface DrugFacts {
  manufacturerCount: number | null
  recallCount: number
  therapeuticClass: string | null
  dosageForm: string | null
}

export interface CauseEstimate {
  shown: boolean
  supplyProbability: number | null
}

export interface DrugResult {
  name: string
  matchedGenericName: string | null
  ndcMatchType: MatchType
  shortageMatchType: MatchType
  shortageStatus: ShortageStatus
  fdaStatedReasons: string[]
  matchedShortageEntries: MatchedShortageEntry[]
  facts: DrugFacts
  fewManufacturersFlag: boolean
  causeEstimate: CauseEstimate
}

export interface ScoreBatchResponse {
  dataAsOf: string
  results: DrugResult[]
}

// ---------------------------------------------------------------------------
// Inventory CSV parsing
// ---------------------------------------------------------------------------

function normalize(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, " ")
}

/** Parse a CSV/newline list of drug names. Uses the first column, skips headers. */
export function parseInventoryCsv(text: string): string[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  const names: string[] = []
  for (const line of lines) {
    const first = line.split(",")[0].trim().replace(/^"|"$/g, "")
    if (!first) continue
    if (/^(drug|drug name|name|medication|ndc|product)$/i.test(first)) continue // header
    names.push(first)
  }
  // de-dupe (case-insensitive) preserving order
  const seen = new Set<string>()
  return names.filter((n) => {
    const k = normalize(n)
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

// ---------------------------------------------------------------------------
// Typeahead search (backed by the real /api/drug-search endpoint)
// ---------------------------------------------------------------------------

export interface DrugSuggestion {
  /** The display name to fill into the input when selected */
  name: string
  /** Generic equivalent when `name` is a brand, otherwise null */
  generic_name: string | null
  is_brand: boolean
}
