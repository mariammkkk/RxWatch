// RxWatch scoring model
// A transparent, rules-based shortage-risk heuristic modeled on signals that are
// publicly derivable from openFDA (Drug Shortages, NDC Directory, Drugs@FDA).
// This is a demonstration model. See the "About this model" section for limits.

export type DosageForm = "Oral" | "Injectable" | "Topical" | "Inhalation" | "Ophthalmic"
export type RiskTier = "Low" | "Medium" | "High" | "Critical"
export type Cause = "Supply-side" | "Demand-side" | "Unclear"

export interface DrugProfile {
  name: string
  /** Number of FDA-registered manufacturers currently marketing the product */
  manufacturers: number
  drugClass: string
  dosageForm: DosageForm
  /** Whether the class is historically prone to supply-side shortages */
  classProneToShortage: boolean
  /** Currently listed on the FDA drug shortage database */
  activeShortage: boolean
  /** Recent demand spike signal (e.g. off-label surge, seasonal, guideline change) */
  demandSpike: boolean
}

export interface ScoredDrug extends DrugProfile {
  score: number
  tier: RiskTier
  cause: Cause
  explanation: string
  factors: { label: string; value: string; weight: number }[]
}

// ---------------------------------------------------------------------------
// Reference dataset (representative sample of commonly stocked drugs)
// ---------------------------------------------------------------------------

