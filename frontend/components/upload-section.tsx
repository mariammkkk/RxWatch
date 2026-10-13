"use client"

import type React from "react"
import { useRef, useState } from "react"
import { Download, FileSpreadsheet, UploadCloud } from "lucide-react"
import { parseInventoryCsv } from "@/lib/rx-data"
import { DrugSearchInput } from "@/components/drug-search-input"
import { cn } from "@/lib/utils"

interface UploadSectionProps {
  onInventory: (names: string[]) => void
  onSingle: (name: string) => void
}

export function UploadSection({ onInventory, onSingle }: UploadSectionProps) {
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleFiles(files: FileList | null) {
    setError(null)
    const file = files?.[0]
    if (!file) return
    if (!/\.(csv|txt)$/i.test(file.name)) {
      setError("Please upload a .csv or .txt file with one drug name per row.")
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const names = parseInventoryCsv(String(reader.result ?? ""))
      if (names.length === 0) {
        setError("We couldn't find any drug names in that file.")
        return
      }
      onInventory(names)
    }
    reader.readAsText(file)
  }

  return (
    <section aria-labelledby="upload-heading" className="space-y-4">
      <div>
        <h2 id="upload-heading" className="text-lg font-semibold text-foreground">
          Check your inventory
        </h2>
        <p className="text-sm text-muted-foreground">
          Upload a CSV of the drugs you stock to check FDA shortage status for each one.
        </p>
      </div>

      <div
        role="button"
        tabIndex={0}
        aria-label="Upload your inventory list. Drag and drop a CSV file or click to browse."
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
        className={cn(
          "group flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border bg-card px-6 py-12 text-center transition-colors",
          "hover:border-primary/50 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          dragging && "border-primary bg-accent/60",
        )}
      >
        <div className="flex size-14 items-center justify-center rounded-full bg-secondary text-primary transition-transform group-hover:scale-105">
          <UploadCloud className="size-7" aria-hidden="true" />
        </div>
        <div>
          <p className="text-base font-semibold text-foreground">Upload your inventory list</p>
          <p className="mt-1 text-sm text-muted-foreground">Drag &amp; drop a CSV here, or click to browse</p>
        </div>
        <a
          href="/sample-inventory.csv"
          download="rxwatch-sample-inventory.csv"
          onClick={(e) => e.stopPropagation()}
          className="mt-1 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Download className="size-3.5" aria-hidden="true" />
          Download sample CSV for format reference
        </a>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.txt"
          className="sr-only"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {error && (
        <p role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <FileSpreadsheet className="size-4" aria-hidden="true" />
          {error}
        </p>
      )}

      <div className="flex items-center gap-3">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">or search a single drug</span>
        <div className="h-px flex-1 bg-border" />
      </div>

      <DrugSearchInput onSelect={onSingle} />
    </section>
  )
}
