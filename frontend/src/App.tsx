import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [message, setMessage] = useState('Connecting to the API…')

  useEffect(() => {
    fetch('/api/hello')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((data: { message: string }) => setMessage(data.message))
      .catch((error: Error) => setMessage(`API unavailable: ${error.message}`))
  }, [])

  return (
    <main>
      <h1>Vibe for Good 2026</h1>
      <p>{message}</p>
    </main>
  )
}

export default App
