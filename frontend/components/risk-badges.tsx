import type { ShortageStatus, MatchType } from "@/lib/rx-data"
import { cn } from "@/lib/utils"

const STATUS_LABELS: Record<ShortageStatus, string> = {
  current: "Current shortage",
  to_be_discontinued: "To be discontinued",
  resolved: "Resolved",
  not_listed: "Not on shortage list",
}

// not_listed is deliberately neutral gray, not green: green would imply
// "safe", and not being on the list doesn't mean a shortage can't occur.
const STATUS_STYLES: Record<ShortageStatus, string> = {
  current: "bg-red-50 text-red-700 ring-red-600/25",
  to_be_discontinued: "bg-orange-50 text-orange-700 ring-orange-600/25",
  resolved: "bg-muted text-muted-foreground ring-border",
  not_listed: "bg-transparent text-muted-foreground ring-border",
}

export function StatusBadge({ status }: { status: ShortageStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset",
        STATUS_STYLES[status],
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}

export function NotFoundBadge() {
  return (
    <span className="inline-flex items-center whitespace-nowrap rounded-full bg-transparent px-2.5 py-1 text-xs font-semibold text-muted-foreground ring-1 ring-inset ring-border">
      Not found
    </span>
  )
}

export function FewManufacturersBadge() {
  return (
    <span
      title="Only 1 or 2 companies list this drug, so there are fewer backup sources if one stops production."
      className="inline-flex items-center rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-600/20"
    >
      Few labelers
    </span>
  )
}

export function MatchTypeNote({
  matchedGenericName,
  matchType,
}: {
  matchedGenericName: string | null
  matchType: MatchType
}) {
  if (!matchedGenericName) {
    return (
      <p className="text-xs text-muted-foreground">
        Not found in FDA data. Check the spelling or try the generic name.
      </p>
    )
  }
  if (matchType === "approximate") {
    return (
      <p className="text-xs text-muted-foreground">
        Matched to: {matchedGenericName} (approximate match, please verify)
      </p>
    )
  }
  return null
}
