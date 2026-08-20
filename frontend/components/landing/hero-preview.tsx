import type { Cause, RiskTier } from "@/lib/rx-data"
import { TierBadge, CauseTag } from "@/components/risk-badges"

type PreviewRow = {
  drug: string
  form: string
  tier: RiskTier
  score: number
  cause: Cause
}

const rows: PreviewRow[] = [
  { drug: "Cisplatin", form: "50 mg/50 mL injection", tier: "High", score: 78, cause: "Demand-side" },
  { drug: "Semaglutide", form: "1 mg/0.5 mL pen", tier: "High", score: 81, cause: "Demand-side" },
  { drug: "Hydroxyzine", form: "25 mg tablet", tier: "Medium", score: 54, cause: "Supply-side" },
  { drug: "Lisinopril", form: "10 mg tablet", tier: "Low", score: 12, cause: "Supply-side" },
]

export function HeroPreview() {
  return (
    <div className="relative">
      {/* Faint offset panel to give the stack a sense of depth */}
      <div
        aria-hidden="true"
        className="absolute inset-0 translate-y-3 rounded-xl border border-border bg-card/60 sm:translate-x-3 sm:translate-y-4"
      />

      {/* The card itself */}
      <div className="relative overflow-hidden rounded-xl border border-border bg-card shadow-2xl shadow-primary/10 ring-1 ring-black/[0.02]">
        {/* Window chrome / title strip */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex size-6 items-center justify-center rounded-md bg-primary font-serif text-[11px] font-semibold text-primary-foreground">
              Rx
            </span>
            <div className="leading-tight">
              <p className="text-xs font-semibold text-foreground">Inventory risk</p>
              <p className="text-[11px] text-muted-foreground">214 drugs scored · updated today</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground ring-1 ring-inset ring-border">
            <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
            openFDA
          </span>
        </div>

        {/* Column labels */}
        <div className="flex items-center gap-3 border-b border-border bg-muted/40 px-4 py-2">
          <span className="min-w-0 flex-1 text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Drug
          </span>
          <span className="w-[108px] text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Risk
          </span>
          <span className="hidden w-[104px] text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground sm:block">
            Cause
          </span>
        </div>

        {/* Rows */}
        <ul className="divide-y divide-border">
          {rows.map((row) => (
            <li key={row.drug} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{row.drug}</p>
                <p className="truncate text-xs text-muted-foreground">{row.form}</p>
              </div>
              <div className="w-[108px] shrink-0">
                <TierBadge tier={row.tier} score={row.score} />
              </div>
              <div className="hidden w-[104px] shrink-0 sm:block">
                <CauseTag cause={row.cause} />
              </div>
            </li>
          ))}
        </ul>

        {/* Footer strip implying scale */}
        <div className="flex items-center justify-between border-t border-border bg-muted/40 px-4 py-2.5">
          <span className="text-[11px] text-muted-foreground">+ 210 more in this file</span>
          <span className="font-mono text-[11px] text-primary">3 need attention</span>
        </div>
      </div>
    </div>
  )
}
