import { useCallback, useState } from 'react'

const DISMISSED_KEY = 'eac.console-context-panel.dismissed'

function readDismissed(): boolean {
  // Private windows, cleared site data and browsers that block storage all
  // throw here. Failing open shows the panel again rather than hiding the
  // explanation from someone who has never seen it.
  try {
    return localStorage.getItem(DISMISSED_KEY) === '1'
  } catch {
    return false
  }
}

/**
 * Open/dismissed state for the first-load explanation, persisted per browser.
 * Kept out of the zustand store because nothing else reads it and it has to
 * survive a reload, which the store does not. Kept out of the component file
 * so that file exports only components and fast refresh keeps working.
 */
export function useConsoleContextPanel() {
  const [open, setOpen] = useState(() => !readDismissed())

  const dismiss = useCallback(() => {
    setOpen(false)
    try {
      localStorage.setItem(DISMISSED_KEY, '1')
    } catch {
      // Dismissal not persisting is survivable; the panel simply returns.
    }
  }, [])

  const reopen = useCallback(() => setOpen(true), [])

  return { open, dismiss, reopen }
}
