"use client"

import { useState } from "react"
import Link from "next/link"
import { ArrowLeft, RotateCcw } from "lucide-react"
import { RxHeader } from "@/components/rx-header"
import { UploadSection } from "@/components/upload-section"
import { SummaryStats } from "@/components/summary-stats"
import { ResultsTable } from "@/components/results-table"
import { AboutModel } from "@/components/about-model"
import { Button } from "@/components/ui/button"
import type { ScoredDrug } from "@/lib/rx-data"

export default function DashboardPage() {
  const [results, setResults] = useState<ScoredDrug[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function scoreNames(names: string[]) {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch("/api/score-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ names }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error || "Something went wrong scoring your drugs.")
      }
      setResults(data.results)
      scrollToResults()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.")
    } finally {
      setLoading(false)
    }
  }

  function handleInventory(names: string[]) {
    scoreNames(names)
  }

  function handleSingle(name: string) {
    scoreNames([name])
  }

  function scrollToResults() {
    requestAnimationFrame(() => {
      document.getElementById("results")?.scrollIntoView({ behavior: "smooth", block: "start" })
    })
  }

  return (
    <div className="min-h-dvh">
      <RxHeader />

      <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground underline-offset-4 transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to overview
        </Link>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-8">
            <UploadSection onInventory={handleInventory} onSingle={handleSingle} />

            {loading && (
              <div className="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center">
                <p className="text-sm text-muted-foreground">Scoring your drugs against the model...</p>
              </div>
            )}

            {error && !loading && (
              <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-6 py-4 text-sm text-destructive">
                {error}
              </div>
            )}

            {results && !loading && (
              <div id="results" className="scroll-mt-6 space-y-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-foreground">Risk assessment</h2>
                    <p className="text-sm text-muted-foreground">
                      Sorted by risk score, highest first. Click any row to see why it scored that way.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setResults(null)}
                    className="shrink-0 gap-1.5 bg-transparent"
                  >
                    <RotateCcw className="size-3.5" aria-hidden="true" />
                    Clear
                  </Button>
                </div>

                <SummaryStats drugs={results} />
                <ResultsTable drugs={results} />
              </div>
            )}

            {!results && !loading && !error && (
              <div className="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center">
                <p className="text-sm text-muted-foreground">
                  Your risk table will appear here once you upload an inventory or search a drug.
                </p>
              </div>
            )}
          </div>

          <aside className="space-y-5 lg:sticky lg:top-6 lg:self-start">
            <AboutModel />
          </aside>
        </div>
      </main>

      <footer className="border-t border-border py-6">
        <p className="mx-auto max-w-6xl px-5 text-center text-xs text-muted-foreground sm:px-8">
          RxWatch is a demonstration screening tool built on public openFDA data. Always verify supply status with your
          wholesaler before making purchasing decisions.
        </p>
      </footer>
    </div>
  )
}