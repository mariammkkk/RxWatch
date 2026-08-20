const problems = [
  {
    title: "Shortages are the normal state of things",
    body: "Hundreds of drugs sit on the FDA shortage list on any given day. For a small pharmacy, one gap can mean turning a patient away or spending an afternoon on the phone chasing stock.",
  },
  {
    title: "The good prediction tools aren't built for you",
    body: "The models that forecast shortages run on hospital purchasing data and paid feeds. An independent pharmacy has no way to plug into any of it.",
  },
  {
    title: "By the time the FDA lists it, it's late",
    body: "Official listings are reactive. When a drug finally shows up as \"in shortage,\" your wholesaler has usually been rationing it for a while already.",
  },
]

export function ProblemSection() {
  return (
    <section aria-labelledby="problem-heading" className="mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-20">
      <div className="grid gap-10 lg:grid-cols-12 lg:gap-8">
        <div className="lg:col-span-5">
          <h2
            id="problem-heading"
            className="text-balance font-serif text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-4xl"
          >
            The gap independent pharmacies live with
          </h2>
          <p className="mt-4 max-w-sm text-pretty text-base leading-relaxed text-muted-foreground">
            Nothing here is a secret. It's just that the tools built to see it coming were never pointed at the
            corner pharmacy.
          </p>
        </div>

        <div className="lg:col-span-7">
          <dl className="border-t border-border">
            {problems.map((p, i) => (
              <div key={p.title} className="grid grid-cols-[auto_1fr] gap-x-5 border-b border-border py-6">
                <span className="font-serif text-2xl leading-none text-primary tabular-nums">{`0${i + 1}`}</span>
                <div>
                  <dt className="text-base font-semibold text-foreground">{p.title}</dt>
                  <dd className="mt-2 text-pretty text-sm leading-relaxed text-muted-foreground">{p.body}</dd>
                </div>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  )
}
