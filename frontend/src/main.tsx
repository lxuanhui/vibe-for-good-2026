import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
// Side effect only: must run before any Map mounts. See the file for why.
import './lib/maplibreWorker.ts'
import App from './App.tsx'
import { DemoFlow } from './demo/DemoFlow.tsx'

// The console has no router: App is one state machine over a few screens.
// The one other path is /demo, the guided presenter flow (#274), decided
// here rather than inside App so App's hooks stay unconditional. Amplify
// rewrites any extensionless path to index.html (#218), so this resolves
// on the deployed console as well as on the dev server.
const isDemoPath = /^\/demo\/?$/.test(window.location.pathname)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isDemoPath ? <DemoFlow /> : <App />}
  </StrictMode>,
)
