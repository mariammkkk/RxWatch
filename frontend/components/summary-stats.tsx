import type { ScoredDrug } from "@/lib/rx-data"
import { AlertTriangle, Boxes, ShieldAlert, Siren } from "lucide-react"

function CauseDonut({ supply, demand, unclear }: { supply: number; demand: number; unclear: number }) {
  const total = Math.max(1, supply + demand + unclear)
  const segments = [
    { value: supply, color: "var(--color-chart-1)", label: "Supply-side" },
    { value: demand, color: "oklch(0.6 0.16 300)", label: "Demand-side" },
    { value: unclear, color: "var(--color-muted-foreground)", label: "Unclear" },
  ]
  const r = 34
  const c = 2 * Math.PI * r
  let offset = 0

  return (
    <div className="flex items-center gap-4">
      <svg width="88" height="88" viewBox="0 0 88 88" className="shrink-0 -rotate-90" role="img" aria-label="Risk cause breakdown">
        {segments.map((s, i) => {
          const len = (s.value / total) * c
          const dash = `${len} ${c - len}`
          const el = (
            <circle
              key={i}
              cx="44"
              cy="44"
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth="12"
              strokeDasharray={dash}
              strokeDashoffset={-offset}
            />
          )
          offset += len
          return el
        })}
        <circle cx="44" cy="44" r={r - 10} fill="var(--color-card)" />
      </svg>
      <ul className="space-y-1 text-xs">
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-2 text-muted-foreground">
            <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden="true" />
            <span className="font-medium text-foreground tabular-nums">{s.value}</span>
            {s.label}
          </li>
        ))}
      </ul>
    </div>
  )
}

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

export function SummaryStats({ drugs }: { drugs: ScoredDrug[] }) {
  const total = drugs.length
  const highRisk = drugs.filter((d) => d.tier === "High" || d.tier === "Critical").length
  const active = drugs.filter((d) => d.activeShortage).length
  const supply = drugs.filter((d) => d.cause === "Supply-side").length
  const demand = drugs.filter((d) => d.cause === "Demand-side").length
  const unclear = drugs.filter((d) => d.cause === "Unclear").length

  return (
    <section aria-label="Summary statistics" className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
      <Stat icon={Boxes} label="Drugs scanned" value={total} />
      <Stat icon={ShieldAlert} label="High / critical risk" value={highRisk} tone="warn" />
      <Stat icon={Siren} label="In active shortage" value={active} tone="danger" />
      <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <div className="flex size-9 items-center justify-center rounded-lg bg-secondary">
          <AlertTriangle className="size-4.5 text-primary" aria-hidden="true" />
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-muted-foreground">Risk cause mix</p>
          <CauseDonut supply={supply} demand={demand} unclear={unclear} />
        </div>
      </div>
    </section>
  )
}
