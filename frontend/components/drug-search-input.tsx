"use client"

import type React from "react"
import { useEffect, useId, useRef, useState } from "react"
import { Loader2, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { DrugSuggestion } from "@/lib/rx-data"

interface DrugSearchInputProps {
  onSelect: (name: string) => void
}

export function DrugSearchInput({ onSelect }: DrugSearchInputProps) {
  const [value, setValue] = useState("")
  const [suggestions, setSuggestions] = useState<DrugSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [queried, setQueried] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  // Guards against out-of-order responses and stale fetches after selection.
  const requestSeq = useRef(0)
  const skipNextFetch = useRef(false)

  // Debounced fetch as the user types (2+ chars, ~250ms).
  useEffect(() => {
    const q = value.trim()

    if (skipNextFetch.current) {
      skipNextFetch.current = false
      return
    }

    if (q.length < 2) {
      setSuggestions([])
      setLoading(false)
      setOpen(false)
      setQueried(false)
      return
    }

    setLoading(true)
    const seq = ++requestSeq.current
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/drug-search?q=${encodeURIComponent(q)}`)
        const data = (await res.json()) as { suggestions: DrugSuggestion[] }
        if (seq !== requestSeq.current) return // a newer request superseded this one
        setSuggestions(data.suggestions ?? [])
        setQueried(true)
        setOpen(true)
        setActiveIndex(-1)
      } catch {
        if (seq !== requestSeq.current) return
        setSuggestions([])
        setQueried(true)
        setOpen(true)
      } finally {
        if (seq === requestSeq.current) setLoading(false)
      }
    }, 250)

    return () => clearTimeout(timer)
  }, [value])

  // Close on outside click.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", onDocClick)
    return () => document.removeEventListener("mousedown", onDocClick)
  }, [])

  function choose(name: string) {
    skipNextFetch.current = true // prevent the value change from reopening the dropdown
    setValue(name)
    setOpen(false)
    setSuggestions([])
    setActiveIndex(-1)
    requestSeq.current++ // invalidate any in-flight request
    onSelect(name)
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (open && activeIndex >= 0 && activeIndex < suggestions.length) {
      choose(suggestions[activeIndex].name)
      return
    }
    const name = value.trim()
    if (name) {
      setOpen(false)
      onSelect(name)
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return

    if (e.key === "ArrowDown") {
      if (!open && suggestions.length > 0) {
        setOpen(true)
        return
      }
      if (suggestions.length === 0) return
      e.preventDefault()
      setActiveIndex((i) => (i + 1) % suggestions.length)
    } else if (e.key === "ArrowUp") {
      if (suggestions.length === 0) return
      e.preventDefault()
      setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1))
    } else if (e.key === "Escape") {
      setOpen(false)
      setActiveIndex(-1)
    }
    // Enter is handled by the form's submit.
  }

  const showDropdown = open && value.trim().length >= 2

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
      <div ref={containerRef} className="relative flex-1">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => {
            if (value.trim().length >= 2 && suggestions.length > 0) setOpen(true)
          }}
          onKeyDown={onKeyDown}
          placeholder="e.g. Amoxicillin, Cisplatin, Albuterol…"
          aria-label="Search a single drug"
          role="combobox"
          aria-expanded={showDropdown}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeIndex >= 0 ? `${listId}-opt-${activeIndex}` : undefined}
          autoComplete="off"
          className="h-11 w-full rounded-lg border border-input bg-card pl-9 pr-9 text-sm text-foreground shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/40"
        />
        {loading && (
          <Loader2
            className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground"
            aria-hidden="true"
          />
        )}

        {showDropdown && (
          <div
            id={listId}
            role="listbox"
            className="absolute left-0 right-0 top-[calc(100%+0.375rem)] z-30 overflow-hidden rounded-lg border border-border bg-popover shadow-lg"
          >
            {suggestions.length > 0 ? (
              <ul className="max-h-72 overflow-y-auto py-1">
                {suggestions.map((s, i) => (
                  <li key={`${s.name}-${i}`}>
                    <button
                      type="button"
                      id={`${listId}-opt-${i}`}
                      role="option"
                      aria-selected={i === activeIndex}
                      onMouseEnter={() => setActiveIndex(i)}
                      onMouseDown={(e) => {
                        // Prevent the input blur from closing before the click registers.
                        e.preventDefault()
                        choose(s.name)
                      }}
                      className={`flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sm transition-colors ${
                        i === activeIndex ? "bg-accent text-accent-foreground" : "text-foreground hover:bg-accent/60"
                      }`}
                    >
                      <span className="flex items-center gap-2 truncate">
                        <Search className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                        <span className="truncate font-medium">{s.name}</span>
                      </span>
                      {s.is_brand && s.generic_name && (
                        <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                          {s.generic_name}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              queried &&
              !loading && <div className="px-3 py-3 text-sm text-muted-foreground">No matches found</div>
            )}
          </div>
        )}
      </div>
      <Button type="submit" className="h-11 px-6" disabled={!value.trim()}>
        Assess drug
      </Button>
    </form>
  )
}
