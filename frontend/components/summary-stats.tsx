import type { DrugResult } from "@/lib/rx-data"
import { AlertTriangle, Ban, Boxes, CheckCircle2, HelpCircle, Siren } from "lucide-react"

function Stat({
  icon: Icon,
  label,
  value,
  tone = "default",
}: {
  icon: typeof Boxes
  label: string
  value: number
  tone?: "default" | "danger" | "warn"
}) {
  const toneClass =
    tone === "danger" ? "text-red-600" : tone === "warn" ? "text-orange-600" : "text-primary"
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex size-9 items-center justify-center rounded-lg bg-secondary">
        <Icon className={`size-4.5 ${toneClass}`} aria-hidden="true" />
      </div>
      <div>
        <p className="font-mono text-2xl font-semibold leading-none tabular-nums text-foreground">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

export function SummaryStats({ drugs }: { drugs: DrugResult[] }) {
  const current = drugs.filter((d) => d.shortageStatus === "current").length
  const toBeDiscontinued = drugs.filter((d) => d.shortageStatus === "to_be_discontinued").length
  const resolved = drugs.filter((d) => d.shortageStatus === "resolved").length
  const notListed = drugs.filter((d) => d.shortageStatus === "not_listed" && d.matchedGenericName !== null).length
  const notFound = drugs.filter((d) => d.matchedGenericName === null).length
  const fewManufacturers = drugs.filter((d) => d.fewManufacturersFlag).length

  return (
    <section aria-label="Summary statistics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <Stat icon={Siren} label="Current shortage" value={current} tone="danger" />
      <Stat icon={AlertTriangle} label="To be discontinued" value={toBeDiscontinued} tone="warn" />
      <Stat icon={CheckCircle2} label="Resolved" value={resolved} />
      <Stat icon={Boxes} label="Not on shortage list" value={notListed} />
      <Stat icon={HelpCircle} label="Not found" value={notFound} />
      <Stat icon={Ban} label="Few manufacturers" value={fewManufacturers} tone="warn" />
    </section>
  )
}
