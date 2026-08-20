import Link from "next/link"
import { ArrowRight, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { HeroPreview } from "@/components/landing/hero-preview"

const atAGlance = [
  "A severity read on the drugs you carry that are already in shortage",
  "Whether it's a supply problem or a demand spike driving it",
  "What that means for you: line up a backup supplier or stock up",
]

export function LandingHero() {
  return (
    <section className="relative overflow-x-clip border-b border-border">
      {/* Quietly-alive background: soft drifting mesh + faint grain, clipped to the section */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
        <div className="rx-mesh rx-mesh-a" />
        <div className="rx-mesh rx-mesh-b" />
        <div className="rx-grain" />
      </div>

      {/* Top bar */}
      <div className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary font-serif text-base font-semibold text-primary-foreground shadow-sm">
            Rx
          </span>
          <span className="text-xl font-semibold tracking-tight text-foreground">
            Rx<span className="text-primary">Watch</span>
          </span>
        </div>
        <div className="flex items-center gap-5">
          <span className="hidden text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground md:block">
            Shortage risk, on public data
          </span>
          <a
            href="/writeup"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
          >
            Methodology
          </a>
        </div>
      </div>

      <div className="relative z-10 mx-auto grid max-w-6xl items-center gap-10 px-5 pb-16 pt-8 sm:px-8 sm:pb-20 lg:grid-cols-12 lg:gap-10 lg:pb-28">
        {/* Left: headline */}
        <div className="min-w-0 lg:col-span-6">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">For independent pharmacies</p>
          <h1 className="mt-4 text-balance font-serif text-4xl font-semibold leading-[1.04] tracking-tight text-foreground sm:text-5xl lg:text-6xl">
            See what's actually behind a shortage, not just that it exists.
          </h1>
          <p className="mt-6 max-w-xl text-pretty text-lg leading-relaxed text-muted-foreground">
            Most shortage tools run on hospital purchasing feeds a corner pharmacy will never see. RxWatch works from
            public FDA data alone, so a two-person shop can understand why a listed shortage is happening, the same way
            a health system would.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button
              render={<Link href="/dashboard" />}
              nativeButton={false}
              size="lg"
              className="group gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/20 active:translate-y-0 motion-reduce:transform-none motion-reduce:transition-none"
            >
              Check your inventory
              <ArrowRight
                className="size-4 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transform-none"
                aria-hidden="true"
              />
            </Button>
            <Button
              render={<a href="#how-it-works" />}
              nativeButton={false}
              variant="ghost"
              size="lg"
              className="text-foreground"
            >
              See how it works
            </Button>
          </div>

          <ul className="mt-8 flex flex-col gap-2.5">
            {atAGlance.map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-sm leading-relaxed text-foreground">
                <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                <span className="text-pretty">{item}</span>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs leading-relaxed text-muted-foreground">
            No account, no wholesaler login, no cost. Your file is used only to score your inventory and isn't stored.
          </p>
        </div>

        {/* Right: floating dashboard preview, overlapping the section edge */}
        <div className="relative z-20 min-w-0 lg:col-span-6 lg:-mb-24 lg:pl-4">
          <HeroPreview />
        </div>
      </div>
    </section>
  )
}
