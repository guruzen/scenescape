import { createRoot } from 'react-dom/client'
import { AuthProvider } from './auth/AuthProvider'
import App from './App'
import './index.css'
import './themes.css'

createRoot(document.getElementById('root')!).render(
  <AuthProvider>
    <App />
  </AuthProvider>,
)
