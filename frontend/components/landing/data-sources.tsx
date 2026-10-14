const sources = [
  {
    name: "openFDA Drug Shortages",
    body: "The current and resolved shortage records themselves, so a drug that's already flagged always shows its real FDA status.",
  },
  {
    name: "NDC Directory",
    body: "How many firms actually list each product. A drug made by one manufacturer behaves very differently from one made by twelve.",
  },
  {
    name: "Enforcement Reports",
    body: "Recall activity that can quietly tip an already-thin supply into a real shortage before anything is formally listed.",
  },
]

export function DataSources() {
  return (
    <section aria-labelledby="sources-heading" className="mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-20">
      <div className="grid gap-10 lg:grid-cols-12 lg:gap-8">
        <div className="lg:col-span-5">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">No black box</p>
          <h2
            id="sources-heading"
            className="mt-4 text-balance font-serif text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-4xl"
          >
            Exactly which data it reads
          </h2>
          <p className="mt-4 max-w-sm text-pretty text-base leading-relaxed text-muted-foreground">
            Three public FDA datasets, pulled through openFDA. All of it is free and open, which is the whole point,
            no login stands between you and it.
          </p>
        </div>

        <div className="lg:col-span-7">
          <dl className="border-t border-border">
            {sources.map((s) => (
              <div key={s.name} className="border-b border-border py-6">
                <dt className="text-sm font-semibold tracking-tight text-foreground">{s.name}</dt>
                <dd className="mt-2 max-w-xl text-pretty text-sm leading-relaxed text-muted-foreground">{s.body}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  )
}
