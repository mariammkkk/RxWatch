"use client"

import { Fragment, useMemo, useState } from "react"
import { ChevronDown } from "lucide-react"
import type { DrugResult, ShortageStatus } from "@/lib/rx-data"
import { StatusBadge, NotFoundBadge, FewManufacturersBadge, MatchTypeNote } from "@/components/risk-badges"
import { cn } from "@/lib/utils"

type DisplayStatus = ShortageStatus | "not_found"

const STATUS_ORDER: DisplayStatus[] = ["current", "to_be_discontinued", "resolved", "not_listed", "not_found"]

function displayStatus(d: DrugResult): DisplayStatus {
  if (d.matchedGenericName === null && d.shortageStatus === "not_listed") return "not_found"
  return d.shortageStatus
}

function formatDataAsOf(dataAsOf: string): string {
  // dataAsOf may be a bare date ("2026-08-20") or a full ISO timestamp.
  const d = new Date(dataAsOf.length <= 10 ? `${dataAsOf}T00:00:00` : dataAsOf)
  if (Number.isNaN(d.getTime())) return dataAsOf
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
}

export function ResultsTable({ drugs, dataAsOf }: { drugs: DrugResult[]; dataAsOf: string }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const sorted = useMemo(() => {
    const arr = [...drugs]
    arr.sort((a, b) => {
      const statusCmp = STATUS_ORDER.indexOf(displayStatus(a)) - STATUS_ORDER.indexOf(displayStatus(b))
      if (statusCmp !== 0) return statusCmp
      const am = a.facts.manufacturerCount
      const bm = b.facts.manufacturerCount
      if (am === null && bm === null) return 0
      if (am === null) return 1 // unknown last
      if (bm === null) return -1
      return am - bm
    })
    return arr
  }, [drugs])

  function toggleRow(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  return (
    <section aria-label="Results" className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-secondary/50 text-left">
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Drug
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Status
              </th>
              <th
                scope="col"
                className="px-4 py-3 font-medium text-muted-foreground"
                title="Distinct companies listing this drug in the FDA NDC Directory, including companies that repackage or relabel."
              >
                Labelers
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Recalls
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Class
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Dosage form
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium text-muted-foreground">
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((d) => {
              const open = expanded.has(d.name)
              const status = displayStatus(d)
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
                      {d.fewManufacturersFlag && (
                        <span className="ml-2 inline-block align-middle">
                          <FewManufacturersBadge />
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {status === "not_found" ? <NotFoundBadge /> : <StatusBadge status={d.shortageStatus} />}
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      {d.facts.manufacturerCount ?? "Unknown"}
                    </td>
                    <td className="px-4 py-3 text-foreground">{d.facts.recallCount}</td>
                    <td className="px-4 py-3 text-foreground">{d.facts.therapeuticClass ?? "Unknown"}</td>
                    <td className="px-4 py-3 text-foreground">{d.facts.dosageForm ?? "Unknown"}</td>
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
                      <td colSpan={7} className="px-4 py-5">
                        <RowDetail drug={d} dataAsOf={dataAsOf} />
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

function RowDetail({ drug, dataAsOf }: { drug: DrugResult; dataAsOf: string }) {
  return (
    <div className="space-y-4">
      <MatchTypeNote matchedGenericName={drug.matchedGenericName} matchType={drug.ndcMatchType} />

      {drug.fdaStatedReasons.length > 0 && (
        <div className="space-y-1">
          {drug.fdaStatedReasons.map((reason) => (
            <p key={reason} className="text-sm text-foreground">
              FDA-reported reason: {reason}
            </p>
          ))}
        </div>
      )}

      {drug.matchedShortageEntries.length > 1 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Listed presentations
          </h3>
          <ul className="space-y-1.5">
            {drug.matchedShortageEntries.map((entry) => (
              <li key={entry.name} className="flex items-center gap-2 text-sm text-foreground">
                <StatusBadge status={entry.status} />
                <span className="text-muted-foreground">{entry.name}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {drug.shortageStatus === "not_listed" && (
        <p className="text-xs text-muted-foreground">
          Not on the FDA shortage list as of {formatDataAsOf(dataAsOf)}. This does not mean a shortage can't occur.
        </p>
      )}

      {drug.causeEstimate.shown && drug.causeEstimate.supplyProbability !== null && (
        <ExperimentalEstimate probability={drug.causeEstimate.supplyProbability} />
      )}
    </div>
  )
}

function ExperimentalEstimate({ probability }: { probability: number }) {
  const supplySide = probability >= 0.5
  const pct = Math.round((supplySide ? probability : 1 - probability) * 100)

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Experimental estimate (small sample)
      </p>
      <p className="mt-2 text-sm font-medium text-foreground">
        {supplySide ? `Leans supply-side (${pct}%)` : `Leans demand-side (${pct}%)`}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        Based on a model trained on 60 past FDA shortages. It performs better than chance, but the sample is small,
        so treat this as a rough signal only.
      </p>
    </div>
  )
}
