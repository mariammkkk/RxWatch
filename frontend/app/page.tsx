import { LandingHero } from "@/components/landing/landing-hero"
import { ProblemSection } from "@/components/landing/problem-section"
import { StatsBand } from "@/components/landing/stats-band"
import { HowItWorks } from "@/components/landing/how-it-works"
import { CauseMatters } from "@/components/landing/cause-matters"
import { DataSources } from "@/components/landing/data-sources"
import { FinalCta } from "@/components/landing/final-cta"
import { Reveal } from "@/components/landing/reveal"

export default function LandingPage() {
  return (
    <div className="min-h-dvh">
      <LandingHero />
      <Reveal>
        <ProblemSection />
      </Reveal>
      <Reveal>
        <StatsBand />
      </Reveal>
      <Reveal>
        <HowItWorks />
      </Reveal>
      <Reveal>
        <CauseMatters />
      </Reveal>
      <Reveal>
        <DataSources />
      </Reveal>
      <Reveal>
        <FinalCta />
      </Reveal>

      <footer className="border-t border-border bg-card/40 py-8">
        <p className="mx-auto max-w-3xl px-5 text-center text-sm leading-relaxed text-muted-foreground sm:px-8">
          RxWatch is a demonstration tool built on openFDA public datasets. It's meant to point you at what to check,
          not to replace wholesaler-verified supply status.
        </p>
      </footer>
    </div>
  )
}
