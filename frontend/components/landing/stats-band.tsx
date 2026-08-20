const claims = [
  {
    head: "It explains what's driving it",
    body: "For the drugs you carry that are already in an FDA-reported shortage, RxWatch reads the likely cause, so you understand why it's happening instead of just that it is.",
  },
  {
    head: "It tells you what kind of problem it is",
    body: "It separates shortages caused by supply problems from those caused by a sudden jump in demand, so you know whether to line up a backup supplier or simply stock up.",
  },
  {
    head: "There's nothing to log into",
    body: "It runs entirely on public FDA data. No hospital system, no wholesaler account, no paid feed, no per-seat license.",
  },
]

export function StatsBand() {
  return (
    <section aria-labelledby="impact-heading" className="relative overflow-hidden bg-primary text-primary-foreground">
      <div aria-hidden="true" className="rx-mesh rx-mesh-light" />
      <div className="relative z-10 mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-20">
        <h2
          id="impact-heading"
          className="max-w-2xl text-balance font-serif text-3xl font-semibold leading-[1.1] tracking-tight sm:text-4xl"
        >
          What it actually does for you
        </h2>

        <div className="mt-12 grid gap-px overflow-hidden rounded-lg border border-primary-foreground/20 bg-primary-foreground/20 sm:grid-cols-3">
          {claims.map((c) => (
            <div key={c.head} className="bg-primary p-6">
              <h3 className="text-lg font-semibold leading-snug">{c.head}</h3>
              <p className="mt-3 text-pretty text-sm leading-relaxed text-primary-foreground/80">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
