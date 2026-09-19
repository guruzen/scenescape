import { createRoot } from 'react-dom/client'
import App from '../src/App'
import '../src/index.css'
import '../src/themes.css'
import '../src/native/native.css'
createRoot(document.getElementById('root')!).render(<App />)
