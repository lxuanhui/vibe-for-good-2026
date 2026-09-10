/** The product's name as users see it.

  Chosen by the team on 2026-09-10 (#257), replacing the provisional
  "Environmental Assurance Console" that PRODUCT.md had recorded as
  scaffolding. Every on-screen use reads this constant; index.html's <title>
  and meta tags repeat the string by hand because Vite's HTML entry is static
  and cannot import it. Change both together. */
export const APP_NAME = 'atmosclear.ai'

/** What the product is, for the line under the name and for <meta> copy. */
export const APP_DESCRIPTOR = 'Environmental assurance console'

export const APP_DESCRIPTION =
  'Reconstructs the satellite fire history of an audited management unit in Indonesia so an auditor can decide which events deserve a human question. It does not determine blame, intent or responsibility.'
