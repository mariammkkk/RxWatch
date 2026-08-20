export function CauseMatters() {
  return (
    <section aria-labelledby="cause-heading" className="border-t border-border bg-card">
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-20">
        <div className="max-w-2xl">
          <h2
            id="cause-heading"
            className="text-balance font-serif text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-4xl"
          >
            A score tells you what to watch. The cause tells you what to do.
          </h2>
        </div>

        <div className="mt-12 grid gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-2">
          <div className="bg-card p-7 sm:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Supply-side</p>
            <h3 className="mt-3 font-serif text-xl font-semibold text-foreground">A manufacturing problem</h3>
            <p className="mt-3 text-pretty text-sm leading-relaxed text-muted-foreground">
              A thin roster of manufacturers, a fragile drug class, a plant going down. In this analysis, oral drugs
              skewed supply-side. When supply is the constraint, the move is to buy ahead and spread your sourcing while
              the stock is still there.
            </p>
          </div>

          <div className="bg-card p-7 sm:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--chart-4)]">Demand-side</p>
            <h3 className="mt-3 font-serif text-xl font-semibold text-foreground">A sudden run on the drug</h3>
            <p className="mt-3 text-pretty text-sm leading-relaxed text-muted-foreground">
              A seasonal surge, a guideline change, something going viral. In this analysis, injectables skewed
              demand-side. When demand is the driver, watch for allocation limits and hold back enough supply for the
              patients already relying on you.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
