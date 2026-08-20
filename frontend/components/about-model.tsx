"use client"

import { useState } from "react"
import { ChevronDown, Database, Info } from "lucide-react"
import { cn } from "@/lib/utils"

export function AboutModel() {
  const [open, setOpen] = useState(false)

  return (
    <section aria-labelledby="about-heading" className="rounded-xl border border-border bg-card">
      <div className="flex items-start gap-3 p-5">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
          <Info className="size-4.5" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <h2 id="about-heading" className="text-sm font-semibold text-foreground">
            About this model
          </h2>
          <p className="mt-1 text-pretty text-sm leading-relaxed text-muted-foreground">
            RxWatch scores are generated from <strong className="font-medium text-foreground">public FDA data only</strong>{" "}
            (openFDA Drug Shortages, the NDC Directory, and Drugs@FDA). No proprietary wholesaler feeds or paid data are
            required. Scores are a transparent, rules-based heuristic: a screening aid, not a guarantee.
          </p>
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Methodology &amp; limitations
            <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
          </button>

          {open && (
            <div className="mt-4 grid gap-5 border-t border-border pt-4 md:grid-cols-2">
              <div>
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Database className="size-3.5" aria-hidden="true" />
                  How the score is built
                </h3>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li>• Manufacturer concentration (fewer suppliers → higher risk)</li>
                  <li>• Dosage form (sterile injectables are hardest to produce)</li>
                  <li>• Drug-class shortage history</li>
                  <li>• Current openFDA active-shortage listing</li>
                  <li>• Demand-side pressure signals</li>
                </ul>
              </div>
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Limitations</h3>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li>• Public data lags real supply conditions by days to weeks.</li>
                  <li>• Regional and wholesaler-specific availability is not modeled.</li>
                  <li>• Unmatched drugs receive an estimated profile for demonstration.</li>
                  <li>• Not medical or purchasing advice. Verify before acting.</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
