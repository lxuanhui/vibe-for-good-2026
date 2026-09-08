export function ExecutiveSummary({ text }: { text: string }) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">Executive summary</h3>
      <p className="text-sm leading-relaxed text-text-muted">{text}</p>
    </section>
  )
}
