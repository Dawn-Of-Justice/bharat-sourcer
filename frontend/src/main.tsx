import { AccountProvider } from './Account'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { ToastProvider } from './toast'
import '@fontsource-variable/source-sans-3'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ToastProvider>
      <AccountProvider>
        <App />
      </AccountProvider>
    </ToastProvider>
  </React.StrictMode>,
)
