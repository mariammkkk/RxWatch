import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"

export function FinalCta() {
  return (
    <section aria-labelledby="cta-heading" className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
      <div className="flex flex-col gap-8 border-t border-border pt-14 md:flex-row md:items-end md:justify-between">
        <div className="max-w-xl">
          <h2
            id="cta-heading"
            className="text-balance font-serif text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-4xl"
          >
            See where your inventory stands
          </h2>
          <p className="mt-3 text-pretty text-base leading-relaxed text-muted-foreground">
            Upload a CSV, or just search a single drug to try it. Takes about a minute.
          </p>
        </div>
        <Button
          render={<Link href="/dashboard" />}
          nativeButton={false}
          size="lg"
          className="group gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/20 active:translate-y-0 md:shrink-0 motion-reduce:transform-none motion-reduce:transition-none"
        >
          Check your inventory
          <ArrowRight
            className="size-4 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transform-none"
            aria-hidden="true"
          />
        </Button>
      </div>
    </section>
  )
}
