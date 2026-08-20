const steps = [
  {
    title: "Upload what you carry",
    body: "Drop in a CSV of your inventory. Your file is used only to score it and isn't stored afterward.",
  },
  {
    title: "It's matched against FDA records",
    body: "Each drug is cross-referenced with current shortage listings, recall history, and how many firms actually make it.",
  },
  {
    title: "You get a score and a cause",
    body: "Every drug already in shortage comes back with a severity score and a likely cause: a supply-side problem or a demand-side spike.",
  },
  {
    title: "You know what kind of problem it is",
    body: "Understanding the cause tells you the right move, whether that's lining up a backup supplier or stocking up while you can.",
  },
]

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-heading"
      className="mx-auto max-w-6xl scroll-mt-6 px-5 py-16 sm:px-8 sm:py-20"
    >
      <div className="max-w-2xl">
        <h2
          id="how-heading"
          className="text-balance font-serif text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-4xl"
        >
          Four steps, start to finish
        </h2>
      </div>

      <ol className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((s, i) => (
          <li key={s.title} className="border-t-2 border-primary pt-4">
            <span className="font-serif text-4xl font-semibold leading-none tabular-nums text-primary">
              {i + 1}
            </span>
            <h3 className="mt-4 text-base font-semibold text-foreground">{s.title}</h3>
            <p className="mt-2 text-pretty text-sm leading-relaxed text-muted-foreground">{s.body}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
