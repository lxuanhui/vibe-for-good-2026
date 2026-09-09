import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
// Side effect only: must run before any Map mounts. See the file for why.
import './lib/maplibreWorker.ts'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
