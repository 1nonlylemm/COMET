import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { BrandingProvider } from './hooks/BrandingProvider'
import { ThemeProvider } from './hooks/ThemeProvider'
import { ToastProvider } from './components'
import ErrorBoundary from './components/ErrorBoundary'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <BrandingProvider>
          <ToastProvider>
            <ErrorBoundary>
              <App />
            </ErrorBoundary>
          </ToastProvider>
        </BrandingProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
