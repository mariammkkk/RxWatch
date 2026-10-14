import type { ShortageStatus } from "@/lib/rx-data"
import { StatusBadge } from "@/components/risk-badges"

type PreviewRow = {
  drug: string
  form: string
  status: ShortageStatus
  manufacturers: number
}

// Verified against the live backend (/api/score-batch) before hardcoding --
// these are real statuses for real drugs from frontend/public/sample-inventory.csv,
// not illustrative placeholders.
const rows: PreviewRow[] = [
  { drug: "Albuterol 90mcg HFA", form: "Inhalation aerosol", status: "current", manufacturers: 53 },
  { drug: "Sodium Chloride 0.9% 1000mL", form: "Injectable", status: "to_be_discontinued", manufacturers: 95 },
  { drug: "Hydrocortisone sodium succinate 100mg inj", form: "Injectable", status: "resolved", manufacturers: 7 },
  { drug: "Lisinopril 10 mg tablet", form: "Oral", status: "not_listed", manufacturers: 37 },
]

const onShortageList = rows.filter((r) => r.status !== "not_listed").length

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
              <p className="text-xs font-semibold text-foreground">Inventory status</p>
              <p className="text-[11px] text-muted-foreground">4 drugs checked</p>
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
          <span className="w-[150px] text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Status
          </span>
          <span className="hidden w-[90px] text-right text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground sm:block">
            Mfrs
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
              <div className="w-[150px] shrink-0">
                <StatusBadge status={row.status} />
              </div>
              <div className="hidden w-[90px] shrink-0 text-right text-sm text-muted-foreground sm:block">
                {row.manufacturers}
              </div>
            </li>
          ))}
        </ul>

        {/* Footer strip */}
        <div className="flex items-center justify-between border-t border-border bg-muted/40 px-4 py-2.5">
          <span className="text-[11px] text-muted-foreground">openFDA Drug Shortages</span>
          <span className="font-mono text-[11px] text-primary">{onShortageList} drugs on the FDA shortage list</span>
        </div>
      </div>
    </div>
  )
}
