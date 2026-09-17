"use client"

import { Fragment, useMemo, useState } from "react"
import { ChevronDown, Factory, FlaskConical, Pill } from "lucide-react"
import type { ScoredDrug } from "@/lib/rx-data"
import { CauseTag, ShortageBadge, TierBadge, tierBarColor } from "@/components/risk-badges"
import { cn } from "@/lib/utils"

type SortKey = "score" | "name"

export function ResultsTable({ drugs }: { drugs: ScoredDrug[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("score")
  const [asc, setAsc] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const sorted = useMemo(() => {
    const arr = [...drugs]
    arr.sort((a, b) => {
      const cmp = sortKey === "score" ? a.score - b.score : a.name.localeCompare(b.name)
      return asc ? cmp : -cmp
    })
    return arr
  }, [drugs, sortKey, asc])

  function toggleSort(key: SortKey) {
    if (key === sortKey) setAsc((v) => !v)
    else {
      setSortKey(key)
      setAsc(key === "name")
    }
  }

  function toggleRow(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  return (
    <section aria-label="Risk results" className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-secondary/50 text-left">
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                <SortButton active={sortKey === "name"} asc={asc} onClick={() => toggleSort("name")}>
                  Drug Name
                </SortButton>
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                <SortButton active={sortKey === "score"} asc={asc} onClick={() => toggleSort("score")}>
                  Risk Score
                </SortButton>
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Predicted Cause
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Active Shortage
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium text-muted-foreground">
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((d) => {
              const open = expanded.has(d.name)
              return (
                <Fragment key={d.name}>
                  <tr
                    className={cn(
                      "cursor-pointer border-b border-border transition-colors hover:bg-accent/30",
                      open && "bg-accent/40",
                    )}
                    onClick={() => toggleRow(d.name)}
                  >
                    <td className="px-4 py-3">
                      <span className="font-medium text-foreground">{d.name}</span>
                      <span className="block text-xs text-muted-foreground">{d.drugClass}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <TierBadge tier={d.tier} score={d.score} />
                        <div className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-muted sm:block">
                          <div
                            className={cn("h-full rounded-full", tierBarColor(d.tier))}
                            style={{ width: `${d.score}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <CauseTag cause={d.cause} />
                    </td>
                    <td className="px-4 py-3">
                      <ShortageBadge active={d.activeShortage} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        aria-expanded={open}
                        aria-label={`${open ? "Collapse" : "Expand"} details for ${d.name}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleRow(d.name)
                        }}
                        className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
                      </button>
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b border-border bg-secondary/30">
                      <td colSpan={5} className="px-4 py-5">
                        <RowDetail drug={d} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function SortButton({
  children,
  active,
  asc,
  onClick,
}: {
  children: React.ReactNode
  active: boolean
  asc: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active && "text-foreground",
      )}
    >
      {children}
      <ChevronDown className={cn("size-3.5 transition-transform", active && asc && "rotate-180", !active && "opacity-30")} />
    </button>
  )
}

function RowDetail({ drug }: { drug: ScoredDrug }) {
  const maxWeight = Math.max(...drug.factors.map((f) => f.weight), 1)
  const iconFor = (label: string) => {
    if (label.startsWith("Manufacturer")) return Factory
    if (label.startsWith("Dosage")) return Pill
    return FlaskConical
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-6 md:grid-cols-[1.4fr_1fr]">
        <div>
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Why this scored {drug.score}/100
          </h3>
          <ul className="space-y-2.5">
            {drug.factors.map((f) => {
              const Icon = iconFor(f.label)
              return (
                <li key={f.label} className="flex items-center gap-3">
                  <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <span className="w-40 shrink-0 text-sm text-foreground">{f.label}</span>
                  <span className="w-40 shrink-0 truncate text-xs text-muted-foreground">{f.value}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary/80"
                      style={{ width: `${(f.weight / maxWeight) * 100}%` }}
                      role="img"
                      aria-label={`Contributes ${f.weight} points`}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">
                    +{f.weight}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Plain-language read
          </h3>
          <p className="text-pretty text-sm leading-relaxed text-foreground">{drug.explanation}</p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="text-muted-foreground">Manufacturers</dt>
              <dd className="font-mono text-sm font-semibold text-foreground">{drug.manufacturers}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Dosage form</dt>
              <dd className="text-sm font-medium text-foreground">{drug.dosageForm}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  )
}
