import type { Cause, RiskTier } from "@/lib/rx-data"
import { cn } from "@/lib/utils"

const TIER_STYLES: Record<RiskTier, string> = {
  Low: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  Medium: "bg-amber-50 text-amber-700 ring-amber-600/20",
  High: "bg-orange-50 text-orange-700 ring-orange-600/25",
  Critical: "bg-red-50 text-red-700 ring-red-600/25",
}

const TIER_DOT: Record<RiskTier, string> = {
  Low: "bg-emerald-500",
  Medium: "bg-amber-500",
  High: "bg-orange-500",
  Critical: "bg-red-500",
}

export function TierBadge({ tier, score }: { tier: RiskTier; score?: number }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset tabular-nums",
        TIER_STYLES[tier],
      )}
    >
      <span className={cn("size-1.5 rounded-full", TIER_DOT[tier])} aria-hidden="true" />
      {tier}
      {typeof score === "number" && <span className="font-mono opacity-70">· {score}</span>}
    </span>
  )
}

const CAUSE_STYLES: Record<Cause, string> = {
  "Supply-side": "bg-sky-50 text-sky-700 ring-sky-600/20",
  "Demand-side": "bg-violet-50 text-violet-700 ring-violet-600/20",
  Unclear: "bg-slate-100 text-slate-600 ring-slate-500/20",
}

export function CauseTag({ cause }: { cause: Cause }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        CAUSE_STYLES[cause],
      )}
    >
      {cause}
    </span>
  )
}

export function ShortageBadge({ active }: { active: boolean }) {
  if (active) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-700 ring-1 ring-inset ring-red-600/25">
        <span className="size-1.5 animate-pulse rounded-full bg-red-500" aria-hidden="true" />
        Yes
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground ring-1 ring-inset ring-border">
      No
    </span>
  )
}

export function tierBarColor(tier: RiskTier): string {
  return {
    Low: "bg-emerald-500",
    Medium: "bg-amber-500",
    High: "bg-orange-500",
    Critical: "bg-red-500",
  }[tier]
}
