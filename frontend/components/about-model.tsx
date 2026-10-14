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
            About the data and methodology
          </h2>
          <p className="mt-1 text-pretty text-sm leading-relaxed text-muted-foreground">
            RxWatch reads three public openFDA datasets: Drug Shortages, the NDC Directory, and Enforcement Reports.
            Shortage status and FDA-reported reasons come straight from FDA records, not from a model.
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
            <div className="mt-4 space-y-4 border-t border-border pt-4">
              <div>
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Database className="size-3.5" aria-hidden="true" />
                  The experimental estimate
                </h3>
                <p className="text-pretty text-sm leading-relaxed text-muted-foreground">
                  An experimental cause estimate is shown only for drugs in an active shortage with no stated FDA
                  reason. The model was revalidated after we found two problems in the original training data:
                  duplicate records (each shortage event was counted many times over) and an incomplete NDC
                  Directory pull, which we fixed by downloading the complete file. After fixing both, the
                  event-level cross-validated AUC is 0.71 on 60 past shortage events (permutation test p = 0.009).
                  The manufacturer-count finding our earlier analysis reported is still not statistically
                  significant at the event level (p = 0.307). Every estimate is labeled experimental because the
                  model is trained on only 60 events. Most of the gain over our earlier analysis came from three
                  additional events, so this result is sensitive to small changes in the data.
                </p>
              </div>
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Limitations
                </h3>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li>• Public data lags real supply conditions by days to weeks.</li>
                  <li>• Regional and wholesaler-specific availability is not tracked.</li>
                  <li>• An approximate match means the matched drug name should be verified before relying on it.</li>
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
