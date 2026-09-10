export function Limitations({ items }: { items: string[] }) {
  if (items.length === 0) return null
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">Limitations</h3>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-xs text-text-muted">
            <span className="text-text-faint">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
