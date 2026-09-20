/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { createRoot } from "react-dom/client"
import App from "../../src/App"
import { AuthTestProvider } from "../../src/auth/AuthProvider"
import "../../src/index.css"
import "../../src/themes.css"
import "../../src/native/native.css"

createRoot(document.getElementById("root")!).render(
  <AuthTestProvider>
    <App />
  </AuthTestProvider>,
)