const DATASET: DrugProfile[] = [
  { name: "Amoxicillin", manufacturers: 14, drugClass: "Antibiotic (penicillin)", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: true },
  { name: "Amoxicillin-Clavulanate", manufacturers: 6, drugClass: "Antibiotic (penicillin)", dosageForm: "Oral", classProneToShortage: false, activeShortage: true, demandSpike: true },
  { name: "Cisplatin", manufacturers: 3, drugClass: "Chemotherapy (platinum)", dosageForm: "Injectable", classProneToShortage: true, activeShortage: true, demandSpike: false },
  { name: "Carboplatin", manufacturers: 4, drugClass: "Chemotherapy (platinum)", dosageForm: "Injectable", classProneToShortage: true, activeShortage: true, demandSpike: false },
  { name: "Methotrexate", manufacturers: 5, drugClass: "Antimetabolite", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
  { name: "Lisinopril", manufacturers: 22, drugClass: "ACE inhibitor", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Metformin", manufacturers: 19, drugClass: "Biguanide", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Atorvastatin", manufacturers: 17, drugClass: "Statin", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Albuterol", manufacturers: 4, drugClass: "Beta-2 agonist", dosageForm: "Inhalation", classProneToShortage: true, activeShortage: true, demandSpike: true },
  { name: "Epinephrine", manufacturers: 3, drugClass: "Adrenergic agonist", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
  { name: "Norepinephrine", manufacturers: 2, drugClass: "Vasopressor", dosageForm: "Injectable", classProneToShortage: true, activeShortage: true, demandSpike: false },
  { name: "Heparin", manufacturers: 5, drugClass: "Anticoagulant", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
  { name: "Lidocaine", manufacturers: 6, drugClass: "Local anesthetic", dosageForm: "Injectable", classProneToShortage: true, activeShortage: true, demandSpike: false },
  { name: "Dextrose 50%", manufacturers: 2, drugClass: "IV solution", dosageForm: "Injectable", classProneToShortage: true, activeShortage: true, demandSpike: false },
  { name: "Sodium Chloride 0.9%", manufacturers: 3, drugClass: "IV solution", dosageForm: "Injectable", classProneToShortage: true, activeShortage: true, demandSpike: true },
  { name: "Ozempic (semaglutide)", manufacturers: 1, drugClass: "GLP-1 agonist", dosageForm: "Injectable", classProneToShortage: false, activeShortage: true, demandSpike: true },
  { name: "Wegovy (semaglutide)", manufacturers: 1, drugClass: "GLP-1 agonist", dosageForm: "Injectable", classProneToShortage: false, activeShortage: true, demandSpike: true },
  { name: "Adderall (amphetamine)", manufacturers: 8, drugClass: "CNS stimulant (C-II)", dosageForm: "Oral", classProneToShortage: true, activeShortage: true, demandSpike: true },
  { name: "Lisdexamfetamine", manufacturers: 3, drugClass: "CNS stimulant (C-II)", dosageForm: "Oral", classProneToShortage: true, activeShortage: true, demandSpike: true },
  { name: "Amoxicillin Suspension", manufacturers: 5, drugClass: "Antibiotic (penicillin)", dosageForm: "Oral", classProneToShortage: false, activeShortage: true, demandSpike: true },
  { name: "Hydrochlorothiazide", manufacturers: 15, drugClass: "Thiazide diuretic", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Omeprazole", manufacturers: 20, drugClass: "Proton pump inhibitor", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Levothyroxine", manufacturers: 9, drugClass: "Thyroid hormone", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Gabapentin", manufacturers: 16, drugClass: "Anticonvulsant", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Prednisone", manufacturers: 11, drugClass: "Corticosteroid", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Fentanyl", manufacturers: 4, drugClass: "Opioid analgesic (C-II)", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
  { name: "Morphine", manufacturers: 5, drugClass: "Opioid analgesic (C-II)", dosageForm: "Injectable", classProneToShortage: true, activeShortage: true, demandSpike: false },
  { name: "Ketamine", manufacturers: 3, drugClass: "Anesthetic (C-III)", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: true },
  { name: "Insulin Glargine", manufacturers: 3, drugClass: "Long-acting insulin", dosageForm: "Injectable", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Vancomycin", manufacturers: 7, drugClass: "Glycopeptide antibiotic", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
  { name: "Ceftriaxone", manufacturers: 6, drugClass: "Cephalosporin antibiotic", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
  { name: "Furosemide", manufacturers: 8, drugClass: "Loop diuretic", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
  { name: "Sertraline", manufacturers: 14, drugClass: "SSRI", dosageForm: "Oral", classProneToShortage: false, activeShortage: false, demandSpike: false },
  { name: "Amiodarone", manufacturers: 6, drugClass: "Antiarrhythmic", dosageForm: "Injectable", classProneToShortage: true, activeShortage: false, demandSpike: false },
]

// ---------------------------------------------------------------------------
// Scoring model
// ---------------------------------------------------------------------------

export function scoreDrug(d: DrugProfile): ScoredDrug {
  const factors: ScoredDrug["factors"] = []
  let score = 0

  // Manufacturer concentration: the single strongest supply-side signal.
  let mfrWeight = 0
  if (d.manufacturers <= 1) mfrWeight = 40
  else if (d.manufacturers === 2) mfrWeight = 34
  else if (d.manufacturers === 3) mfrWeight = 28
  else if (d.manufacturers <= 5) mfrWeight = 20
  else if (d.manufacturers <= 8) mfrWeight = 12
  else if (d.manufacturers <= 14) mfrWeight = 6
  else mfrWeight = 2
  score += mfrWeight
  factors.push({
    label: "Manufacturer count",
    value: `${d.manufacturers} active`,
    weight: mfrWeight,
  })

  // Dosage form: sterile injectables carry far higher manufacturing complexity.
  const formWeight =
    d.dosageForm === "Injectable" ? 22 : d.dosageForm === "Inhalation" || d.dosageForm === "Ophthalmic" ? 14 : 4
  score += formWeight
  factors.push({ label: "Dosage form", value: d.dosageForm, weight: formWeight })

  // Drug class history.
  const classWeight = d.classProneToShortage ? 18 : 3
  score += classWeight
  factors.push({
    label: "Drug class",
    value: d.classProneToShortage ? `${d.drugClass} (shortage-prone)` : d.drugClass,
    weight: classWeight,
  })

  // Active shortage right now.
  const shortageWeight = d.activeShortage ? 15 : 0
  score += shortageWeight
  if (d.activeShortage) {
    factors.push({ label: "Active FDA shortage", value: "Listed now", weight: shortageWeight })
  }

  // Demand-side pressure.
  const demandWeight = d.demandSpike ? 10 : 0
  score += demandWeight
  if (d.demandSpike) {
    factors.push({ label: "Demand pressure", value: "Elevated / surging", weight: demandWeight })
  }

  score = Math.max(0, Math.min(100, Math.round(score)))

  const tier: RiskTier = score >= 75 ? "Critical" : score >= 55 ? "High" : score >= 30 ? "Medium" : "Low"

  // Determine dominant cause.
  const supplySignal = mfrWeight + formWeight + classWeight
  const demandSignal = demandWeight * 2.2 + (d.demandSpike ? 8 : 0)
  let cause: Cause
  if (d.demandSpike && demandSignal >= supplySignal * 0.75 && d.manufacturers >= 5) cause = "Demand-side"
  else if (supplySignal >= 40) cause = "Supply-side"
  else if (d.demandSpike) cause = "Demand-side"
  else cause = "Unclear"

  const explanation = buildExplanation(d, cause, tier)

  return { ...d, score, tier, cause, explanation, factors: factors.sort((a, b) => b.weight - a.weight) }
}

function buildExplanation(d: DrugProfile, cause: Cause, tier: RiskTier): string {
  const parts: string[] = []
  if (d.manufacturers <= 3) parts.push(`only ${d.manufacturers} manufacturer${d.manufacturers === 1 ? "" : "s"} supply it`)
  else if (d.manufacturers <= 8) parts.push(`a modest ${d.manufacturers} manufacturers supply it`)
  else parts.push(`${d.manufacturers} manufacturers keep supply diversified`)

  if (d.dosageForm === "Injectable") parts.push("it is a sterile injectable (complex to produce)")
  if (d.classProneToShortage) parts.push("its class has a history of supply-side shortages")
  if (d.demandSpike) parts.push("demand is currently elevated")

  const lead =
    tier === "Critical" || tier === "High"
      ? "High shortage risk"
      : tier === "Medium"
        ? "Moderate shortage risk"
        : "Low shortage risk"

  const causeText =
    cause === "Supply-side"
      ? "Risk is driven primarily by supply-side fragility."
      : cause === "Demand-side"
        ? "Risk is driven primarily by demand-side pressure."
        : "The driving factor is unclear from public signals alone."

  return `${lead}: ${parts.join(", ")}. ${causeText}`
}

// ---------------------------------------------------------------------------
// Lookups & CSV parsing
// ---------------------------------------------------------------------------

function normalize(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, " ")
}

// Deterministic pseudo-random from a string so unknown drugs still get a
// stable, plausible profile (demo behaviour).
function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) / 4294967295
}

const CLASSES = ["Antibiotic", "Analgesic", "Antihypertensive", "Antidepressant", "Antiviral", "Corticosteroid"]

export function lookupDrug(rawName: string): DrugProfile | null {
  const name = normalize(rawName)
  if (!name) return null
  const exact = DATASET.find((d) => normalize(d.name) === name)
  if (exact) return exact
  const partial = DATASET.find((d) => normalize(d.name).includes(name) || name.includes(normalize(d.name)))
  if (partial) return partial
  return null
}

export function profileFor(rawName: string): DrugProfile {
  const known = lookupDrug(rawName)
  if (known) return known
  // Synthesize a deterministic profile for an unknown drug.
  const r = hash(normalize(rawName))
  const r2 = hash(normalize(rawName) + "x")
  const r3 = hash(normalize(rawName) + "yz")
  const manufacturers = Math.max(1, Math.round(r * 20) + 1)
  const forms: DosageForm[] = ["Oral", "Oral", "Oral", "Injectable", "Topical", "Inhalation"]
  const dosageForm = forms[Math.floor(r2 * forms.length)]
  return {
    name: titleCase(rawName),
    manufacturers,
    drugClass: CLASSES[Math.floor(r3 * CLASSES.length)],
    dosageForm,
    classProneToShortage: dosageForm === "Injectable" && r3 > 0.5,
    activeShortage: r > 0.82,
    demandSpike: r2 > 0.8,
  }
}

function titleCase(s: string): string {
  return s
    .trim()
    .split(/\s+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ")
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

export function scoreInventory(names: string[]): ScoredDrug[] {
  return names.map((n) => scoreDrug(profileFor(n)))
}

export const SAMPLE_DRUG_NAMES = DATASET.map((d) => d.name)

export const SAMPLE_CSV = ["Drug Name", ...SAMPLE_DRUG_NAMES.slice(0, 16)].join("\n") + "\n"

// ---------------------------------------------------------------------------
// Typeahead search
// ---------------------------------------------------------------------------

export interface DrugSuggestion {
  /** The display name to fill into the input when selected */
  name: string
  /** Generic equivalent when `name` is a brand, otherwise null */
  generic_name: string | null
  is_brand: boolean
}

// Build a search index from the dataset. Names shaped "Brand (generic)" are
// split into a brand name plus its generic equivalent.
const SEARCH_INDEX: DrugSuggestion[] = DATASET.map((d) => {
  const match = d.name.match(/^(.+?)\s*\(([^)]+)\)\s*$/)
  if (match) {
    return { name: match[1].trim(), generic_name: match[2].trim(), is_brand: true }
  }
  return { name: d.name, generic_name: null, is_brand: false }
})

export function searchDrugs(query: string, limit = 8): DrugSuggestion[] {
  const q = normalize(query)
  if (q.length < 2) return []

  const scored = SEARCH_INDEX.map((s) => {
    const name = normalize(s.name)
    const generic = s.generic_name ? normalize(s.generic_name) : ""
    let rank = -1
    if (name.startsWith(q)) rank = 0
    else if (generic && generic.startsWith(q)) rank = 1
    else if (name.includes(q)) rank = 2
    else if (generic && generic.includes(q)) rank = 3
    return { s, rank }
  }).filter((x) => x.rank >= 0)

  scored.sort((a, b) => a.rank - b.rank || a.s.name.localeCompare(b.s.name))
  return scored.slice(0, limit).map((x) => x.s)
}
