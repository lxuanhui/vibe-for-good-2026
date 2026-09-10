/** The earth mark: a globe drawn as a graticule, in the current text colour.

  Strokes only, no fill, so it reads at 16 px in a tab strip and at 40 px in
  a header on either the dark ground or the white print theme. A real
  coastline was rejected: at favicon size it becomes a blob, and a stylised
  Borneo would put a map of the demo scope in the brand, which the product
  is not about. public/favicon.svg draws the same geometry with the dark
  ground baked in, because a favicon cannot inherit currentColor; if this
  path changes, update that file by hand. */
export function EarthMark({ className = 'h-5 w-5', title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <circle cx="16" cy="16" r="12.5" />
      <ellipse cx="16" cy="16" rx="5.2" ry="12.5" />
      <path d="M3.5 16h25M5.6 9.6q10.4 4 20.8 0M5.6 22.4q10.4-4 20.8 0" />
    </svg>
  )
}
