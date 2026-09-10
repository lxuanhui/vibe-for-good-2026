import { defineConfig } from 'vitest/config'

// Separate from vite.config.ts on purpose. The app config carries the Tailwind
// plugin and the maplibre worker/pre-bundling workarounds, none of which a
// jsdom component test needs -- and loading Tailwind for every test run costs
// seconds for nothing. JSX is transformed from tsconfig.app.json's
// `"jsx": "react-jsx"`, so the React plugin is not needed either.
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    // Each test asserts on what the component asked the API seam for, so a
    // call recorded by the previous test must not still be there.
    restoreMocks: true,
  },
})
