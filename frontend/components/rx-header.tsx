import { Activity, ShieldCheck } from "lucide-react"

export function RxHeader() {
  return (
    <header className="border-b border-border bg-card/60 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Activity className="size-5" strokeWidth={2.4} aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              Rx<span className="text-primary">Watch</span>
            </h1>
            <p className="max-w-md text-pretty text-sm leading-relaxed text-muted-foreground">
              Shortage risk intelligence for independent pharmacies, built on public FDA data
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-start rounded-full bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground ring-1 ring-inset ring-border sm:self-auto">
          <ShieldCheck className="size-3.5 text-primary" aria-hidden="true" />
          openFDA · no proprietary access required
        </div>
      </div>
    </header>
  )
}
