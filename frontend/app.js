/**
 * ClaimSense AI - Unified Frontend Controller
 * Complete Phase 1-5 Implementation:
 *   - Phase 1 & 2: Health Monitoring, Multi-Source Evidence Upload, Real-Time Validation
 *   - Phase 3: User Authentication, Session Rotation, CSRF Protection, XSS Sanitization, PDF Receipts
 *   - Phase 4: Three-Section Dashboard, Policy & Claim Lookup, Replacement Vehicle Image Handling
 *   - Phase 5: YOLOv8 Computer Vision Damage Detection & Automated Visual Inspection
 */

function initClaimSenseApp() {
    let currentUser = null;
    let currentActiveClaimId = null;
    let activeSection = "submit";
    let mySubmissionsData = [];
    let csrfToken = null;
    let currentLang = localStorage.getItem("claimsense_lang") || "en";

    // -------------------------------------------------------------
    // Helper: HTML Entity Escaping (Prevent Stored & Reflected XSS)
    // -------------------------------------------------------------
    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    const escapeHTML = escapeHtml;

    // -------------------------------------------------------------
    // Helper: Format File Sizes
    // -------------------------------------------------------------
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return "0 Bytes";
        const k = 1024;
        const sizes = ["Bytes", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    // -------------------------------------------------------------
    // Robust CSRF Token Management & Input Synchronization
    // -------------------------------------------------------------
    function getCsrfToken() {
        if (csrfToken) return csrfToken;
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content && meta.content.trim()) {
            csrfToken = meta.content.trim();
            return csrfToken;
        }
        const match = document.cookie.match(/(?:^|;\s*)claimsense_csrf_token=([^;]+)/);
        if (match && match[1]) {
            csrfToken = decodeURIComponent(match[1]).trim();
            return csrfToken;
        }
        const input = document.querySelector('input[name="csrf_token"]');
        if (input && input.value && input.value.trim()) {
            csrfToken = input.value.trim();
            return csrfToken;
        }
        return null;
    }

    function syncCsrfInputs(token) {
        if (!token) return;
        csrfToken = token;
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) meta.content = token;
        document.querySelectorAll('input[name="csrf_token"]').forEach((input) => {
            input.value = token;
        });
    }

    async function fetchCsrfToken() {
        try {
            const res = await fetch("/api/auth/csrf-token", { credentials: "same-origin" });
            if (res.ok) {
                const data = await res.json();
                if (data && data.csrf_token) {
                    syncCsrfInputs(data.csrf_token);
                    return data.csrf_token;
                }
            }
        } catch (err) {
            console.warn("Could not retrieve CSRF token from endpoint:", err);
        }
        const fallback = getCsrfToken();
        if (fallback) syncCsrfInputs(fallback);
        return fallback;
    }

    // Synchronize initial CSRF token immediately on page load
    const initialCsrf = getCsrfToken();
    if (initialCsrf) {
        syncCsrfInputs(initialCsrf);
    }
    fetchCsrfToken();

    // -------------------------------------------------------------
    // Application API Base URL Resolution (Same-Origin or Configured Base)
    // -------------------------------------------------------------
    function getConfiguredApiBase() {
        if (typeof window !== "undefined" && typeof window.CLAIMSENSE_API_BASE === "string" && window.CLAIMSENSE_API_BASE.trim()) {
            return window.CLAIMSENSE_API_BASE.trim().replace(/\/+$/, "");
        }
        if (typeof document !== "undefined") {
            const meta = document.querySelector('meta[name="api-base"]');
            if (meta && meta.content && meta.content.trim()) {
                return meta.content.trim().replace(/\/+$/, "");
            }
        }
        return "";
    }

    function getApiUrl(endpoint) {
        if (!endpoint) return "";
        if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) {
            return endpoint;
        }
        const ep = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
        const configuredBase = getConfiguredApiBase();
        if (configuredBase) {
            return `${configuredBase}${ep}`;
        }
        if (typeof window !== "undefined" && window.location && window.location.protocol === "file:") {
            return `http://127.0.0.1:5001${ep}`;
        }
        return ep;
    }

    // -------------------------------------------------------------
    // Robust HTTP / JSON Response Parser (Gracefully handles non-JSON / HTML errors)
    // -------------------------------------------------------------
    async function safeFetchJson(endpoint, options = {}) {
        const fullUrl = getApiUrl(endpoint);
        const fetchOptions = { ...options };
        fetchOptions.headers = { ...(options.headers || {}) };

        // Attach CSRF token if available
        const token = getCsrfToken();
        if (token && !fetchOptions.headers["X-CSRFToken"]) {
            fetchOptions.headers["X-CSRFToken"] = token;
            fetchOptions.headers["X-CSRF-Token"] = token;
        }

        let response;
        try {
            response = await fetch(fullUrl, fetchOptions);
        } catch (networkErr) {
            const originHint = (typeof window !== "undefined" && window.location && window.location.origin && window.location.origin !== "null")
                ? window.location.origin
                : (getConfiguredApiBase() || "the configured backend");
            return {
                ok: false,
                status: 0,
                contentType: "",
                data: null,
                error: `Cannot connect to ClaimSense AI backend (${originHint}). (${networkErr.message})`,
            };
        }

        const contentType = (response.headers.get("content-type") || "").toLowerCase();
        const isJson = contentType.includes("application/json");

        if (isJson) {
            try {
                const data = await response.json();
                return {
                    ok: response.ok,
                    status: response.status,
                    contentType,
                    data,
                    error: !response.ok ? (data.message || data.error || `Request failed with HTTP ${response.status}`) : null,
                };
            } catch (jsonErr) {
                return {
                    ok: false,
                    status: response.status,
                    contentType,
                    data: null,
                    error: `Failed to parse response as JSON (${jsonErr.message}).`,
                };
            }
        } else {
            // Non-JSON response (e.g. HTML 500, 404, or dev server fallback)
            let textSnippet = "";
            try {
                const rawText = await response.text();
                if (rawText.includes("<title>")) {
                    const match = rawText.match(/<title>(.*?)<\/title>/i);
                    if (match && match[1]) textSnippet = match[1].trim();
                } else {
                    textSnippet = rawText.substring(0, 120).trim();
                }
            } catch (e) {
                textSnippet = "";
            }

            let msg = `Server returned HTTP ${response.status} (${response.statusText || "Non-JSON"}).`;
            if (response.status === 404) {
                msg = `API endpoint not found (HTTP 404): ${endpoint}`;
            } else if (response.status === 401) {
                msg = "Authentication required (HTTP 401). Please sign in to perform this operation.";
            } else if (response.status === 403) {
                msg = "Access forbidden (HTTP 403). You do not have permission for this claim.";
            } else if (response.status === 413) {
                msg = "Uploaded file exceeds maximum allowed limit (HTTP 413).";
            } else if (response.status === 500) {
                msg = `Internal server error (HTTP 500)${textSnippet ? `: ${textSnippet}` : "."}`;
            } else if (textSnippet) {
                msg += ` (${textSnippet})`;
            }

            return {
                ok: false,
                status: response.status,
                contentType,
                data: null,
                error: msg,
            };
        }
    }

    // -------------------------------------------------------------
    // 1. Lightweight Backend Health Monitor (Header Status)
    // -------------------------------------------------------------
    const statusIndicator = document.getElementById("status-indicator");
    const statusBadge = document.getElementById("status-badge");

    async function checkBackendHealth() {
        if (statusIndicator) statusIndicator.className = "status-indicator";
        if (statusBadge) statusBadge.textContent = currentLang === "hi" ? "सर्वर जांचा जा रहा है..." : "Checking backend...";

        const res = await safeFetchJson("/api/health/live");
        if (res.ok && res.data) {
            if (statusIndicator) statusIndicator.className = "status-indicator connected";
            if (statusBadge) statusBadge.textContent = currentLang === "hi" ? "बैकएंड कनेक्टेड" : "Backend Connected";
        } else {
            if (statusIndicator) statusIndicator.className = "status-indicator error";
            if (statusBadge) statusBadge.textContent = currentLang === "hi" ? "बैकएंड डिस्कनेक्टेड" : "Backend Disconnected";
        }
    }
    checkBackendHealth();
    setInterval(checkBackendHealth, 30000);

    // -------------------------------------------------------------
    // 2. Theme Toggle (Dark / Light Theme Persistence)
    // -------------------------------------------------------------
    const themeToggleBtn = document.getElementById("theme-toggle");

    function getPreferredTheme() {
        const saved = localStorage.getItem("claimsense-theme") || localStorage.getItem("claimsense_theme");
        if (saved === "light" || saved === "dark") return saved;
        const currentAttr = document.documentElement.getAttribute("data-theme");
        if (currentAttr === "light" || currentAttr === "dark") return currentAttr;
        return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }

    function applyTheme(theme) {
        const targetTheme = theme === "light" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", targetTheme);
        localStorage.setItem("claimsense-theme", targetTheme);
        localStorage.setItem("claimsense_theme", targetTheme);
        updateThemeToggleUI(targetTheme);
    }

    function updateThemeToggleUI(theme) {
        if (!themeToggleBtn) return;
        const label = themeToggleBtn.querySelector(".theme-label");
        const icon = themeToggleBtn.querySelector(".theme-icon");
        if (theme === "light") {
            if (icon) {
                icon.innerHTML = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`;
            }
            if (label) label.textContent = "Light";
            themeToggleBtn.setAttribute("aria-label", "Switch to Dark Mode");
            themeToggleBtn.setAttribute("title", "Switch to Dark Theme");
        } else {
            if (icon) {
                icon.innerHTML = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;
            }
            if (label) label.textContent = "Dark";
            themeToggleBtn.setAttribute("aria-label", "Switch to Light Mode");
            themeToggleBtn.setAttribute("title", "Switch to Light Theme");
        }
    }

    applyTheme(getPreferredTheme());

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            const current = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
            applyTheme(current === "light" ? "dark" : "light");
        });
    }

    // -------------------------------------------------------------
    // 3. User Authentication & Session Management
    // -------------------------------------------------------------
    const authModal = document.getElementById("auth-modal");
    const authModalClose = document.getElementById("btn-close-auth-modal") || document.getElementById("auth-modal-close");
    const tabBtnLogin = document.getElementById("tab-btn-login");
    const tabBtnSignup = document.getElementById("tab-btn-signup");
    const loginForm = document.getElementById("login-form");
    const signupForm = document.getElementById("signup-form");
    const authAlert = document.getElementById("auth-alert");
    const headerAuth = document.getElementById("header-auth");

    const linkSwitchToSignup = document.getElementById("link-switch-to-signup");
    const linkSwitchToLogin = document.getElementById("link-switch-to-login");

    function showAuthAlert(msg) {
        if (!authAlert) return;
        authAlert.textContent = msg;
        authAlert.style.display = "block";
    }

    function clearAuthAlert() {
        if (!authAlert) return;
        authAlert.textContent = "";
        authAlert.style.display = "none";
    }

    function openAuthModal(tab = "login") {
        if (!authModal) return;
        clearAuthAlert();
        switchAuthTab(tab);
        authModal.style.display = "flex";
        fetchCsrfToken();
    }
    const showAuthModal = openAuthModal;

    function closeAuthModal() {
        if (!authModal) return;
        authModal.style.display = "none";
        clearAuthAlert();
        if (loginForm) loginForm.reset();
        if (signupForm) signupForm.reset();
    }

    function switchAuthTab(tab) {
        clearAuthAlert();
        if (tab === "login") {
            if (tabBtnLogin) tabBtnLogin.classList.add("active");
            if (tabBtnSignup) tabBtnSignup.classList.remove("active");
            if (loginForm) loginForm.style.display = "block";
            if (signupForm) signupForm.style.display = "none";
            const title = document.getElementById("modal-title");
            if (title) title.textContent = "Account Sign In";
        } else {
            if (tabBtnSignup) tabBtnSignup.classList.add("active");
            if (tabBtnLogin) tabBtnLogin.classList.remove("active");
            if (loginForm) loginForm.style.display = "none";
            if (signupForm) signupForm.style.display = "block";
            const title = document.getElementById("modal-title");
            if (title) title.textContent = "Create New Account";
        }
    }

    if (authModalClose) authModalClose.addEventListener("click", closeAuthModal);
    if (tabBtnLogin) tabBtnLogin.addEventListener("click", () => switchAuthTab("login"));
    if (tabBtnSignup) tabBtnSignup.addEventListener("click", () => switchAuthTab("signup"));
    if (linkSwitchToSignup) {
        linkSwitchToSignup.addEventListener("click", (e) => {
            e.preventDefault();
            switchAuthTab("signup");
        });
    }
    if (linkSwitchToLogin) {
        linkSwitchToLogin.addEventListener("click", (e) => {
            e.preventDefault();
            switchAuthTab("login");
        });
    }

    // Modal background click to close
    window.addEventListener("click", (e) => {
        if (e.target === authModal) closeAuthModal();
        const modalClaimDetails = document.getElementById("modal-claim-details");
        const modalClaimEvidence = document.getElementById("modal-claim-evidence");
        if (e.target === modalClaimDetails && typeof closeClaimDetailsModal === "function") closeClaimDetailsModal();
        if (e.target === modalClaimEvidence && typeof closeClaimEvidenceModal === "function") closeClaimEvidenceModal();
    });

    function renderHeaderAuth() {
        if (headerAuth) {
            if (currentUser) {
                headerAuth.innerHTML = `
                    <div class="user-badge" id="user-badge">
                        <span class="user-role-pill">${escapeHtml(currentUser.role || "user")}</span>
                        <span>${escapeHtml(currentUser.full_name || currentUser.username)}</span>
                    </div>
                    <button type="button" id="btn-header-logout" class="btn btn-outline btn-sm">Sign Out</button>
                `;
                const btnLogout = document.getElementById("btn-header-logout");
                if (btnLogout) {
                    btnLogout.addEventListener("click", handleLogout);
                }
            } else {
                headerAuth.innerHTML = `
                    <button type="button" id="btn-nav-login" class="btn btn-secondary btn-sm">Sign In</button>
                    <button type="button" id="btn-nav-signup" class="btn btn-primary btn-sm">Register</button>
                `;
                const btnLogin = document.getElementById("btn-nav-login");
                const btnSignup = document.getElementById("btn-nav-signup");
                if (btnLogin) btnLogin.addEventListener("click", () => openAuthModal("login"));
                if (btnSignup) btnSignup.addEventListener("click", () => openAuthModal("signup"));
            }
        }

        // Sidebar user info synchronization
        const sidebarUserName = document.getElementById("sidebar-user-name");
        const sidebarUserRole = document.getElementById("sidebar-user-role");
        const sidebarUserAvatar = document.getElementById("sidebar-user-avatar");
        if (currentUser) {
            if (sidebarUserName) sidebarUserName.textContent = currentUser.full_name || currentUser.username;
            if (sidebarUserRole) sidebarUserRole.textContent = (currentUser.role === "admin" ? "Claims Assessor" : "Verified Claimant");
            if (sidebarUserAvatar) sidebarUserAvatar.textContent = (currentUser.full_name || currentUser.username || "U")[0].toUpperCase();
        } else {
            if (sidebarUserName) sidebarUserName.textContent = "Guest User";
            if (sidebarUserRole) sidebarUserRole.textContent = "Sign In Required";
            if (sidebarUserAvatar) sidebarUserAvatar.textContent = "G";
        }
    }

    async function checkCurrentUserSession() {
        try {
            const res = await fetch("/api/auth/me", { credentials: "same-origin" });
            if (res.ok) {
                const data = await res.json();
                if (data.authenticated && data.user) {
                    currentUser = data.user;
                } else {
                    currentUser = null;
                }
            } else {
                currentUser = null;
            }
        } catch {
            currentUser = null;
        } finally {
            renderHeaderAuth();
        }
    }
    checkCurrentUserSession();

    // Login Form Submit
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            clearAuthAlert();
            const idInput = document.getElementById("login-identifier");
            const pwdInput = document.getElementById("login-password");
            const identifier = idInput ? idInput.value.trim() : "";
            const password = pwdInput ? pwdInput.value : "";

            if (!identifier || !password) {
                showAuthAlert("Please enter both identifier and password.");
                return;
            }

            let token = getCsrfToken();
            if (!token) token = await fetchCsrfToken();
            if (token) syncCsrfInputs(token);

            const headers = { "Content-Type": "application/json" };
            if (token) {
                headers["X-CSRFToken"] = token;
                headers["X-CSRF-Token"] = token;
            }

            const payload = { identifier, password };
            if (token) payload["csrf_token"] = token;

            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    credentials: "same-origin",
                    headers,
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    showAuthAlert(data.message || "Invalid username or password.");
                    return;
                }

                currentUser = data.user;
                renderHeaderAuth();
                if (data.csrf_token) syncCsrfInputs(data.csrf_token);
                closeAuthModal();

                if (activeSection === "myclaims" && typeof loadMyClaims === "function") {
                    loadMyClaims();
                }
            } catch (err) {
                showAuthAlert(`Login failed: ${err.message}`);
            }
        });
    }

    // Signup Form Submit

    if (signupForm) {
        signupForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            clearAuthAlert();

            const fullNameInput = document.getElementById("signup-fullname");
            const usernameInput = document.getElementById("signup-username");
            const emailInput = document.getElementById("signup-email");
            const passwordInput = document.getElementById("signup-password");
            const confirmInput = document.getElementById("signup-confirm");

            const full_name = fullNameInput ? fullNameInput.value.trim() : "";
            const username = usernameInput ? usernameInput.value.trim() : "";
            const email = emailInput ? emailInput.value.trim() : "";
            const password = passwordInput ? passwordInput.value : "";
            const confirm_password = confirmInput ? confirmInput.value : "";

            if (!full_name || !username || !email || !password || !confirm_password) {
                showAuthAlert("All fields are required.");
                return;
            }

            if (password.length < 8 || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
                showAuthAlert("Password must be at least 8 characters and include both letters and numbers.");
                return;
            }

            if (password !== confirm_password) {
                showAuthAlert("Passwords do not match.");
                return;
            }

            let token = getCsrfToken();
            if (!token) token = await fetchCsrfToken();
            if (token) syncCsrfInputs(token);

            const headers = { "Content-Type": "application/json" };
            if (token) {
                headers["X-CSRFToken"] = token;
                headers["X-CSRF-Token"] = token;
            }

            const payload = {
                full_name,
                username,
                email,
                password,
                confirm_password,
            };
            if (token) payload["csrf_token"] = token;

            try {
                const res = await fetch("/api/auth/signup", {
                    method: "POST",
                    credentials: "same-origin",
                    headers,
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    showAuthAlert(data.message || "Failed to create account.");
                    return;
                }

                if (data.csrf_token) syncCsrfInputs(data.csrf_token);

                // Auto login after successful signup
                const loginToken = getCsrfToken();
                const loginHeaders = { "Content-Type": "application/json" };
                if (loginToken) {
                    loginHeaders["X-CSRFToken"] = loginToken;
                    loginHeaders["X-CSRF-Token"] = loginToken;
                }
                const loginPayload = { identifier: username, password };
                if (loginToken) loginPayload["csrf_token"] = loginToken;

                try {
                    const loginRes = await fetch("/api/auth/login", {
                        method: "POST",
                        credentials: "same-origin",
                        headers: loginHeaders,
                        body: JSON.stringify(loginPayload),
                    });
                    const loginData = await loginRes.json();
                    if (loginRes.ok && loginData.success) {
                        currentUser = loginData.user;
                        renderHeaderAuth();
                        if (loginData.csrf_token) syncCsrfInputs(loginData.csrf_token);
                    }
                } catch {
                    // Fallback to switching tab
                }

                closeAuthModal();
                if (activeSection === "myclaims" && typeof loadMyClaims === "function") {
                    loadMyClaims();
                }
            } catch (err) {
                showAuthAlert(`Account registration failed: ${err.message}`);
            }
        });
    }

    async function handleLogout() {
        try {
            let token = getCsrfToken();
            if (!token) token = await fetchCsrfToken();
            const headers = {};
            if (token) {
                headers["X-CSRFToken"] = token;
                headers["X-CSRF-Token"] = token;
            }
            await fetch("/api/auth/logout", {
                method: "POST",
                credentials: "same-origin",
                headers,
            });
        } catch {
            // ignore network error on logout
        } finally {
            currentUser = null;
            renderHeaderAuth();
            fetchCsrfToken();
            if (activeSection === "myclaims") {
                switchView("submit");
            }
        }
    }

    // -------------------------------------------------------------
    // 4. Toast Notification System
    // -------------------------------------------------------------
    function showToast(message, type = "info", duration = 4000) {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast-item toast-${type}`;

        let iconSvg = "";
        if (type === "success") {
            iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
        } else if (type === "error") {
            iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
        } else if (type === "warning") {
            iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
        } else {
            iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
        }

        toast.innerHTML = `
            <span class="toast-icon">${iconSvg}</span>
            <span class="toast-message">${escapeHtml(message)}</span>
            <button type="button" class="toast-close" aria-label="Close notification">&times;</button>
        `;

        const closeBtn = toast.querySelector(".toast-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", () => {
                toast.style.opacity = "0";
                toast.style.transform = "translateY(12px)";
                setTimeout(() => toast.remove(), 250);
            });
        }

        container.appendChild(toast);

        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.opacity = "0";
                toast.style.transform = "translateY(12px)";
                setTimeout(() => toast.remove(), 250);
            }
        }, duration);
    }

    // -------------------------------------------------------------
    // 4b. Multilingual Support (English & Hindi Translations)
    // -------------------------------------------------------------
    // currentLang is initialized at the top of initClaimSenseApp() to avoid TDZ errors.

    function t(key, fallback = "") {
        const tr = window.CLAIM_TRANSLATIONS || window.CLAIMSENSE_TRANSLATIONS || {};
        const dict = tr[currentLang] || tr["en"] || {};
        if (dict[key] !== undefined) return dict[key];
        return fallback || key;
    }

    function applyTranslations() {
        document.querySelectorAll("[data-i18n]").forEach((el) => {
            if (el.id === "status-badge") {
                const isConn = statusIndicator && statusIndicator.classList.contains("connected");
                const isErr = statusIndicator && statusIndicator.classList.contains("error");
                if (isConn) {
                    el.textContent = currentLang === "hi" ? "बैकएंड कनेक्टेड" : "Backend Connected";
                    return;
                }
                if (isErr) {
                    el.textContent = currentLang === "hi" ? "बैकएंड डिस्कनेक्टेड" : "Backend Disconnected";
                    return;
                }
            }
            const key = el.getAttribute("data-i18n");
            const val = t(key);
            if (val) {
                if (el.children.length === 0) {
                    el.textContent = val;
                } else {
                    const textNode = Array.from(el.childNodes).find((n) => n.nodeType === Node.TEXT_NODE);
                    if (textNode) {
                        textNode.textContent = val + " ";
                    } else {
                        el.textContent = val;
                    }
                }
            }
        });

        document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
            const key = el.getAttribute("data-i18n-placeholder");
            const val = t(key);
            if (val) el.setAttribute("placeholder", val);
        });

        const langSelect = document.getElementById("lang-select");
        if (langSelect) langSelect.value = currentLang;
        const settingsLang = document.getElementById("settings-lang-select");
        if (settingsLang) settingsLang.value = currentLang;
    }

    function setLanguage(lang) {
        currentLang = lang === "hi" ? "hi" : "en";
        localStorage.setItem("claimsense_lang", currentLang);
        applyTranslations();
        showToast(currentLang === "hi" ? "भाषा बदलकर हिंदी कर दी गई है।" : "Language changed to English.", "info");
    }

    const langSelect = document.getElementById("lang-select");
    if (langSelect) {
        langSelect.addEventListener("change", (e) => setLanguage(e.target.value));
    }
    const settingsLang = document.getElementById("settings-lang-select");
    if (settingsLang) {
        settingsLang.addEventListener("change", (e) => setLanguage(e.target.value));
    }

    // -------------------------------------------------------------
    // 4c. Enterprise Portal Navigation & View Switcher
    // -------------------------------------------------------------
    const pillDashboard = document.getElementById("pill-nav-dashboard");
    const pillSubmit = document.getElementById("pill-nav-submit");
    const pillSearch = document.getElementById("pill-nav-search");
    const pillMyClaims = document.getElementById("pill-nav-myclaims");
    const pillHelp = document.getElementById("pill-nav-help");
    const pillDocuments = document.getElementById("pill-nav-documents");
    const pillReports = document.getElementById("pill-nav-reports");
    const pillSettings = document.getElementById("pill-nav-settings");

    const sectionDashboard = document.getElementById("section-dashboard");
    const sectionSubmit = document.getElementById("section-submit");
    const sectionLookup = document.getElementById("section-lookup");
    const sectionMyClaims = document.getElementById("section-myclaims");
    const sectionHelp = document.getElementById("section-help");
    const sectionDocuments = document.getElementById("section-documents");
    const sectionReports = document.getElementById("section-reports");
    const sectionSettings = document.getElementById("section-settings");

    const submissionCard = document.getElementById("submission-card");
    const successCard = document.getElementById("submission-success-card");

    function switchView(sectionName) {
        if (!sectionName) sectionName = "dashboard";
        if (sectionName === "search") sectionName = "lookup";
        activeSection = sectionName;

        // Reset pills
        const allNavPills = [
            pillSubmit, pillSearch, pillMyClaims,
            document.getElementById("pill-nav-submit-legacy"),
            document.getElementById("pill-nav-search-legacy"),
            document.getElementById("pill-nav-myclaims-legacy")
        ];
        allNavPills.forEach((p) => {
            if (p) {
                p.classList.remove("active");
                p.setAttribute("aria-selected", "false");
            }
        });

        // Hide all 8 sections
        if (sectionDashboard) sectionDashboard.style.display = "none";
        if (sectionSubmit) sectionSubmit.style.display = "none";
        if (sectionLookup) sectionLookup.style.display = "none";
        if (sectionMyClaims) sectionMyClaims.style.display = "none";
        if (sectionHelp) sectionHelp.style.display = "none";
        if (sectionDocuments) sectionDocuments.style.display = "none";
        if (sectionReports) sectionReports.style.display = "none";
        if (sectionSettings) sectionSettings.style.display = "none";

        // Display targeted section
        if (sectionName === "dashboard") {
            if (sectionDashboard) sectionDashboard.style.display = "block";
            updateDashboardStats(mySubmissionsData);
        } else if (sectionName === "submit") {
            if (pillSubmit) {
                pillSubmit.classList.add("active");
                pillSubmit.setAttribute("aria-selected", "true");
            }
            const leg = document.getElementById("pill-nav-submit-legacy");
            if (leg) { leg.classList.add("active"); leg.setAttribute("aria-selected", "true"); }
            if (sectionSubmit) sectionSubmit.style.display = "block";
        } else if (sectionName === "search" || sectionName === "lookup") {
            if (pillSearch) {
                pillSearch.classList.add("active");
                pillSearch.setAttribute("aria-selected", "true");
            }
            const leg = document.getElementById("pill-nav-search-legacy");
            if (leg) { leg.classList.add("active"); leg.setAttribute("aria-selected", "true"); }
            if (sectionLookup) sectionLookup.style.display = "block";
        } else if (sectionName === "myclaims") {
            if (pillMyClaims) {
                pillMyClaims.classList.add("active");
                pillMyClaims.setAttribute("aria-selected", "true");
            }
            const leg = document.getElementById("pill-nav-myclaims-legacy");
            if (leg) { leg.classList.add("active"); leg.setAttribute("aria-selected", "true"); }
            if (sectionMyClaims) sectionMyClaims.style.display = "block";
            if (typeof loadMyClaims === "function") loadMyClaims();
        } else if (sectionName === "help") {
            if (sectionHelp) sectionHelp.style.display = "block";
        } else if (sectionName === "documents") {
            if (sectionDocuments) sectionDocuments.style.display = "block";
        } else if (sectionName === "reports") {
            if (sectionReports) sectionReports.style.display = "block";
        } else if (sectionName === "settings") {
            if (sectionSettings) sectionSettings.style.display = "block";
        }

        // Synchronize sidebar active state
        document.querySelectorAll(".sidebar-nav-item").forEach((item) => {
            const sec = item.getAttribute("data-view") || item.getAttribute("data-section");
            const isMatch = sec === sectionName ||
                ((sectionName === "lookup" || sectionName === "search") && (sec === "lookup" || sec === "search"));
            if (isMatch) {
                item.classList.add("active");
            } else {
                item.classList.remove("active");
            }
        });

        // Close mobile drawer if opened
        const sidebar = document.getElementById("app-sidebar") || document.getElementById("portal-sidebar") || document.querySelector(".portal-sidebar");
        if (sidebar) sidebar.classList.remove("mobile-open");

        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    if (pillDashboard) pillDashboard.addEventListener("click", () => switchView("dashboard"));
    if (pillSubmit) pillSubmit.addEventListener("click", () => switchView("submit"));
    if (pillSearch) pillSearch.addEventListener("click", () => switchView("lookup"));
    if (pillMyClaims) pillMyClaims.addEventListener("click", () => {
        if (!currentUser) {
            openAuthModal("login");
            showAuthAlert("Please sign in to view your submitted claims.");
            return;
        }
        switchView("myclaims");
    });
    if (pillHelp) pillHelp.addEventListener("click", () => switchView("help"));
    if (pillDocuments) pillDocuments.addEventListener("click", () => switchView("documents"));
    if (pillReports) pillReports.addEventListener("click", () => switchView("reports"));
    if (pillSettings) pillSettings.addEventListener("click", () => switchView("settings"));

    // Legacy quick-nav pills
    const pillSubmitLegacy = document.getElementById("pill-nav-submit-legacy");
    if (pillSubmitLegacy) pillSubmitLegacy.addEventListener("click", () => switchView("submit"));
    const pillSearchLegacy = document.getElementById("pill-nav-search-legacy");
    if (pillSearchLegacy) pillSearchLegacy.addEventListener("click", () => switchView("lookup"));
    const pillMyClaimsLegacy = document.getElementById("pill-nav-myclaims-legacy");
    if (pillMyClaimsLegacy) pillMyClaimsLegacy.addEventListener("click", () => {
        if (!currentUser) {
            openAuthModal("login");
            showAuthAlert("Please sign in to view your submitted claims.");
            return;
        }
        switchView("myclaims");
    });

    // Sidebar navigation click handlers
    document.querySelectorAll(".sidebar-nav-item").forEach((item) => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const sec = item.getAttribute("data-view") || item.getAttribute("data-section");
            if (!sec) return;
            if (sec === "myclaims" && !currentUser) {
                openAuthModal("login");
                showAuthAlert("Please sign in to view your submitted claims.");
                return;
            }
            switchView(sec);
        });
    });

    // Brand logo home navigation
    const headerLogoHome = document.getElementById("header-logo-home");
    if (headerLogoHome) {
        headerLogoHome.addEventListener("click", () => switchView("dashboard"));
    }

    // Header help button navigation
    const btnHeaderHelp = document.getElementById("btn-header-help");
    if (btnHeaderHelp) {
        btnHeaderHelp.addEventListener("click", () => switchView("help"));
    }

    // Sidebar collapse & mobile drawer toggle
    const portalSidebar = document.getElementById("app-sidebar") || document.getElementById("portal-sidebar") || document.querySelector(".portal-sidebar");
    const btnCollapseSidebar = document.getElementById("btn-collapse-sidebar");
    const btnMobileSidebar = document.getElementById("btn-mobile-sidebar");

    if (btnCollapseSidebar && portalSidebar) {
        btnCollapseSidebar.addEventListener("click", (e) => {
            e.preventDefault();
            portalSidebar.classList.toggle("sidebar-collapsed");
        });
    }

    if (btnMobileSidebar && portalSidebar) {
        btnMobileSidebar.addEventListener("click", (e) => {
            e.preventDefault();
            portalSidebar.classList.toggle("mobile-open");
        });
    }

    // Dashboard Quick Action Buttons
    [
        document.getElementById("btn-dash-submit-claim"),
        document.getElementById("btn-dash-first-claim"),
        document.getElementById("dash-btn-new-claim"),
        document.getElementById("btn-empty-submit")
    ].forEach((b) => {
        if (b) {
            b.addEventListener("click", () => {
                if (typeof resetClaimSubmissionForm === "function") {
                    resetClaimSubmissionForm();
                }
                switchView("submit");
                if (typeof goToWizardStep === "function") goToWizardStep(1);
            });
        }
    });

    [
        document.getElementById("btn-dash-open-help"),
        document.getElementById("btn-dashboard-help")
    ].forEach((b) => {
        if (b) b.addEventListener("click", () => switchView("help"));
    });

    const btnDashViewAll = document.getElementById("btn-dash-view-all");
    if (btnDashViewAll) {
        btnDashViewAll.addEventListener("click", () => {
            if (!currentUser) {
                openAuthModal("login");
                showAuthAlert("Please sign in to view your submitted claims.");
                return;
            }
            switchView("myclaims");
        });
    }

    const btnDashQuickPolicy = document.getElementById("btn-dash-quick-policy") || document.getElementById("dash-btn-quick-check");
    const dashQuickPolicyInput = document.getElementById("dash-quick-policy-input");
    function executeQuickPolicyLookup() {
        const query = dashQuickPolicyInput ? dashQuickPolicyInput.value.trim() : "";
        switchView("lookup");
        const searchInput = document.getElementById("search-policy-input");
        if (searchInput && query) {
            searchInput.value = query;
            const form = document.getElementById("policy-search-form");
            if (form) form.dispatchEvent(new Event("submit", { cancelable: true }));
        }
    }
    if (btnDashQuickPolicy) btnDashQuickPolicy.addEventListener("click", executeQuickPolicyLookup);
    if (dashQuickPolicyInput) {
        dashQuickPolicyInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                executeQuickPolicyLookup();
            }
        });
    }

    const dashBtnFillSample = document.getElementById("dash-btn-fill-sample");
    if (dashBtnFillSample) {
        dashBtnFillSample.addEventListener("click", () => {
            switchView("submit");
            if (btnFillSample) btnFillSample.click();
            goToWizardStep(1);
            showToast("Demo claim package pre-populated.", "info");
        });
    }

    // Portal Settings Buttons
    const btnSettingsTheme = document.getElementById("btn-settings-theme");
    if (btnSettingsTheme) {
        btnSettingsTheme.addEventListener("click", () => {
            const current = document.documentElement.getAttribute("data-theme") || "dark";
            applyTheme(current === "dark" ? "light" : "dark");
            showToast(`Switched to ${current === "dark" ? "Light" : "Dark"} theme.`, "info");
        });
    }

    const btnSettingsTour = document.getElementById("btn-settings-tour");
    if (btnSettingsTour) {
        btnSettingsTour.addEventListener("click", () => {
            if (typeof openOnboardingTour === "function") openOnboardingTour();
        });
    }

    const btnLaunchTour = document.getElementById("btn-launch-tour");
    if (btnLaunchTour) {
        btnLaunchTour.addEventListener("click", () => {
            if (typeof openOnboardingTour === "function") openOnboardingTour();
        });
    }

    // Documents & Reports Browse buttons
    const btnBrowseDocs = document.getElementById("btn-browse-docs-myclaims");
    if (btnBrowseDocs) {
        btnBrowseDocs.addEventListener("click", () => {
            if (!currentUser) {
                openAuthModal("login");
                showAuthAlert("Please sign in to view your submitted claims.");
                return;
            }
            switchView("myclaims");
        });
    }
    const btnBrowseReports = document.getElementById("btn-browse-reports-myclaims");
    if (btnBrowseReports) {
        btnBrowseReports.addEventListener("click", () => {
            if (!currentUser) {
                openAuthModal("login");
                showAuthAlert("Please sign in to view your submitted claims.");
                return;
            }
            switchView("myclaims");
        });
    }

    // -------------------------------------------------------------
    // 4d. Dashboard Metrics & Recent Claims Activity
    // -------------------------------------------------------------
    function updateDashboardStats(claims = []) {
        const statTotal = document.getElementById("dash-stat-total");
        const statReview = document.getElementById("dash-stat-review");
        const statConsistent = document.getElementById("dash-stat-consistent");
        const statPolicies = document.getElementById("dash-stat-policies");

        const total = claims.length;
        let reviewCount = 0;
        let consistentCount = 0;
        const uniquePolicies = new Set();

        claims.forEach((c) => {
            if (c.policy_number) uniquePolicies.add(c.policy_number);
            const st = (c.status || "").toUpperCase();
            if (st === "NEEDS_REVIEW" || st === "FLAGGED") {
                reviewCount++;
            } else {
                consistentCount++;
            }
        });

        if (statTotal) statTotal.textContent = total;
        if (statReview) statReview.textContent = reviewCount;
        if (statConsistent) {
            const pct = total > 0 ? Math.round((consistentCount / total) * 100) : 100;
            statConsistent.textContent = `${pct}%`;
        }
        if (statPolicies) statPolicies.textContent = uniquePolicies.size;

        const recentList = document.getElementById("dash-recent-claims-list");
        if (recentList) {
            if (claims.length === 0) {
                recentList.innerHTML = `
                    <div style="text-align: center; padding: 2rem 1rem; color: var(--text-muted);">
                        <p style="margin-bottom: 1rem;">No submitted claims registered under your account yet.</p>
                        <button type="button" class="btn btn-primary btn-sm" id="btn-dash-first-claim">Submit Your First Claim</button>
                    </div>
                `;
                const btn = document.getElementById("btn-dash-first-claim");
                if (btn) btn.addEventListener("click", () => switchView("submit"));
            } else {
                const recent = claims.slice(0, 4);
                recentList.innerHTML = recent
                    .map(
                        (c) => `
                    <div class="recent-claim-item">
                        <div class="recent-claim-meta">
                            <span class="recent-claim-id">${escapeHtml(c.claim_id || "CLM-000")}</span>
                            <span class="recent-claim-policy">${escapeHtml(c.claimant_name || "Claimant")} &bull; ${escapeHtml(c.policy_number || "-")}</span>
                        </div>
                        <div class="recent-claim-right">
                            <span class="status-badge ${c.status === "NEEDS_REVIEW" ? "badge-status-mismatch" : "badge-status-match"}">${escapeHtml(c.status || "PENDING")}</span>
                            <button type="button" class="btn btn-secondary btn-sm btn-dash-view" data-claim-id="${escapeHtml(c.claim_id)}">View</button>
                        </div>
                    </div>
                `
                    )
                    .join("");

                recentList.querySelectorAll(".btn-dash-view").forEach((b) => {
                    b.addEventListener("click", () => {
                        const cid = b.getAttribute("data-claim-id");
                        if (cid && typeof openClaimDetailsModal === "function") {
                            openClaimDetailsModal(cid);
                        }
                    });
                });
            }
        }
    }

    // -------------------------------------------------------------
    // 4e. 5-Step Guided Claim Submission Wizard
    // -------------------------------------------------------------
    let currentWizardStep = 1;

    function goToWizardStep(step) {
        if (step > currentWizardStep) {
            // Validation of preceding steps
            for (let s = currentWizardStep; s < step; s++) {
                if (s === 1) {
                    const claimantName = document.getElementById("claimant_name")?.value.trim();
                    const policyNumber = document.getElementById("policy_number")?.value.trim();
                    const vehicleNumber = document.getElementById("vehicle_number")?.value.trim();
                    const accidentDate = document.getElementById("accident_date")?.value.trim();
                    if (!claimantName || !policyNumber || !vehicleNumber || !accidentDate) {
                        showToast("Please fill in all required claimant and policy fields in Step 1.", "warning");
                        showError("Please fill out all required fields in Step 1.");
                        return;
                    }
                } else if (s === 2) {
                    const desc = document.getElementById("claim_description")?.value.trim();
                    if (!desc || desc.length < 10) {
                        showToast("Please provide an incident narrative (at least 10 characters).", "warning");
                        showError("Please provide an incident narrative in Step 2.");
                        return;
                    }
                } else if (s === 3) {
                    const files = [
                        { id: "policy_document", name: "Policy Schedule" },
                        { id: "claim_form_file", name: "Claim Form" },
                        { id: "invoice_document", name: "Invoice / Repair Estimate" },
                        { id: "vehicle_image", name: "Vehicle Photograph" },
                    ];
                    for (const f of files) {
                        const inp = document.getElementById(f.id);
                        if (!inp || !inp.files || inp.files.length === 0) {
                            showToast(`Missing required document: ${f.name}`, "warning");
                            showError(`Please upload all 4 required evidence documents in Step 3 (Missing: ${f.name}).`);
                            return;
                        }
                    }
                }
            }
        }

        clearError();
        currentWizardStep = step;

        // Step 4 review data population
        if (step === 4) {
            const claimantName = document.getElementById("claimant_name")?.value.trim() || "-";
            const policyNumber = document.getElementById("policy_number")?.value.trim() || "-";
            const vehicleNumber = document.getElementById("vehicle_number")?.value.trim() || "-";
            const accidentDate = document.getElementById("accident_date")?.value.trim() || "-";
            const incidentLocation = document.getElementById("incident_location")?.value.trim() || "Not specified";
            const claimDesc = document.getElementById("claim_description")?.value.trim() || "-";

            const setEl = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val;
            };
            setEl("rev-val-name", claimantName);
            setEl("rev-val-policy", policyNumber);
            setEl("rev-val-vehicle", vehicleNumber);
            setEl("rev-val-date", accidentDate);
            setEl("rev-val-location", incidentLocation);
            setEl("rev-val-narrative", claimDesc);

            const fileMap = [
                { id: "policy_document", label: "Policy Schedule", revId: "rev-file-policy", chkId: "rev-chk-policy" },
                { id: "claim_form_file", label: "Claim Form", revId: "rev-file-form", chkId: "rev-chk-form" },
                { id: "invoice_document", label: "Invoice / Estimate", revId: "rev-file-invoice", chkId: "rev-chk-invoice" },
                { id: "vehicle_image", label: "Accident Photo", revId: "rev-file-image", chkId: "rev-chk-image" },
            ];

            fileMap.forEach((f) => {
                const inp = document.getElementById(f.id);
                const revEl = document.getElementById(f.revId);
                const chkEl = document.getElementById(f.chkId);
                if (inp && inp.files && inp.files.length > 0) {
                    const file = inp.files[0];
                    if (revEl) revEl.textContent = `${f.label}: ${file.name} (${formatBytes(file.size)})`;
                    if (chkEl) chkEl.classList.add("file-ready");
                } else {
                    if (revEl) revEl.textContent = `${f.label}: Not selected`;
                    if (chkEl) chkEl.classList.remove("file-ready");
                }
            });
        }

        // Show/hide step panels
        for (let i = 1; i <= 4; i++) {
            const pane = document.getElementById(`wizard-step-${i}`);
            if (pane) {
                pane.style.display = i === step ? "block" : "none";
                if (i === step) pane.classList.add("active");
                else pane.classList.remove("active");
            }
        }

        // Stepper nodes active/completed
        for (let i = 1; i <= 4; i++) {
            const node = document.getElementById(`wizard-node-${i}`);
            if (node) {
                node.classList.remove("active", "completed");
                if (i === step) {
                    node.classList.add("active");
                } else if (i < step) {
                    node.classList.add("completed");
                }
            }
        }

        // Stepper connectors
        for (let i = 1; i <= 3; i++) {
            const conn = document.getElementById(`connector-${i}`);
            if (conn) {
                if (i < step) conn.classList.add("completed");
                else conn.classList.remove("completed");
            }
        }

        const submissionCard = document.getElementById("submission-card");
        if (submissionCard) submissionCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // Step navigation buttons
    const btnStep1Next = document.getElementById("btn-step1-next");
    if (btnStep1Next) btnStep1Next.addEventListener("click", () => goToWizardStep(2));

    const btnStep2Prev = document.getElementById("btn-step2-prev");
    if (btnStep2Prev) btnStep2Prev.addEventListener("click", () => goToWizardStep(1));
    const btnStep2Next = document.getElementById("btn-step2-next");
    if (btnStep2Next) btnStep2Next.addEventListener("click", () => goToWizardStep(3));

    const btnStep3Prev = document.getElementById("btn-step3-prev");
    if (btnStep3Prev) btnStep3Prev.addEventListener("click", () => goToWizardStep(2));
    const btnStep3Next = document.getElementById("btn-step3-next");
    if (btnStep3Next) btnStep3Next.addEventListener("click", () => goToWizardStep(4));

    const btnStep4Prev = document.getElementById("btn-step4-prev");
    if (btnStep4Prev) btnStep4Prev.addEventListener("click", () => goToWizardStep(3));

    // Stepper node clicks
    document.querySelectorAll(".wizard-step-node").forEach((node) => {
        node.addEventListener("click", () => {
            const targetStep = parseInt(node.getAttribute("data-step"), 10);
            if (!isNaN(targetStep)) goToWizardStep(targetStep);
        });
    });

    // Narrative Sample Fill Button
    const btnUseNarrativeSample = document.getElementById("btn-use-narrative-sample");
    if (btnUseNarrativeSample) {
        btnUseNarrativeSample.addEventListener("click", () => {
            const descInput = document.getElementById("claim_description");
            if (descInput) {
                descInput.value =
                    "While halting at an intersection signal on MG Road, vehicle was rear-ended by a commercial pickup truck. Damage observed on the rear bumper, trunk hatch, and right tail lamp assembly.";
                showToast("Sample accident narrative inserted.", "info");
            }
        });
    }

    // -------------------------------------------------------------
    // 4f. Drag & Drop Upload Cards
    // -------------------------------------------------------------
    function setupDropzoneCard(dropzoneId, inputId, badgeId) {
        const dropzone = document.getElementById(dropzoneId);
        const input = document.getElementById(inputId);
        const badge = document.getElementById(badgeId);
        if (!dropzone || !input) return;

        dropzone.addEventListener("click", (e) => {
            if (e.target === input) return;
            input.click();
        });

        ["dragenter", "dragover"].forEach((evtName) => {
            dropzone.addEventListener(evtName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add("dragover");
            });
        });

        ["dragleave", "drop"].forEach((evtName) => {
            dropzone.addEventListener(evtName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove("dragover");
            });
        });

        dropzone.addEventListener("drop", (e) => {
            if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                input.files = e.dataTransfer.files;
                input.dispatchEvent(new Event("change", { bubbles: true }));
                showToast(`Attached file: ${e.dataTransfer.files[0].name}`, "info");
            }
        });

        input.addEventListener("change", () => {
            if (input.files && input.files.length > 0) {
                dropzone.classList.add("has-file");
            } else {
                dropzone.classList.remove("has-file");
            }
            refreshFileBadges();
        });
    }

    setupDropzoneCard("dropzone-policy", "policy_document", "badge-policy_document");
    setupDropzoneCard("dropzone-form", "claim_form_file", "badge-claim_form_file");
    setupDropzoneCard("dropzone-invoice", "invoice_document", "badge-invoice_document");
    setupDropzoneCard("dropzone-image", "vehicle_image", "badge-vehicle_image");

    // -------------------------------------------------------------
    // 4g. Help Centre Tabs, FAQs & Search Filtering
    // -------------------------------------------------------------
    document.querySelectorAll(".help-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            const targetPaneId = `pane-help-${tab.getAttribute("data-help-tab")}`;
            document.querySelectorAll(".help-tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");

            document.querySelectorAll(".help-article-pane").forEach((p) => {
                p.style.display = p.id === targetPaneId ? "block" : "none";
                if (p.id === targetPaneId) p.classList.add("active");
                else p.classList.remove("active");
            });
        });
    });

    document.querySelectorAll(".faq-question").forEach((q) => {
        q.addEventListener("click", () => {
            const item = q.closest(".faq-item");
            if (item) item.classList.toggle("open");
        });
    });

    const helpSearchInput = document.getElementById("help-search-input");
    if (helpSearchInput) {
        helpSearchInput.addEventListener("input", (e) => {
            const query = e.target.value.trim().toLowerCase();
            if (!query) {
                document.querySelectorAll(".faq-item").forEach((item) => (item.style.display = ""));
                return;
            }
            document.querySelectorAll(".faq-item").forEach((item) => {
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(query) ? "block" : "none";
                if (text.includes(query)) item.classList.add("open");
            });
        });
    }

    // -------------------------------------------------------------
    // 4h. First-Time User Onboarding Walkthrough Tour
    // -------------------------------------------------------------
    let currentOnboardingStep = 1;
    const totalOnboardingSteps = 4;
    const onboardingModal = document.getElementById("onboarding-modal");
    const btnOnboardingNext = document.getElementById("btn-onboarding-next");
    const btnOnboardingPrev = document.getElementById("btn-onboarding-prev");
    const btnOnboardingSkip = document.getElementById("btn-onboarding-skip");
    const btnCloseOnboarding = document.getElementById("btn-close-onboarding");
    const onboardingStepTitle = document.getElementById("onboarding-step-title");
    const onboardingStepPill = document.getElementById("onboarding-step-pill");

    const onboardingTitles = [
        "Welcome to ClaimSense AI",
        "How to Submit a Claim Package",
        "Understanding AI Findings & Scores",
        "PDF Receipts & Comprehensive Reports",
    ];

    function showOnboardingSlide(step) {
        currentOnboardingStep = step;
        for (let i = 1; i <= totalOnboardingSteps; i++) {
            const slide = document.getElementById(`onboarding-slide-${i}`);
            if (slide) {
                slide.style.display = i === step ? "block" : "none";
            }
        }
        if (onboardingStepTitle) onboardingStepTitle.textContent = onboardingTitles[step - 1];
        if (onboardingStepPill) onboardingStepPill.textContent = `Step ${step} of ${totalOnboardingSteps}`;
        if (btnOnboardingPrev) btnOnboardingPrev.style.display = step > 1 ? "inline-block" : "none";
        if (btnOnboardingNext) {
            btnOnboardingNext.textContent = step === totalOnboardingSteps ? "Finish Tour ✓" : "Continue ➔";
        }
    }

    function openOnboardingTour() {
        if (!onboardingModal) return;
        showOnboardingSlide(1);
        onboardingModal.style.display = "flex";
    }

    function closeOnboardingTour() {
        if (!onboardingModal) return;
        onboardingModal.style.display = "none";
        localStorage.setItem("claimsense_onboarding_completed", "true");
    }

    if (btnOnboardingNext) {
        btnOnboardingNext.addEventListener("click", () => {
            if (currentOnboardingStep < totalOnboardingSteps) {
                showOnboardingSlide(currentOnboardingStep + 1);
            } else {
                closeOnboardingTour();
                showToast("Walkthrough completed! Welcome to ClaimSense AI.", "success");
            }
        });
    }

    if (btnOnboardingPrev) {
        btnOnboardingPrev.addEventListener("click", () => {
            if (currentOnboardingStep > 1) {
                showOnboardingSlide(currentOnboardingStep - 1);
            }
        });
    }

    if (btnOnboardingSkip) btnOnboardingSkip.addEventListener("click", closeOnboardingTour);
    if (btnCloseOnboarding) btnCloseOnboarding.addEventListener("click", closeOnboardingTour);

    // Auto-launch onboarding on first visit
    if (!localStorage.getItem("claimsense_onboarding_completed")) {
        setTimeout(openOnboardingTour, 1000);
    }
    applyTranslations();

    // -------------------------------------------------------------
    // 5. Selected Filenames Badges & Size Formatting
    // -------------------------------------------------------------
    // 5. Selected Filenames Badges & Size Formatting
    // -------------------------------------------------------------
    function setupFileBadge(inputId, badgeId) {
        const input = document.getElementById(inputId);
        const badge = document.getElementById(badgeId);
        if (!input || !badge) return;

        input.addEventListener("change", () => {
            if (input.files && input.files.length > 0) {
                const file = input.files[0];
                const nameSpan = badge.querySelector(".selected-filename");
                const sizeSpan = badge.querySelector(".selected-filesize");
                if (nameSpan) nameSpan.textContent = file.name;
                if (sizeSpan) sizeSpan.textContent = `(${formatBytes(file.size)})`;
                badge.style.display = "inline-flex";
            } else {
                badge.style.display = "none";
            }
        });
    }

    setupFileBadge("policy_document", "badge-policy_document");
    setupFileBadge("claim_form_file", "badge-claim_form_file");
    setupFileBadge("invoice_document", "badge-invoice_document");
    setupFileBadge("vehicle_image", "badge-vehicle_image");

    function refreshFileBadges() {
        const dropMap = {
            policy_document: "dropzone-policy",
            claim_form_file: "dropzone-form",
            invoice_document: "dropzone-invoice",
            vehicle_image: "dropzone-image",
        };

        ["policy_document", "claim_form_file", "invoice_document", "vehicle_image"].forEach((id) => {
            const input = document.getElementById(id);
            const badge = document.getElementById(`badge-${id}`);
            const dzId = dropMap[id];
            const dropzone = dzId ? document.getElementById(dzId) : null;

            if (input && badge && input.files && input.files.length > 0) {
                const file = input.files[0];
                const nameSpan = badge.querySelector(".selected-filename");
                const sizeSpan = badge.querySelector(".selected-filesize");
                if (nameSpan) nameSpan.textContent = file.name;
                if (sizeSpan) sizeSpan.textContent = `(${formatBytes(file.size)})`;
                badge.style.display = "inline-flex";
                if (dropzone) dropzone.classList.add("has-file");
            } else if (badge) {
                badge.style.display = "none";
                if (dropzone) dropzone.classList.remove("has-file");
            }
        });
    }

    // -------------------------------------------------------------
    // 6. Section 1: Submit Claim Evidence
    // -------------------------------------------------------------
    const claimForm = document.getElementById("claim-form");
    const btnSubmitClaim = document.getElementById("btn-submit-claim");
    const errorAlert = document.getElementById("form-error-alert") || document.getElementById("error-alert");
    const errorMessage = document.getElementById("error-message");

    const resClaimId = document.getElementById("res-claim-id");
    const resClaimantName = document.getElementById("res-claimant-name");
    const resPolicyNumber = document.getElementById("res-policy-number");
    const resVehicleNumber = document.getElementById("res-vehicle-number");
    const resAccidentDate = document.getElementById("res-accident-date");
    const resIncidentLocation = document.getElementById("res-incident-location");
    const resClaimDescription = document.getElementById("res-claim-description");
    const resFileCount = document.getElementById("res-file-count");
    const resTimestamp = document.getElementById("res-timestamp");
    const btnDownloadReceipt = document.getElementById("btn-download-receipt");
    const btnDownloadDocumentReport = document.getElementById("btn-download-document-report");
    const btnViewClaimModal = document.getElementById("btn-view-claim-modal");

    const btnNewClaim = document.getElementById("btn-new-claim");
    const btnCopyClaimId = document.getElementById("btn-copy-claim-id");
    const btnFillSample = document.getElementById("btn-fill-sample");

    function showError(msg) {
        if (!errorAlert) return;
        if (errorMessage) {
            errorMessage.textContent = msg;
        } else {
            errorAlert.textContent = msg;
        }
        errorAlert.style.display = "block";
        errorAlert.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function clearError() {
        if (!errorAlert) return;
        if (errorMessage) errorMessage.textContent = "";
        errorAlert.textContent = "";
        errorAlert.style.display = "none";
    }

    function setSubmittingState(isSubmitting) {
        if (!btnSubmitClaim) return;
        btnSubmitClaim.disabled = isSubmitting;
        const btnText = btnSubmitClaim.querySelector(".btn-text");
        const btnSpinner = btnSubmitClaim.querySelector(".btn-spinner");
        if (btnText && btnSpinner) {
            btnText.style.display = isSubmitting ? "none" : "inline";
            btnSpinner.style.display = isSubmitting ? "inline-flex" : "none";
        }
    }

    if (claimForm) {
        claimForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            clearError();

            // Client-side authentication check
            if (!currentUser) {
                showError("Authentication required: Please sign in or create an account before submitting claim evidence.");
                openAuthModal("login");
                return;
            }

            const chkConfirm = document.getElementById("chk-confirm-submission");
            if (chkConfirm && !chkConfirm.checked) {
                showError("Please check the confirmation box acknowledging the authenticity of your claim submission.");
                showToast("Declaration confirmation required before submission.", "warning");
                return;
            }

            const formData = new FormData(claimForm);
            const claimantName = formData.get("claimant_name")?.trim();
            const policyNumber = formData.get("policy_number")?.trim();
            const vehicleNumber = formData.get("vehicle_number")?.trim();
            const accidentDate = formData.get("accident_date")?.trim();
            const claimDesc = formData.get("claim_description")?.trim();

            if (!claimantName || !policyNumber || !vehicleNumber || !accidentDate || !claimDesc) {
                showError("Please fill out all required text fields.");
                return;
            }

            const requiredFiles = [
                { id: "policy_document", label: "Policy Document" },
                { id: "claim_form_file", label: "Claim Form" },
                { id: "invoice_document", label: "Invoice / Repair Estimate" },
                { id: "vehicle_image", label: "Accident / Vehicle Image" },
            ];

            for (const rf of requiredFiles) {
                const el = document.getElementById(rf.id);
                if (!el || !el.files || el.files.length === 0) {
                    showError(`Missing required file: ${rf.label}`);
                    return;
                }
            }

            setSubmittingState(true);

            let token = getCsrfToken();
            if (!token) token = await fetchCsrfToken();
            if (token) {
                syncCsrfInputs(token);
                formData.set("csrf_token", token);
            }

            const headers = {};
            if (token) {
                headers["X-CSRFToken"] = token;
                headers["X-CSRF-Token"] = token;
            }

            try {
                const response = await fetch("/api/claims?async=true", {
                    method: "POST",
                    credentials: "same-origin",
                    headers,
                    body: formData,
                });

                const result = await response.json();

                if (!response.ok) {
                    let errMsg = result.message || "Failed to submit claim.";
                    if (result.details && Array.isArray(result.details)) {
                        errMsg += ` (${result.details.join("; ")})`;
                    }
                    throw new Error(errMsg);
                }

                // Populate success summary
                if (resClaimId) resClaimId.textContent = result.claim_id;
                if (resClaimantName) resClaimantName.textContent = result.data.claimant_name || "-";
                if (resPolicyNumber) resPolicyNumber.textContent = result.data.policy_number || "-";
                if (resVehicleNumber) resVehicleNumber.textContent = result.data.vehicle_number || "-";
                if (resAccidentDate) resAccidentDate.textContent = result.data.accident_date || "-";
                if (resIncidentLocation) {
                    resIncidentLocation.textContent = result.data.incident_location || "Not specified";
                }
                if (resClaimDescription) resClaimDescription.textContent = result.data.claim_description || "-";
                if (resFileCount) resFileCount.textContent = `${result.data.files_count || 4} evidence files safely saved`;
                if (resTimestamp) resTimestamp.textContent = new Date(result.data.created_at).toLocaleString();

                // Download buttons
                if (btnDownloadReceipt) {
                    btnDownloadReceipt.href = `/api/claims/${result.claim_id}/receipt`;
                }
                if (btnDownloadDocumentReport) {
                    btnDownloadDocumentReport.href = `/api/claims/${result.claim_id}/document-report`;
                }
                currentActiveClaimId = result.claim_id;

                // Reset replacement photo box status
                const replaceStatus = document.getElementById("replace-image-status");
                if (replaceStatus) {
                    replaceStatus.style.display = "none";
                    replaceStatus.textContent = "";
                }

                // Switch views within Section 1
                if (submissionCard) submissionCard.style.display = "none";
                if (successCard) {
                    successCard.style.display = "block";
                    successCard.scrollIntoView({ behavior: "smooth" });
                }

                // Phase 12 Asynchronous Polling Integration
                const isAsync = (response.status === 202) || (result.status === "queued") || Boolean(result.task_id);
                if (isAsync) {
                    showToast("Claim accepted! Background multi-stage AI verification running.", "info");
                    startAsyncPipelinePolling(result.claim_id, result.task_id);
                } else {
                    showToast("Claim successfully registered and verified!", "success");
                }
                if (typeof loadMyClaims === "function") loadMyClaims();

            } catch (err) {
                showError(`Submission rejected: ${err.message}`);
            } finally {
                setSubmittingState(false);
            }
        });
    }

    let asyncPollingInterval = null;

    function startAsyncPipelinePolling(claimId, taskId) {
        if (asyncPollingInterval) {
            clearInterval(asyncPollingInterval);
            asyncPollingInterval = null;
        }

        const widget = document.getElementById("async-pipeline-status-card");
        const titleEl = document.getElementById("async-pipeline-title");
        const badgeEl = document.getElementById("async-pipeline-badge");
        const barEl = document.getElementById("async-progress-bar");
        const metaEl = document.getElementById("async-pipeline-meta");
        const spinner = document.getElementById("async-spinner");

        const stageMap = {
            "INTAKE": "stage-intake",
            "OCR_PROCESSING": "stage-ocr",
            "DAMAGE_ANALYSIS": "stage-damage",
            "NLP_CHRONOLOGY": "stage-nlp",
            "CROSS_SOURCE_VERIFICATION": "stage-verif",
            "REPORT_PERSISTENCE": "stage-verif",
            "COMPLETED": "stage-verif",
        };

        const stageOrder = [
            "INTAKE",
            "OCR_PROCESSING",
            "DAMAGE_ANALYSIS",
            "NLP_CHRONOLOGY",
            "CROSS_SOURCE_VERIFICATION",
        ];

        if (widget) widget.style.display = "block";
        if (spinner) spinner.style.display = "inline-block";
        if (titleEl) {
            titleEl.textContent = "AI Verification Pipeline: In Progress...";
            titleEl.style.color = "#e2e8f0";
        }
        if (barEl) {
            barEl.style.width = "10%";
            barEl.style.background = "linear-gradient(90deg, #6366f1, #38bdf8)";
        }

        function updateStageHighlight(currentStage) {
            const curIdx = stageOrder.indexOf(currentStage);
            stageOrder.forEach((stg, idx) => {
                const elId = stageMap[stg];
                const el = document.getElementById(elId);
                if (!el) return;
                if (idx < curIdx || currentStage === "COMPLETED") {
                    el.style.background = "rgba(34, 197, 94, 0.2)";
                    el.style.color = "#86efac";
                    el.style.fontWeight = "600";
                } else if (idx === curIdx) {
                    el.style.background = "rgba(99, 102, 241, 0.35)";
                    el.style.color = "#c7d2fe";
                    el.style.fontWeight = "700";
                } else {
                    el.style.background = "transparent";
                    el.style.color = "#94a3b8";
                    el.style.fontWeight = "400";
                }
            });
        }

        async function pollStatus() {
            try {
                const res = await fetch(`/api/claims/${claimId}/status`);
                if (!res.ok) return;
                const data = await res.json();
                if (!data || !data.success) return;

                const status = (data.status || "queued").toLowerCase();
                const stage = data.stage || "INTAKE";
                const progress = data.progress_percent || 10;

                if (barEl) barEl.style.width = `${progress}%`;
                if (badgeEl) {
                    badgeEl.textContent = `${stage.replace(/_/g, " ")} (${progress}%)`;
                }

                updateStageHighlight(stage);

                if (metaEl) {
                    metaEl.textContent = `Task: ${data.task_id || taskId || "active"} | Broker: Active`;
                }

                if (status === "completed") {
                    clearInterval(asyncPollingInterval);
                    asyncPollingInterval = null;
                    if (barEl) {
                        barEl.style.width = "100%";
                        barEl.style.background = "#22c55e";
                    }
                    if (titleEl) {
                        titleEl.textContent = "AI Multi-Source Verification Completed ✓";
                        titleEl.style.color = "#86efac";
                    }
                    if (spinner) spinner.style.display = "none";
                    if (badgeEl) {
                        badgeEl.textContent = "COMPLETED (100%)";
                        badgeEl.style.background = "rgba(34, 197, 94, 0.2)";
                        badgeEl.style.color = "#86efac";
                        badgeEl.style.border = "1px solid rgba(34, 197, 94, 0.4)";
                    }
                    updateStageHighlight("COMPLETED");
                    showToast("AI Verification & Claim Report Ready!", "success");
                    if (typeof loadMyClaims === "function") loadMyClaims();
                } else if (status === "failed") {
                    clearInterval(asyncPollingInterval);
                    asyncPollingInterval = null;
                    if (titleEl) {
                        titleEl.textContent = "Processing Pipeline Alert";
                        titleEl.style.color = "#f87171";
                    }
                    if (spinner) spinner.style.display = "none";
                    if (badgeEl) {
                        badgeEl.textContent = "FAILED";
                        badgeEl.style.background = "rgba(239, 68, 68, 0.2)";
                        badgeEl.style.color = "#fca5a5";
                    }
                    showToast(`Pipeline paused: ${data.error_message || "Processing exception"}`, "error");
                }
            } catch (err) {
                console.warn("Async polling transient check:", err);
            }
        }

        pollStatus();
        asyncPollingInterval = setInterval(pollStatus, 1500);
    }

    if (btnViewClaimModal) {
        btnViewClaimModal.addEventListener("click", () => {
            if (currentActiveClaimId && typeof openClaimDetailsModal === "function") {
                openClaimDetailsModal(currentActiveClaimId);
            }
        });
    }

    function resetClaimSubmissionForm() {
        // 1. Abort any running polling intervals
        if (asyncPollingInterval) {
            clearInterval(asyncPollingInterval);
            asyncPollingInterval = null;
        }
        currentActiveClaimId = null;

        // 2. Reset the native HTML form
        if (claimForm) {
            claimForm.reset();
        }

        // 3. Explicitly wipe form field values (in case form.reset() missed dynamically populated inputs)
        const fieldIds = [
            "claimant_name",
            "policy_number",
            "vehicle_number",
            "accident_date",
            "incident_location",
            "claim_description",
            "policy_document",
            "claim_form_file",
            "invoice_document",
            "vehicle_image"
        ];
        fieldIds.forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = "";
        });

        // 4. Reset checkboxes
        const chkConfirm = document.getElementById("chk-confirm-submission");
        if (chkConfirm) chkConfirm.checked = false;

        // 5. Clear dropzone styling and file badges
        refreshFileBadges();
        ["dropzone-policy", "dropzone-form", "dropzone-invoice", "dropzone-image"].forEach((dzId) => {
            const dz = document.getElementById(dzId);
            if (dz) dz.classList.remove("has-file");
        });

        // 6. Reset review step (Step 4) UI elements
        const setEl = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setEl("rev-val-name", "-");
        setEl("rev-val-policy", "-");
        setEl("rev-val-vehicle", "-");
        setEl("rev-val-date", "-");
        setEl("rev-val-location", "-");
        setEl("rev-val-narrative", "-");

        const reviewFiles = [
            { revId: "rev-file-policy", chkId: "rev-chk-policy", label: "Policy Schedule" },
            { revId: "rev-file-form", chkId: "rev-chk-form", label: "Claim Form" },
            { revId: "rev-file-invoice", chkId: "rev-chk-invoice", label: "Invoice / Estimate" },
            { revId: "rev-file-image", chkId: "rev-chk-image", label: "Accident Photo" }
        ];
        reviewFiles.forEach((rf) => {
            setEl(rf.revId, `${rf.label}: Not selected`);
            const chkEl = document.getElementById(rf.chkId);
            if (chkEl) chkEl.classList.remove("file-ready");
        });

        // 7. Reset results & async pipeline progress card
        if (successCard) successCard.style.display = "none";
        const asyncCard = document.getElementById("async-pipeline-status-card");
        if (asyncCard) asyncCard.style.display = "none";

        const pBar = document.getElementById("async-progress-bar");
        if (pBar) {
            pBar.style.width = "0%";
            pBar.className = "progress-bar-fill progress-idle";
        }
        const oBadge = document.getElementById("async-overall-status-badge");
        if (oBadge) {
            oBadge.textContent = "IDLE";
            oBadge.className = "status-badge status-idle";
        }
        const pPercent = document.getElementById("async-progress-percentage");
        if (pPercent) pPercent.textContent = "0%";

        const stageList = ["intake", "ocr", "cardd", "nlp", "verification"];
        stageList.forEach((s) => {
            const item = document.getElementById(`pipeline-stage-${s}`);
            if (item) item.className = "pipeline-stage-item stage-pending";
            const val = document.getElementById(`stage-val-${s}`);
            if (val) val.textContent = "pending";
        });

        clearError();

        // 8. Restore intake view to Step 1
        if (submissionCard) {
            submissionCard.style.display = "block";
        }
        currentWizardStep = 1;
        if (typeof goToWizardStep === "function") {
            goToWizardStep(1);
        }
        if (submissionCard) {
            submissionCard.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    if (btnNewClaim) {
        btnNewClaim.addEventListener("click", () => {
            resetClaimSubmissionForm();
        });
    }

    if (btnCopyClaimId) {
        btnCopyClaimId.addEventListener("click", async () => {
            const cid = resClaimId ? resClaimId.textContent : "";
            if (!cid) return;
            try {
                await navigator.clipboard.writeText(cid);
                const originalText = btnCopyClaimId.textContent;
                btnCopyClaimId.textContent = "Copied! ✓";
                setTimeout(() => {
                    btnCopyClaimId.textContent = originalText;
                }, 2000);
            } catch {
                alert(`Claim ID: ${cid}`);
            }
        });
    }

    // Replacement Vehicle Photograph Upload
    const formReplaceImage = document.getElementById("form-replace-image");
    const inputReplaceImage = document.getElementById("input-replace-image");
    const replaceImageStatus = document.getElementById("replace-image-status");
    const btnSubmitReplaceImage = document.getElementById("btn-submit-replace-image");

    if (formReplaceImage) {
        formReplaceImage.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (!currentActiveClaimId) {
                alert("No active claim identifier found.");
                return;
            }
            if (!inputReplaceImage || !inputReplaceImage.files || inputReplaceImage.files.length === 0) {
                alert("Please select a JPEG or PNG vehicle photograph to upload.");
                return;
            }

            const formData = new FormData();
            formData.append("vehicle_image", inputReplaceImage.files[0]);

            let token = getCsrfToken();
            if (!token) token = await fetchCsrfToken();
            if (token) {
                syncCsrfInputs(token);
                formData.set("csrf_token", token);
            }

            const headers = {};
            if (token) {
                headers["X-CSRFToken"] = token;
                headers["X-CSRF-Token"] = token;
            }

            if (btnSubmitReplaceImage) btnSubmitReplaceImage.disabled = true;
            if (replaceImageStatus) {
                replaceImageStatus.style.display = "block";
                replaceImageStatus.className = "alert alert-info mt-2";
                replaceImageStatus.textContent = "Uploading and validating replacement photograph...";
            }

            try {
                const repRes = await safeFetchJson(`/api/claims/${currentActiveClaimId}/replace-image`, {
                    method: "POST",
                    body: formData,
                });

                if (!repRes.ok || !repRes.data || !repRes.data.success) {
                    const errMsg = repRes.error || (repRes.data && repRes.data.message) || "Failed to replace vehicle photograph.";
                    if (replaceImageStatus) {
                        replaceImageStatus.className = "alert alert-error mt-2";
                        replaceImageStatus.textContent = `⚠ ${errMsg}`;
                    }
                    return;
                }

                const data = repRes.data;
                if (replaceImageStatus) {
                    if (data.validation && data.validation.is_valid_vehicle_photo) {
                        replaceImageStatus.className = "alert alert-success mt-2";
                        replaceImageStatus.textContent = `✓ Replacement photograph verified as authentic vehicle damage photograph! (${data.validation.resolution || ""})`;
                    } else {
                        replaceImageStatus.className = "alert alert-error mt-2";
                        replaceImageStatus.textContent = `⚠ Uploaded replacement image flagged: ${data.validation ? data.validation.reason : "Invalid photograph format"}`;
                    }
                }
            } catch (err) {
                if (replaceImageStatus) {
                    replaceImageStatus.className = "alert alert-error mt-2";
                    replaceImageStatus.textContent = `Error: ${err.message}`;
                }
            } finally {
                if (btnSubmitReplaceImage) btnSubmitReplaceImage.disabled = false;
            }
        });
    }

    // Fill Sample Demo Data
    if (btnFillSample) {
        btnFillSample.addEventListener("click", () => {
            const elName = document.getElementById("claimant_name");
            const elPolicy = document.getElementById("policy_number");
            const elVehicle = document.getElementById("vehicle_number");
            const elDate = document.getElementById("accident_date");
            const elDesc = document.getElementById("claim_description");
            const locInput = document.getElementById("incident_location");

            if (elName) elName.value = "Rajesh Sharma";
            if (elPolicy) elPolicy.value = "POL-2024-88391";
            if (elVehicle) elVehicle.value = "MH-12-DE-4052";
            if (elDate) elDate.value = "2026-09-28";
            if (locInput) locInput.value = "MG Road, Pune, Maharashtra";
            if (elDesc) {
                elDesc.value = "While halting at an intersection signal on MG Road, vehicle was rear-ended by a commercial pickup truck. Damage observed on the rear bumper, trunk hatch, and right tail lamp assembly.";
            }

            const escapePdfText = (text) => text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");

            const createSyntheticPdfFile = (name, lines) => {
                const content = lines.map((line, index) => `BT /F1 12 Tf 50 ${760 - index * 20} Td (${escapePdfText(line)}) Tj ET`).join("\n");
                const objects = [
                    "<< /Type /Catalog /Pages 2 0 R >>",
                    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
                    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
                    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`
                ];

                let pdf = "%PDF-1.4\n";
                const offsets = [0];
                for (let i = 0; i < objects.length; i += 1) {
                    offsets.push(pdf.length);
                    pdf += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`;
                }
                const xrefStart = pdf.length;
                pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
                for (let i = 1; i <= objects.length; i += 1) {
                    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
                }
                pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;

                return new File([new Blob([pdf], { type: "application/pdf" })], name, { type: "application/pdf" });
            };

            const createSyntheticImageFile = (name) => {
                const canvas = document.createElement("canvas");
                canvas.width = 900;
                canvas.height = 600;
                const ctx = canvas.getContext("2d");
                ctx.fillStyle = "#f8fafc";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = "#1d4ed8";
                ctx.fillRect(60, 70, 220, 80);
                ctx.fillStyle = "#ffffff";
                ctx.font = "bold 34px sans-serif";
                ctx.fillText("Rear Bumper", 90, 120);
                ctx.font = "28px sans-serif";
                ctx.fillStyle = "#0f172a";
                ctx.fillText("Policy POL-2024-88391", 60, 240);
                ctx.fillText("Vehicle MH-12-DE-4052", 60, 285);
                ctx.fillText("Accident 2026-09-28", 60, 330);
                const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
                const base64 = dataUrl.split(",")[1];
                const binary = atob(base64);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i += 1) {
                    bytes[i] = binary.charCodeAt(i);
                }
                return new File([bytes], name, { type: "image/jpeg" });
            };

            const setFileInput = (id, file) => {
                const input = document.getElementById(id);
                if (input) {
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    input.files = dt.files;
                }
            };

            setFileInput("policy_document", createSyntheticPdfFile("policy_schedule_88391.pdf", ["CLAIMSENSE AI", "Policy Number: POL-2024-88391", "Vehicle Registration: MH-12-DE-4052", "Accident Date: 2026-09-28"]));
            setFileInput("claim_form_file", createSyntheticPdfFile("signed_claim_form.pdf", ["Claimant: Rajesh Sharma", "Policy Number: POL-2024-88391", "Claim Description: Rear-end collision at MG Road intersection.", "Accident Date: 2026-09-28"]));
            setFileInput("invoice_document", createSyntheticPdfFile("garage_estimate_4052.pdf", ["Garage Estimate", "Claim Amount: INR 84500", "Bodywork and paint: 38500", "Tail lamp replacement: 16000", "Labor and miscellaneous: 30000"]));
            setFileInput("vehicle_image", createSyntheticImageFile("rear_bumper_damage.jpg"));

            refreshFileBadges();
            clearError();
            showToast("Sample demo claim data and synthetic files loaded.", "success");
        });
    }

    // -------------------------------------------------------------
    // 7. Shared Claim Card HTML Renderer
    // -------------------------------------------------------------
    function renderClaimCard(claim) {
        const dateStr = claim.created_at ? new Date(claim.created_at).toLocaleDateString() : "-";
        const filesCount = claim.files_count || (claim.documents ? claim.documents.length + (claim.images ? claim.images.length : 0) : 4);
        const locationBadge = `
            <div class="meta-item wide">
                <span class="meta-label">Incident Location</span>
                <span class="meta-val">${claim.incident_location ? escapeHtml(claim.incident_location) : '<span style="color: var(--text-muted); font-weight: normal;">Not specified</span>'}</span>
            </div>`;

        return `
            <div class="claim-result-card" data-claim-id="${escapeHtml(claim.claim_id)}">
                <div class="result-card-header">
                    <div class="claim-id-group">
                        <span class="claim-id-badge">${escapeHtml(claim.claim_id)}</span>
                        <button type="button" class="btn-copy-card-id" data-id="${escapeHtml(claim.claim_id)}" title="Copy Claim ID">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                        </button>
                    </div>
                    <span class="status-pill status-ready">
                        <span class="status-dot"></span>
                        ${escapeHtml(claim.status || "SUBMITTED")}
                    </span>
                </div>
                <div class="result-details-grid">
                    <div class="meta-item">
                        <span class="meta-label">Claimant</span>
                        <span class="meta-val">${escapeHtml(claim.claimant_name || "-")}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Policy Number</span>
                        <span class="meta-val monospace-val">${escapeHtml(claim.policy_number || "-")}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Vehicle Registration #</span>
                        <span class="meta-val monospace-val">${escapeHtml(claim.vehicle_number || "-")}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Accident Date</span>
                        <span class="meta-val">${escapeHtml(claim.accident_date || "-")}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Submitted On</span>
                        <span class="meta-val">${escapeHtml(dateStr)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Evidence Files</span>
                        <span class="meta-val">${filesCount} files attached</span>
                    </div>
                    ${locationBadge}
                </div>
                <div class="result-card-footer">
                    <div class="action-buttons-group">
                        <button type="button" class="btn btn-secondary btn-sm btn-action-details" data-claim-id="${escapeHtml(claim.claim_id)}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                            <span>View Details</span>
                        </button>
                        <button type="button" class="btn btn-secondary btn-sm btn-action-evidence" data-claim-id="${escapeHtml(claim.claim_id)}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                            <span>View Evidence</span>
                        </button>
                    </div>
                    <div class="download-buttons-group">
                        <a href="/api/claims/${escapeHtml(claim.claim_id)}/receipt" target="_blank" class="btn btn-outline btn-sm">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                            <span>Receipt</span>
                        </a>
                        <a href="/api/claims/${escapeHtml(claim.claim_id)}/document-report" target="_blank" class="btn btn-primary btn-sm">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
                            <span>Report</span>
                        </a>
                    </div>
                </div>
            </div>
        `;
    }

    function attachCardActionListeners(container) {
        if (!container) return;
        container.querySelectorAll(".btn-action-details").forEach((btn) => {
            btn.addEventListener("click", () => {
                const claimId = btn.getAttribute("data-claim-id");
                if (claimId) openClaimDetailsModal(claimId);
            });
        });
        container.querySelectorAll(".btn-action-evidence").forEach((btn) => {
            btn.addEventListener("click", () => {
                const claimId = btn.getAttribute("data-claim-id");
                if (claimId) openClaimEvidenceModal(claimId);
            });
        });
        container.querySelectorAll(".btn-copy-card-id").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const cid = btn.getAttribute("data-id");
                if (!cid) return;
                try {
                    await navigator.clipboard.writeText(cid);
                    btn.style.color = "var(--success)";
                    setTimeout(() => { btn.style.color = ""; }, 1500);
                } catch {
                    alert(`Claim ID: ${cid}`);
                }
            });
        });
    }

    // -------------------------------------------------------------
    // 8. Section 2: Policy & Claim ID Lookup
    // -------------------------------------------------------------
    const policySearchForm = document.getElementById("policy-search-form");
    const searchPolicyInput = document.getElementById("search-policy-input");
    const policySearchAlert = document.getElementById("policy-search-alert");
    const policySearchResults = document.getElementById("policy-search-results");
    const policyResultsList = document.getElementById("policy-results-list");
    const resultsCount = document.getElementById("results-count");
    const lookupInitialState = document.getElementById("lookup-initial-state");
    const btnClearLookup = document.getElementById("btn-clear-lookup");

    if (btnClearLookup) {
        btnClearLookup.addEventListener("click", () => {
            if (searchPolicyInput) searchPolicyInput.value = "";
            if (policySearchAlert) policySearchAlert.style.display = "none";
            if (policySearchResults) policySearchResults.style.display = "none";
            if (lookupInitialState) lookupInitialState.style.display = "block";
            btnClearLookup.style.display = "none";
        });
    }

    if (policySearchForm) {
        policySearchForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (!searchPolicyInput) return;
            const query = searchPolicyInput.value.trim();
            if (!query) return;

            if (policySearchAlert) policySearchAlert.style.display = "none";
            if (policySearchResults) policySearchResults.style.display = "none";
            if (policyResultsList) policyResultsList.innerHTML = "";
            if (lookupInitialState) lookupInitialState.style.display = "none";
            if (btnClearLookup) btnClearLookup.style.display = "inline-flex";

            // Determine search mode: auto, claim_id, or policy
            const modeRadio = document.querySelector('input[name="search-mode"]:checked');
            const mode = modeRadio ? modeRadio.value : "auto";

            const isClaimIdPattern = /^CLM-\d{8}-[A-Za-z0-9]{4}$/i.test(query) || query.toUpperCase().startsWith("CLM-");
            const searchByClaimId = mode === "claim_id" || (mode === "auto" && isClaimIdPattern);

            if (searchByClaimId) {
                // Search by Claim ID
                try {
                    const res = await fetch(`/api/claims/${encodeURIComponent(query)}`);
                    const data = await res.json();

                    if (!res.ok || !data.success) {
                        if (res.status === 401) {
                            openAuthModal("login");
                            showAuthAlert("Authentication required to view this claim.");
                            return;
                        }
                        if (res.status === 403) {
                            showLookupError("Access Restricted: You are not authorized to view claim records belonging to another policyholder.");
                            return;
                        }
                        showLookupError(data.message || `No claim record found matching identifier '${query}'.`);
                        return;
                    }

                    const claim = data.data;
                    if (resultsCount) resultsCount.textContent = "1";
                    if (policyResultsList) {
                        policyResultsList.innerHTML = renderClaimCard(claim);
                        attachCardActionListeners(policyResultsList);
                    }
                    if (policySearchResults) policySearchResults.style.display = "block";

                } catch (err) {
                    showLookupError(`Lookup request failed: ${err.message}`);
                }
            } else {
                // Search by Policy Number
                if (!currentUser) {
                    openAuthModal("login");
                    showAuthAlert("Authentication required to search claims by policy number.");
                    return;
                }

                try {
                    const res = await fetch(`/api/claims/policy/${encodeURIComponent(query)}`);
                    const data = await res.json();

                    if (!res.ok || !data.success) {
                        if (res.status === 401) {
                            openAuthModal("login");
                            showAuthAlert("Authentication required to search claims.");
                            return;
                        }
                        showLookupError(data.message || `No claims found for policy '${query}' under your account.`);
                        return;
                    }

                    if (resultsCount) resultsCount.textContent = data.count || data.claims.length;
                    if (policyResultsList) {
                        policyResultsList.innerHTML = data.claims
                            .map((claim) => renderClaimCard(claim))
                            .join("");
                        attachCardActionListeners(policyResultsList);
                    }
                    if (policySearchResults) policySearchResults.style.display = "block";

                } catch (err) {
                    showLookupError(`Search failed: ${err.message}`);
                }
            }
        });
    }

    function showLookupError(msg) {
        if (!policySearchAlert) return;
        policySearchAlert.textContent = msg;
        policySearchAlert.style.display = "block";
    }

    // -------------------------------------------------------------
    // 9. Section 3: My Submissions
    // -------------------------------------------------------------
    const myClaimsList = document.getElementById("my-claims-list");
    const myClaimsAlert = document.getElementById("my-claims-alert");
    const btnRefreshMyClaims = document.getElementById("btn-refresh-my-claims");
    const myClaimsFilterInput = document.getElementById("myclaims-filter-input");
    const myClaimsSortSelect = document.getElementById("myclaims-sort-select");
    const myClaimsCountDisplay = document.getElementById("myclaims-count-display");

    async function loadMyClaims() {
        if (!myClaimsList) return;
        if (!currentUser) {
            myClaimsList.innerHTML = `
                <div class="empty-state-card">
                    <div class="empty-state-icon-wrapper">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                    </div>
                    <h3>Authentication Required</h3>
                    <p>Please sign in to view and manage claims submitted under your account profile.</p>
                    <button type="button" class="btn btn-primary" id="btn-submissions-login">Sign In / Register</button>
                </div>
            `;
            const loginBtn = document.getElementById("btn-submissions-login");
            if (loginBtn) loginBtn.addEventListener("click", () => openAuthModal("login"));
            if (myClaimsCountDisplay) myClaimsCountDisplay.textContent = "0 Submissions";
            return;
        }

        myClaimsList.innerHTML = `
            <div class="empty-state-card">
                <div class="empty-state-icon-wrapper">
                    <span class="spinner-circle" style="width: 24px; height: 24px; border-width: 3px; margin: 0;"></span>
                </div>
                <h3>Loading Submissions...</h3>
                <p>Retrieving your secured claim submissions...</p>
            </div>
        `;
        if (myClaimsAlert) myClaimsAlert.style.display = "none";

        try {
            const res = await fetch("/api/my-claims");
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.message || "Failed to load claim history.");
            }

            mySubmissionsData = data.claims || [];
            applySubmissionsFilterAndSort();
            updateDashboardStats(mySubmissionsData);

        } catch (err) {
            if (myClaimsAlert) {
                myClaimsAlert.textContent = `Error loading claims: ${err.message}`;
                myClaimsAlert.style.display = "block";
            }
            myClaimsList.innerHTML = `<p class="empty-state">Could not fetch submissions.</p>`;
        }
    }

    function applySubmissionsFilterAndSort() {
        if (!myClaimsList) return;

        const filterQuery = (myClaimsFilterInput ? myClaimsFilterInput.value : "").trim().toLowerCase();
        const sortOrder = myClaimsSortSelect ? myClaimsSortSelect.value : "newest";

        let filtered = [...mySubmissionsData];

        // Filter
        if (filterQuery) {
            filtered = filtered.filter((c) => {
                const cid = (c.claim_id || "").toLowerCase();
                const pol = (c.policy_number || "").toLowerCase();
                const name = (c.claimant_name || "").toLowerCase();
                const veh = (c.vehicle_number || "").toLowerCase();
                const desc = (c.claim_description || "").toLowerCase();
                const loc = (c.incident_location || "").toLowerCase();
                return cid.includes(filterQuery) ||
                       pol.includes(filterQuery) ||
                       name.includes(filterQuery) ||
                       veh.includes(filterQuery) ||
                       desc.includes(filterQuery) ||
                       loc.includes(filterQuery);
            });
        }

        // Sort
        filtered.sort((a, b) => {
            const timeA = new Date(a.created_at || 0).getTime();
            const timeB = new Date(b.created_at || 0).getTime();
            return sortOrder === "oldest" ? timeA - timeB : timeB - timeA;
        });

        if (myClaimsCountDisplay) {
            myClaimsCountDisplay.textContent = `${filtered.length} of ${mySubmissionsData.length} Submissions`;
        }

        if (filtered.length === 0) {
            if (mySubmissionsData.length === 0) {
                myClaimsList.innerHTML = `
                    <div class="empty-state-card">
                        <div class="empty-state-icon-wrapper">
                            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                        </div>
                        <h3>No Claims Submitted Yet</h3>
                        <p>You haven't submitted any insurance claims under this account. Click below to submit your first claim evidence.</p>
                        <button type="button" class="btn btn-primary" id="btn-submit-first-claim">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                            <span>Submit Claim Evidence</span>
                        </button>
                    </div>
                `;
                const firstBtn = document.getElementById("btn-submit-first-claim");
                if (firstBtn) firstBtn.addEventListener("click", () => switchView("submit"));
            } else {
                myClaimsList.innerHTML = `
                    <div class="empty-state-card">
                        <div class="empty-state-icon-wrapper">
                            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        </div>
                        <h3>No Matching Submissions</h3>
                        <p>No claims match your filter query "<strong>${escapeHtml(filterQuery)}</strong>". Try clearing your search.</p>
                    </div>
                `;
            }
            return;
        }

        myClaimsList.innerHTML = filtered
            .map((claim) => renderClaimCard(claim))
            .join("");
        attachCardActionListeners(myClaimsList);
    }

    if (btnRefreshMyClaims) btnRefreshMyClaims.addEventListener("click", loadMyClaims);

    const btnClearMyClaimsFilter = document.getElementById("btn-clear-myclaims-filter");
    if (myClaimsFilterInput) {
        myClaimsFilterInput.addEventListener("input", () => {
            if (btnClearMyClaimsFilter) {
                btnClearMyClaimsFilter.style.display = myClaimsFilterInput.value ? "flex" : "none";
            }
            applySubmissionsFilterAndSort();
        });
    }

    if (btnClearMyClaimsFilter) {
        btnClearMyClaimsFilter.addEventListener("click", () => {
            if (myClaimsFilterInput) myClaimsFilterInput.value = "";
            btnClearMyClaimsFilter.style.display = "none";
            applySubmissionsFilterAndSort();
        });
    }

    if (myClaimsSortSelect) myClaimsSortSelect.addEventListener("change", applySubmissionsFilterAndSort);

    // -------------------------------------------------------------
    // 10. Modals: Claim Details & Evidence Inspection
    // -------------------------------------------------------------
    const modalClaimDetails = document.getElementById("modal-claim-details");
    const btnCloseDetailsModal = document.getElementById("btn-close-details-modal");
    const btnModalClose = document.getElementById("btn-modal-close");

    const modalClaimEvidence = document.getElementById("modal-claim-evidence");
    const btnCloseEvidenceModal = document.getElementById("btn-close-evidence-modal");
    const btnEvidenceModalClose = document.getElementById("btn-evidence-modal-close");

    let claimDetailsScrollPos = 0;

    function lockClaimDetailsScroll() {
        if (!document.body.classList.contains("modal-open")) {
            claimDetailsScrollPos = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
            document.documentElement.classList.add("modal-open");
            document.body.classList.add("modal-open");
        }
    }

    function unlockClaimDetailsScroll() {
        document.documentElement.classList.remove("modal-open");
        document.body.classList.remove("modal-open");
        const prevBehavior = document.documentElement.style.scrollBehavior;
        document.documentElement.style.scrollBehavior = "auto";
        try {
            window.scrollTo({
                top: claimDetailsScrollPos,
                left: 0,
                behavior: "instant"
            });
        } catch (e) {
            window.scrollTo(0, claimDetailsScrollPos);
        }
        document.documentElement.style.scrollBehavior = prevBehavior;
    }

    function closeClaimDetailsModal() {
        if (modalClaimDetails) modalClaimDetails.style.display = "none";
        unlockClaimDetailsScroll();
    }

    function closeClaimEvidenceModal() {
        if (modalClaimEvidence) modalClaimEvidence.style.display = "none";
    }

    if (btnCloseDetailsModal) btnCloseDetailsModal.addEventListener("click", closeClaimDetailsModal);
    if (btnModalClose) btnModalClose.addEventListener("click", closeClaimDetailsModal);
    if (btnCloseEvidenceModal) btnCloseEvidenceModal.addEventListener("click", closeClaimEvidenceModal);
    if (btnEvidenceModalClose) btnEvidenceModalClose.addEventListener("click", closeClaimEvidenceModal);

    // Close Claim Details modal with Escape key
    window.addEventListener("keydown", (e) => {
        if (e.key === "Escape" || e.keyCode === 27) {
            if (modalClaimDetails && modalClaimDetails.style.display === "flex") {
                closeClaimDetailsModal();
            }
        }
    });

    async function openClaimDetailsModal(claimId) {
        if (!modalClaimDetails) return;

        // Synchronize active claim identifier across all portal modules
        currentActiveClaimId = claimId;

        lockClaimDetailsScroll();

        const idSpan = document.getElementById("modal-details-id");
        if (idSpan) idSpan.textContent = claimId;

        // Reset details
        document.getElementById("detail-claimant-name").textContent = "Loading...";
        document.getElementById("detail-policy-number").textContent = "Loading...";
        document.getElementById("detail-vehicle-number").textContent = "Loading...";
        document.getElementById("detail-accident-date").textContent = "Loading...";
        document.getElementById("detail-incident-location").textContent = "-";
        document.getElementById("detail-status").textContent = "Loading...";
        document.getElementById("detail-description").textContent = "Loading claim narrative...";

        const btnReceipt = document.getElementById("btn-modal-receipt");
        const btnReport = document.getElementById("btn-modal-report");
        if (btnReceipt) btnReceipt.href = `/api/claims/${claimId}/receipt`;
        if (btnReport) btnReport.href = `/api/claims/${claimId}/document-report`;

        const extractedSection = document.getElementById("modal-extracted-section");
        const extractedRows = document.getElementById("modal-extracted-rows");
        if (extractedSection) extractedSection.style.display = "none";
        if (extractedRows) extractedRows.innerHTML = "";

        modalClaimDetails.style.display = "flex";
        const modalBody = modalClaimDetails.querySelector(".modal-body");
        if (modalBody) modalBody.scrollTop = 0;

        try {
            const res = await fetch(`/api/claims/${claimId}`);
            const json = await res.json();
            if (!res.ok || !json.success) throw new Error(json.message || "Failed to load claim details.");

            const claim = json.data;
            document.getElementById("detail-claimant-name").textContent = claim.claimant_name || "-";
            document.getElementById("detail-policy-number").textContent = claim.policy_number || "-";
            document.getElementById("detail-vehicle-number").textContent = claim.vehicle_number || "-";
            document.getElementById("detail-accident-date").textContent = claim.accident_date || "-";
            document.getElementById("detail-incident-location").textContent = claim.incident_location || "Not specified";
            document.getElementById("detail-status").textContent = claim.status || "SUBMITTED";
            document.getElementById("detail-description").textContent = claim.claim_description || "No narrative provided.";

            // Fetch extracted fields if present (Phase 4 OCR)
            try {
                const extRes = await fetch(`/api/claims/${claimId}/extracted`);
                if (extRes.ok) {
                    const extData = await extRes.json();
                    if (extData.fields && extData.fields.length > 0 && extractedRows && extractedSection) {
                        extractedRows.innerHTML = extData.fields.map((f) => `
                            <tr>
                                <td><strong>${escapeHtml(f.field_name || "-")}</strong></td>
                                <td>${escapeHtml(f.extracted_value || "-")}</td>
                                <td><code>${escapeHtml(f.source_filename || "-")}</code> (p.${f.page_number || 1})</td>
                                <td>${escapeHtml(f.extraction_method || "OCR/Regex")}</td>
                                <td>${f.confidence_score ? (f.confidence_score * 100).toFixed(0) + "%" : "90%"}</td>
                                <td><span class="status-pill status-ready">${escapeHtml(f.field_status || "Consistent")}</span></td>
                            </tr>
                        `).join("");
                        extractedSection.style.display = "block";
                    }
                }
            } catch {
                // optional
            }

            // Phase 5: Load and display AI Vehicle Damage Inspection (CarDD)
            const damageSection = document.getElementById("modal-damage-section");
            const btnAnalyzeDamage = document.getElementById("btn-analyze-damage");
            const btnDamageText = document.getElementById("btn-damage-text");
            const btnDamageSpinner = document.getElementById("btn-damage-spinner");
            const damageStatusBanner = document.getElementById("damage-status-banner");
            const damageVisualContainer = document.getElementById("damage-visual-container");
            const damageOriginalImg = document.getElementById("damage-original-img");
            const damageAnnotatedImg = document.getElementById("damage-annotated-img");
            const damageAnnotatedPlaceholder = document.getElementById("damage-annotated-placeholder");
            const btnDownloadAnnotated = document.getElementById("btn-download-annotated");
            const damageMetricsContainer = document.getElementById("damage-metrics-container");
            const metricDamageCount = document.getElementById("metric-damage-count");
            const metricDamagePeakConf = document.getElementById("metric-damage-peak-conf");
            const metricDamageLatency = document.getElementById("metric-damage-latency");
            const metricDamageModel = document.getElementById("metric-damage-model");
            const damageTableContainer = document.getElementById("damage-table-container");
            const damageDetectionsRows = document.getElementById("damage-detections-rows");
            const damageHistoryContainer = document.getElementById("damage-history-container");
            const damageHistoryList = document.getElementById("damage-history-list");
            const modelBenchmarkSubtitle = document.getElementById("model-benchmark-subtitle");

            if (modelBenchmarkSubtitle) {
                modelBenchmarkSubtitle.innerHTML = "Model: <b>YOLOv8n-CarDD</b> (v1.0) &bull; Dataset: <b>CarDD-300</b> &bull; Precision: <b>31.4%</b> &bull; Recall: <b>34.6%</b> &bull; mAP@50: <b>19.3%</b> &bull; mAP@50-95: <b>12.2%</b>";
            }

            function getPillClass(cat) {
                const c = (cat || "").toLowerCase();
                if (c.includes("dent")) return "damage-dent";
                if (c.includes("scratch")) return "damage-scratch";
                if (c.includes("crack")) return "damage-crack";
                if (c.includes("glass")) return "damage-glass";
                if (c.includes("lamp")) return "damage-lamp";
                if (c.includes("tire")) return "damage-tire";
                return "damage-dent";
            }

            function displayDamageAnalysis(analysis) {
                if (!damageVisualContainer) return;

                if (damageOriginalImg) {
                    damageOriginalImg.src = getApiUrl(`/api/claims/${claimId}/evidence/image?t=${Date.now()}`);
                }

                if (analysis && (analysis.total_detections !== undefined || analysis.detections)) {
                    const count = analysis.total_detections !== undefined ? analysis.total_detections : (analysis.detections ? analysis.detections.length : 0);
                    const peak = (analysis.highest_confidence !== undefined ? analysis.highest_confidence : (analysis.max_confidence || 0)) * 100;
                    const latency = analysis.processing_time_ms || analysis.inference_time_ms || 0;

                    if (damageAnnotatedImg) {
                        damageAnnotatedImg.src = getApiUrl(`/api/claims/${claimId}/annotated-image?t=${Date.now()}`);
                        damageAnnotatedImg.style.display = "block";
                    }
                    if (damageAnnotatedPlaceholder) damageAnnotatedPlaceholder.style.display = "none";
                    if (btnDownloadAnnotated) {
                        btnDownloadAnnotated.href = getApiUrl(`/api/claims/${claimId}/annotated-image?download=true`);
                        btnDownloadAnnotated.style.display = "inline-flex";
                    }

                    if (metricDamageCount) metricDamageCount.textContent = count;
                    if (metricDamagePeakConf) metricDamagePeakConf.textContent = peak.toFixed(1) + "%";
                    if (metricDamageLatency) metricDamageLatency.textContent = latency > 0 ? latency.toFixed(0) + " ms" : "-";
                    if (metricDamageModel) metricDamageModel.textContent = analysis.model_name || "YOLOv8n-CarDD";

                    damageVisualContainer.style.display = "grid";
                    if (damageMetricsContainer) damageMetricsContainer.style.display = "grid";

                    const detections = analysis.detections || [];
                    if (detections.length > 0 && damageDetectionsRows && damageTableContainer) {
                        damageDetectionsRows.innerHTML = detections.map((d, idx) => {
                            const conf = d.confidence ? (d.confidence * 100).toFixed(1) + "%" : "-";
                            const bbox = d.bbox || (d.bbox_x1 !== undefined ? [d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2] : null);
                            const bboxStr = bbox ? `[${bbox.map(v => Math.round(v)).join(", ")}]` : "-";
                            const reg = (d.location_region || d.region || "center").replace(/_/g, " ").toUpperCase();
                            const cat = (d.category || "damage").toUpperCase();
                            const pillCls = getPillClass(d.category);
                            return `
                                <tr>
                                    <td><strong>${d.detection_index || (idx + 1)}</strong></td>
                                    <td><span class="damage-pill ${pillCls}">${escapeHtml(cat)}</span></td>
                                    <td><strong>${escapeHtml(conf)}</strong></td>
                                    <td>${escapeHtml(reg)}</td>
                                    <td><code>${escapeHtml(bboxStr)}</code></td>
                                </tr>
                            `;
                        }).join("");
                        damageTableContainer.style.display = "block";
                    } else if (damageTableContainer) {
                        damageTableContainer.style.display = "none";
                    }

                    if (damageStatusBanner) {
                        damageStatusBanner.className = "damage-banner success mt-2";
                        damageStatusBanner.textContent = `✓ AI Damage Analysis completed: ${count} damage regions localized with YOLOv8n-CarDD (Peak: ${peak.toFixed(1)}%).`;
                        damageStatusBanner.style.display = "block";
                    }
                } else {
                    if (damageAnnotatedImg) damageAnnotatedImg.style.display = "none";
                    if (damageAnnotatedPlaceholder) damageAnnotatedPlaceholder.style.display = "flex";
                    if (btnDownloadAnnotated) btnDownloadAnnotated.style.display = "none";
                    if (damageMetricsContainer) damageMetricsContainer.style.display = "none";
                    if (damageTableContainer) damageTableContainer.style.display = "none";
                    damageVisualContainer.style.display = "grid";

                    if (damageStatusBanner) {
                        damageStatusBanner.className = "damage-banner info mt-2";
                        damageStatusBanner.textContent = 'ℹ Vehicle photograph loaded. Click "Analyze Vehicle Damage" to execute YOLOv8 detection.';
                        damageStatusBanner.style.display = "block";
                    }
                }
            }

            // Modal Replacement Image Upload Widget Integration
            const modalReplaceContainer = document.getElementById("modal-replace-container");
            const btnToggleReplaceModal = document.getElementById("btn-toggle-replace-modal");
            const modalFormReplaceImage = document.getElementById("modal-form-replace-image");
            const modalInputReplaceImage = document.getElementById("modal-input-replace-image");
            const modalBtnSubmitReplace = document.getElementById("modal-btn-submit-replace");
            const modalBtnReplaceText = document.getElementById("modal-btn-replace-text");
            const modalBtnReplaceSpinner = document.getElementById("modal-btn-replace-spinner");
            const modalReplaceStatus = document.getElementById("modal-replace-status");

            if (modalReplaceContainer) modalReplaceContainer.style.display = "none";
            if (modalReplaceStatus) modalReplaceStatus.style.display = "none";

            if (btnToggleReplaceModal) {
                btnToggleReplaceModal.onclick = () => {
                    if (modalReplaceContainer) {
                        const isVisible = modalReplaceContainer.style.display !== "none";
                        modalReplaceContainer.style.display = isVisible ? "none" : "block";
                        if (!isVisible && modalInputReplaceImage) {
                            modalInputReplaceImage.focus();
                        }
                    }
                };
            }

            if (modalFormReplaceImage) {
                modalFormReplaceImage.onsubmit = async (e) => {
                    e.preventDefault();
                    if (!modalInputReplaceImage || !modalInputReplaceImage.files || modalInputReplaceImage.files.length === 0) {
                        if (modalReplaceStatus) {
                            modalReplaceStatus.className = "alert alert-error mt-2";
                            modalReplaceStatus.textContent = "Please select a JPEG or PNG vehicle photograph to upload.";
                            modalReplaceStatus.style.display = "block";
                        }
                        return;
                    }

                    const file = modalInputReplaceImage.files[0];
                    const formData = new FormData();
                    formData.append("vehicle_image", file);

                    let token = getCsrfToken();
                    if (token) formData.append("csrf_token", token);

                    if (modalBtnSubmitReplace) modalBtnSubmitReplace.disabled = true;
                    if (modalBtnReplaceSpinner) modalBtnReplaceSpinner.style.display = "inline-block";
                    if (modalBtnReplaceText) modalBtnReplaceText.textContent = "Uploading & Validating...";
                    if (modalReplaceStatus) {
                        modalReplaceStatus.className = "alert alert-info mt-2";
                        modalReplaceStatus.textContent = "Uploading and validating replacement photograph...";
                        modalReplaceStatus.style.display = "block";
                    }

                    try {
                        const repRes = await safeFetchJson(`/api/claims/${claimId}/replace-image`, {
                            method: "POST",
                            body: formData,
                        });

                        if (!repRes.ok || !repRes.data || !repRes.data.success) {
                            const errMsg = repRes.error || (repRes.data && repRes.data.message) || "Failed to upload replacement photograph.";
                            if (modalReplaceStatus) {
                                modalReplaceStatus.className = "alert alert-error mt-2";
                                modalReplaceStatus.textContent = `⚠ ${errMsg}`;
                                modalReplaceStatus.style.display = "block";
                            }
                            if (damageStatusBanner) {
                                damageStatusBanner.className = "damage-banner danger mt-2";
                                damageStatusBanner.textContent = `Upload rejected: ${errMsg}`;
                                damageStatusBanner.style.display = "block";
                            }
                            return;
                        }

                        const data = repRes.data;
                        if (modalReplaceStatus) {
                            modalReplaceStatus.className = "alert alert-success mt-2";
                            modalReplaceStatus.textContent = `✓ Replacement photograph verified as authentic vehicle photograph! (${data.validation && data.validation.resolution ? data.validation.resolution : "Validated"})`;
                            modalReplaceStatus.style.display = "block";
                        }

                        // Refresh original image preview with cache-buster
                        if (damageOriginalImg) {
                            damageOriginalImg.src = getApiUrl(`/api/claims/${claimId}/evidence/image?t=${Date.now()}`);
                        }
                        const badgePhoto = document.getElementById("badge-photo-validation");
                        if (badgePhoto) {
                            badgePhoto.className = "badge badge-success";
                            badgePhoto.textContent = "Authentic Replacement Photo";
                        }

                        // If damage analysis was auto-executed on backend
                        if (data.damage_analysis) {
                            displayDamageAnalysis(data.damage_analysis);
                            loadDamageHistory();
                        } else {
                            if (damageStatusBanner) {
                                damageStatusBanner.className = "damage-banner success mt-2";
                                damageStatusBanner.textContent = '✓ Replacement photograph uploaded and validated. Click "Analyze Vehicle Damage" to execute YOLOv8 detection.';
                                damageStatusBanner.style.display = "block";
                            }
                        }
                    } catch (err) {
                        if (modalReplaceStatus) {
                            modalReplaceStatus.className = "alert alert-error mt-2";
                            modalReplaceStatus.textContent = `Error: ${err.message}`;
                            modalReplaceStatus.style.display = "block";
                        }
                    } finally {
                        if (modalBtnSubmitReplace) modalBtnSubmitReplace.disabled = false;
                        if (modalBtnReplaceSpinner) modalBtnReplaceSpinner.style.display = "none";
                        if (modalBtnReplaceText) modalBtnReplaceText.textContent = "Upload Replacement Photo";
                    }
                };
            }

            // Wire up analyze button with robust non-JSON / HTML error handling
            if (btnAnalyzeDamage) {
                btnAnalyzeDamage.onclick = async () => {
                    btnAnalyzeDamage.disabled = true;
                    if (btnDamageSpinner) btnDamageSpinner.style.display = "inline-block";
                    if (btnDamageText) btnDamageText.textContent = "Analyzing Damage...";
                    if (damageStatusBanner) {
                        damageStatusBanner.className = "damage-banner info mt-2";
                        damageStatusBanner.textContent = "Running YOLOv8n-CarDD computer vision inference...";
                        damageStatusBanner.style.display = "block";
                    }

                    try {
                        const anRes = await safeFetchJson(`/api/claims/${claimId}/analyze-damage`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" }
                        });

                        if (!anRes.ok || !anRes.data || !anRes.data.success) {
                            const data = anRes.data;
                            if (data && data.requires_replacement) {
                                if (damageStatusBanner) {
                                    damageStatusBanner.className = "damage-banner warning mt-2";
                                    damageStatusBanner.textContent = `⚠ ${data.message || "Invalid vehicle photograph. Please upload an authentic replacement photograph."}`;
                                    damageStatusBanner.style.display = "block";
                                }
                                if (modalReplaceContainer) {
                                    modalReplaceContainer.style.display = "block";
                                    modalReplaceContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
                                }
                                const badgePhoto = document.getElementById("badge-photo-validation");
                                if (badgePhoto) {
                                    badgePhoto.className = "badge badge-danger";
                                    badgePhoto.textContent = data.validation ? data.validation.status.replace(/_/g, " ").toUpperCase() : "INVALID GRAPHIC";
                                }
                            } else {
                                const errMsg = anRes.error || (data && data.message) || "Failed to analyze vehicle damage.";
                                if (damageStatusBanner) {
                                    damageStatusBanner.className = "damage-banner danger mt-2";
                                    damageStatusBanner.textContent = `Error: ${errMsg}`;
                                    damageStatusBanner.style.display = "block";
                                }
                            }
                            return;
                        }

                        displayDamageAnalysis(anRes.data.analysis);
                        loadDamageHistory();
                    } catch (err) {
                        if (damageStatusBanner) {
                            damageStatusBanner.className = "damage-banner danger mt-2";
                            damageStatusBanner.textContent = `Error: ${err.message}`;
                            damageStatusBanner.style.display = "block";
                        }
                    } finally {
                        btnAnalyzeDamage.disabled = false;
                        if (btnDamageSpinner) btnDamageSpinner.style.display = "none";
                        if (btnDamageText) btnDamageText.textContent = "🔍 Analyze Vehicle Damage";
                    }
                };
            }

            async function loadDamageHistory() {
                if (!damageHistoryContainer || !damageHistoryList) return;
                try {
                    const hRes = await safeFetchJson(`/api/claims/${claimId}/damage-history`);
                    if (hRes.ok && hRes.data) {
                        const hData = hRes.data;
                        if (hData.analyses && hData.analyses.length > 0) {
                            damageHistoryList.innerHTML = hData.analyses.map((a, i) => `
                                <span class="history-tag">Run #${hData.analyses.length - i} &bull; ${a.total_detections || 0} damages &bull; ${(a.highest_confidence * 100 || 0).toFixed(1)}% conf &bull; ${Math.round(a.processing_time_ms || 0)}ms</span>
                            `).join("");
                            damageHistoryContainer.style.display = "block";
                        } else {
                            damageHistoryContainer.style.display = "none";
                        }
                    }
                } catch {
                    // optional
                }
            }

            // Initial load of damage analysis
            if (claim.damage_analysis) {
                displayDamageAnalysis(claim.damage_analysis);
            } else {
                try {
                    const daRes = await safeFetchJson(`/api/claims/${claimId}/damage-analysis`);
                    if (daRes.ok && daRes.data && daRes.data.analysis) {
                        displayDamageAnalysis(daRes.data.analysis);
                    } else {
                        displayDamageAnalysis(null);
                    }
                } catch {
                    displayDamageAnalysis(null);
                }
            }

            loadDamageHistory();

            // -------------------------------------------------------------
            // Phase 6: Load and display AI Claim Description Analysis (NLP)
            // -------------------------------------------------------------
            const btnAnalyzeNlp = document.getElementById("btn-analyze-nlp");
            const btnNlpText = document.getElementById("btn-nlp-text");
            const btnNlpSpinner = document.getElementById("btn-nlp-spinner");
            const nlpStatusBanner = document.getElementById("nlp-status-banner");
            const nlpResultsContainer = document.getElementById("nlp-results-container");
            const nlpNarrativeText = document.getElementById("nlp-narrative-text");
            const nlpMetricType = document.getElementById("nlp-metric-type");
            const nlpMetricConfidence = document.getElementById("nlp-metric-confidence");
            const nlpMetricEntities = document.getElementById("nlp-metric-entities");
            const nlpMetricConsistency = document.getElementById("nlp-metric-consistency");
            const nlpEntitiesList = document.getElementById("nlp-entities-list");
            const nlpChronologyBadge = document.getElementById("nlp-chronology-badge");
            const nlpTimelineContainer = document.getElementById("nlp-timeline-container");
            const nlpDamagesRows = document.getElementById("nlp-damages-rows");
            const nlpConsistencyRows = document.getElementById("nlp-consistency-rows");
            const nlpMissingContainer = document.getElementById("nlp-missing-container");
            const nlpMissingList = document.getElementById("nlp-missing-list");

            function displayNlpAnalysis(analysis) {
                if (!nlpResultsContainer) return;

                if (analysis && (analysis.accident_type || analysis.entities || analysis.timeline)) {
                    if (nlpNarrativeText) {
                        nlpNarrativeText.textContent = `"${analysis.original_narrative || claim.claim_description || ""}"`;
                    }
                    if (nlpMetricType) nlpMetricType.textContent = analysis.accident_type || "UNKNOWN";
                    if (nlpMetricConfidence) {
                        const confVal = (analysis.accident_type_confidence || 0) * 100;
                        nlpMetricConfidence.textContent = `${confVal.toFixed(0)}%`;
                    }
                    if (nlpMetricEntities) {
                        nlpMetricEntities.textContent = (analysis.entities ? analysis.entities.length : 0);
                    }
                    if (nlpMetricConsistency) {
                        const consVal = analysis.consistency ? analysis.consistency.consistency_score : 0;
                        nlpMetricConsistency.textContent = `${(consVal || 0)}%`;
                    }

                    // Render Entities
                    if (nlpEntitiesList) {
                        const ents = analysis.entities || [];
                        if (ents.length > 0) {
                            nlpEntitiesList.innerHTML = ents.map((e) => {
                                const t = e.entity_type || "ENTITY";
                                let badgeClass = "badge-location";
                                if (t.includes("ROAD")) badgeClass = "badge-road";
                                else if (t.includes("VEHICLE")) badgeClass = "badge-vehicle";
                                else if (t.includes("OTHER")) badgeClass = "badge-other";
                                else if (t.includes("CLAIMANT")) badgeClass = "badge-claimant";
                                else if (t.includes("DATE") || t.includes("TIME")) badgeClass = "badge-date";
                                else if (t.includes("WEATHER")) badgeClass = "badge-weather";
                                return `<span class="entity-chip"><span class="entity-type-badge ${badgeClass}">${escapeHtml(t)}</span><strong>${escapeHtml(e.text)}</strong></span>`;
                            }).join("");
                        } else {
                            nlpEntitiesList.innerHTML = `<span style="font-size: 0.8rem; color: var(--text-muted);">No distinct domain entities found in narrative.</span>`;
                        }
                    }

                    // Render Chronology Timeline
                    if (nlpTimelineContainer) {
                        const steps = analysis.timeline || [];
                        if (steps.length > 0) {
                            nlpTimelineContainer.innerHTML = steps.map((s) => `
                                <div class="timeline-item">
                                    <div class="timeline-step-num">${s.step_number || 1}</div>
                                    <div class="timeline-content">
                                        <div class="timeline-header">
                                            <span class="badge badge-primary">${escapeHtml(s.event_type || "EVENT")}</span>
                                            <span class="timeline-phase">${escapeHtml(s.phase || s.time_reference || "")}</span>
                                        </div>
                                        <div class="timeline-desc">${escapeHtml(s.description || "")}</div>
                                        <div class="timeline-quote">"${escapeHtml(s.supporting_sentence || "")}"</div>
                                    </div>
                                </div>
                            `).join("");
                        } else {
                            nlpTimelineContainer.innerHTML = `<span style="font-size: 0.8rem; color: var(--text-muted);">No sequential timeline events extracted.</span>`;
                        }
                    }

                    // Render Claimant-Reported Damages
                    if (nlpDamagesRows) {
                        const dmgs = analysis.reported_damages || [];
                        if (dmgs.length > 0) {
                            nlpDamagesRows.innerHTML = dmgs.map((d) => `
                                <tr>
                                    <td><strong>${escapeHtml(d.component || "-")}</strong></td>
                                    <td><span class="badge badge-info">${escapeHtml(d.reported_condition || "Damaged")}</span></td>
                                    <td>${escapeHtml((d.spatial_region || "rear").replace(/_/g, " ").toUpperCase())}</td>
                                    <td><i>"${escapeHtml(d.supporting_sentence || "-")}"</i></td>
                                </tr>
                            `).join("");
                        } else {
                            nlpDamagesRows.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No vehicle damage items mentioned in narrative statement.</td></tr>`;
                        }
                    }

                    // Render Consistency Corroboration
                    if (nlpConsistencyRows) {
                        const comps = (analysis.consistency && analysis.consistency.comparisons) || [];
                        if (comps.length > 0) {
                            nlpConsistencyRows.innerHTML = comps.map((c) => {
                                const st = c.status || "INFO";
                                let pillCls = "status-ready";
                                if (st === "MATCH") pillCls = "status-ready";
                                else if (st === "CONTRADICTORY") pillCls = "status-failed";
                                else if (st === "MISSING_IN_NARRATIVE") pillCls = "status-pending";
                                return `
                                    <tr>
                                        <td><strong>${escapeHtml(c.field || "-")}</strong></td>
                                        <td>${escapeHtml(c.narrative_value || "-")}</td>
                                        <td>${escapeHtml(c.document_value || "-")}<br/><small style="color: var(--text-muted);">${escapeHtml(c.source_document || "")}</small></td>
                                        <td><span class="status-pill ${pillCls}">${escapeHtml(st)}</span></td>
                                        <td>${escapeHtml(c.explanation || "-")}</td>
                                    </tr>
                                `;
                            }).join("");
                        } else {
                            nlpConsistencyRows.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No cross-source comparisons recorded.</td></tr>`;
                        }
                    }

                    // Missing / Ambiguous Notes
                    const missing = analysis.missing_information || [];
                    if (missing.length > 0 && nlpMissingContainer && nlpMissingList) {
                        nlpMissingList.innerHTML = missing.map((m) => `<li>${escapeHtml(m)}</li>`).join("");
                        nlpMissingContainer.style.display = "block";
                    } else if (nlpMissingContainer) {
                        nlpMissingContainer.style.display = "none";
                    }

                    if (nlpStatusBanner) {
                        nlpStatusBanner.className = "damage-banner success mt-2";
                        nlpStatusBanner.textContent = `✓ NLP Claim Narrative Analysis complete: ${analysis.accident_type || 'Accident'} classified with ${analysis.entities ? analysis.entities.length : 0} entities and ${analysis.timeline ? analysis.timeline.length : 0} chronological events.`;
                        nlpStatusBanner.style.display = "block";
                    }

                    nlpResultsContainer.style.display = "block";
                } else {
                    nlpResultsContainer.style.display = "none";
                    if (nlpStatusBanner) {
                        nlpStatusBanner.className = "damage-banner info mt-2";
                        nlpStatusBanner.textContent = 'ℹ Claimant statement ready. Click "Analyze Narrative" to run NLP entity, chronology, and classification extraction.';
                        nlpStatusBanner.style.display = "block";
                    }
                }
            }

            // Wire up NLP analyze button
            if (btnAnalyzeNlp) {
                btnAnalyzeNlp.onclick = async () => {
                    btnAnalyzeNlp.disabled = true;
                    if (btnNlpSpinner) btnNlpSpinner.style.display = "inline-block";
                    if (btnNlpText) btnNlpText.textContent = "Analyzing Narrative...";
                    if (nlpStatusBanner) {
                        nlpStatusBanner.className = "damage-banner info mt-2";
                        nlpStatusBanner.textContent = "Executing NLP entity extraction and event timeline reconstruction...";
                        nlpStatusBanner.style.display = "block";
                    }

                    try {
                        const anRes = await fetch(`/api/claims/${claimId}/analyze-description`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" }
                        });
                        const anData = await anRes.json();
                        if (!anRes.ok || !anData.success) {
                            throw new Error(anData.message || "Failed to analyze claim description.");
                        }
                        displayNlpAnalysis(anData.analysis);
                    } catch (err) {
                        if (nlpStatusBanner) {
                            nlpStatusBanner.className = "damage-banner danger mt-2";
                            nlpStatusBanner.textContent = `Error: ${err.message}`;
                            nlpStatusBanner.style.display = "block";
                        }
                    } finally {
                        btnAnalyzeNlp.disabled = false;
                        if (btnNlpSpinner) btnNlpSpinner.style.display = "none";
                        if (btnNlpText) btnNlpText.textContent = "🔍 Analyze Narrative";
                    }
                };
            }

            // Initial load of NLP analysis
            if (claim.nlp_analysis) {
                displayNlpAnalysis(claim.nlp_analysis);
            } else {
                try {
                    const nlpRes = await fetch(`/api/claims/${claimId}/nlp-analysis`);
                    if (nlpRes.ok) {
                        const nlpData = await nlpRes.json();
                        if (nlpData.analysis) {
                            displayNlpAnalysis(nlpData.analysis);
                        } else {
                            displayNlpAnalysis(null);
                        }
                    } else {
                        displayNlpAnalysis(null);
                    }
                } catch {
                    displayNlpAnalysis(null);
                }
            }

            // =========================================================
            // PHASE 7: Cross-Source Verification Logic
            // =========================================================
            const btnRunVerification = document.getElementById("btn-run-verification");
            const verifPendingBanner = document.getElementById("verif-pending-banner");
            const verifContentContainer = document.getElementById("verif-content-container");
            const verifMetricStatus = document.getElementById("verif-metric-status");
            const verifMetricScore = document.getElementById("verif-metric-score");
            const verifMetricMatched = document.getElementById("verif-metric-matched");
            const verifMetricMismatched = document.getElementById("verif-metric-mismatched");
            const verifMetricMissing = document.getElementById("verif-metric-missing");
            const verifFindingsRows = document.getElementById("verif-findings-rows");
            const verifRecommendationsContainer = document.getElementById("verif-recommendations-container");
            const verifRecommendationsList = document.getElementById("verif-recommendations-list");

            function displayVerificationResults(verif) {
                if (!verif || (verif.total_comparisons === undefined && !verif.findings)) {
                    if (verifPendingBanner) {
                        verifPendingBanner.className = "damage-banner banner-info mt-2";
                        verifPendingBanner.textContent = "Click 'Run Verification' to perform automated multi-source consistency checks across submitted evidence.";
                        verifPendingBanner.style.display = "block";
                    }
                    if (verifContentContainer) verifContentContainer.style.display = "none";
                    return;
                }

                if (verifPendingBanner) verifPendingBanner.style.display = "none";
                if (verifContentContainer) verifContentContainer.style.display = "block";

                // Populate metrics
                if (verifMetricStatus) {
                    verifMetricStatus.textContent = verif.overall_status || "CONSISTENT";
                    if (verif.overall_status === "CONSISTENT") {
                        verifMetricStatus.style.color = "var(--success)";
                    } else if (verif.overall_status === "REVIEW_REQUIRED") {
                        verifMetricStatus.style.color = "var(--danger)";
                    } else {
                        verifMetricStatus.style.color = "var(--warning)";
                    }
                }
                if (verifMetricScore) {
                    const score = verif.consistency_score != null ? Number(verif.consistency_score).toFixed(1) : "100.0";
                    verifMetricScore.textContent = `${score}%`;
                    verifMetricScore.style.color = Number(score) >= 75 ? "var(--success)" : (Number(score) >= 50 ? "var(--warning)" : "var(--danger)");
                }
                if (verifMetricMatched) verifMetricMatched.textContent = verif.matched_comparisons || 0;
                if (verifMetricMismatched) verifMetricMismatched.textContent = verif.mismatched_comparisons || 0;
                if (verifMetricMissing) verifMetricMissing.textContent = verif.missing_evidence_count || 0;

                // Populate findings table
                if (verifFindingsRows) {
                    verifFindingsRows.innerHTML = "";
                    const findings = verif.findings || [];
                    if (findings.length === 0) {
                        verifFindingsRows.innerHTML = `<tr><td colspan="7" class="text-center text-muted p-4">No comparison findings generated.</td></tr>`;
                    } else {
                        findings.forEach(f => {
                            const tr = document.createElement("tr");

                            // Status badge class and concise label
                            let stClass = "badge-status-missing";
                            const st = (f.comparison_status || "").toUpperCase();
                            let stDisplay = (f.comparison_status || "").replace(/_/g, " ");

                            if (st === "MATCH") {
                                stClass = "badge-status-match";
                                stDisplay = "MATCH";
                            } else if (st === "MISMATCH") {
                                stClass = "badge-status-mismatch";
                                stDisplay = "MISMATCH";
                            } else if (st === "MISSING_IN_SOURCE" || st === "NOT_PRESENT") {
                                stClass = "badge-status-missing";
                                stDisplay = "MISSING";
                            } else if (st === "INCONCLUSIVE" || st === "NEEDS_REVIEW" || st === "EXTRACTION_ERROR") {
                                stClass = "badge-status-inconclusive";
                                stDisplay = "INCONCLUSIVE";
                            } else if (st === "POTENTIAL_DISCREPANCY") {
                                stClass = "badge-status-inconclusive";
                                stDisplay = "DISCREPANCY";
                            } else if (st === "NOT_APPLICABLE" || st === "NA") {
                                stClass = "badge-status-na";
                                stDisplay = "N/A";
                            } else if (st === "VISUAL_ONLY" || st === "VISUAL_ONLY_FINDING") {
                                stClass = "badge-status-visual";
                                stDisplay = "VISUAL ONLY";
                            } else if (st === "NOT_CONFIRMED" || st === "UNCONFIRMED" || st === "NOT_VISUALLY_CONFIRMED") {
                                stClass = "badge-status-inconclusive";
                                stDisplay = "NOT CONFIRMED";
                            }

                            // Severity badge class
                            let sevClass = "badge-sev-low";
                            const sev = (f.severity || "").toUpperCase();
                            if (sev === "CRITICAL") {
                                sevClass = "badge-sev-critical";
                            } else if (sev === "HIGH") {
                                sevClass = "badge-sev-high";
                            } else if (sev === "MEDIUM") {
                                sevClass = "badge-sev-medium";
                            } else if (sev === "LOW") {
                                sevClass = "badge-sev-low";
                            }

                            const valA = f.original_value_a != null && f.original_value_a !== "" ? escapeHtml(String(f.original_value_a)) : '<span class="val-token val-token-empty">—</span>';
                            const valB = f.original_value_b != null && f.original_value_b !== "" ? escapeHtml(String(f.original_value_b)) : '<span class="val-token val-token-empty">—</span>';

                            const tokenA = valA.startsWith('<span') ? valA : `<span class="val-token">${valA}</span>`;
                            const tokenB = valB.startsWith('<span') ? valB : `<span class="val-token">${valB}</span>`;

                            tr.innerHTML = `
                                <td class="td-cmp">
                                    <div class="cmp-container">
                                        <span class="cmp-source-primary" title="${escapeHtml(f.source_a || '')}">${escapeHtml(f.source_a || '')}</span>
                                        <span class="cmp-source-secondary" title="vs ${escapeHtml(f.source_b || '')}">vs ${escapeHtml(f.source_b || '')}</span>
                                    </div>
                                </td>
                                <td class="td-field">
                                    <div class="field-title" title="${escapeHtml(f.field_name || '')}">${escapeHtml(f.field_name || '')}</div>
                                    <span class="field-id-tag">${escapeHtml(f.comparison_id || '')}</span>
                                </td>
                                <td class="td-source-a">${tokenA}</td>
                                <td class="td-source-b">${tokenB}</td>
                                <td class="td-status"><span class="status-badge ${stClass}">${escapeHtml(stDisplay)}</span></td>
                                <td class="td-severity"><span class="severity-badge ${sevClass}">${escapeHtml(f.severity || '')}</span></td>
                                <td class="td-explanation"><div class="expl-text">${escapeHtml(f.explanation || '')}</div></td>
                            `;
                            verifFindingsRows.appendChild(tr);
                        });
                    }
                }

                // Recommendations
                if (verifRecommendationsContainer && verifRecommendationsList) {
                    verifRecommendationsList.innerHTML = "";
                    const recs = verif.recommendations || [];
                    if (recs.length > 0) {
                        recs.forEach(r => {
                            const li = document.createElement("li");
                            li.textContent = r;
                            verifRecommendationsList.appendChild(li);
                        });
                        verifRecommendationsContainer.style.display = "block";
                    } else {
                        verifRecommendationsContainer.style.display = "none";
                    }
                }
            }

            // Wire up Run Verification button
            if (btnRunVerification) {
                btnRunVerification.onclick = async () => {
                    btnRunVerification.disabled = true;
                    btnRunVerification.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Verifying...`;

                    if (verifPendingBanner) {
                        verifPendingBanner.className = "damage-banner banner-info mt-2";
                        verifPendingBanner.textContent = "Executing multi-source cross-verification across evidence documents and vision models...";
                        verifPendingBanner.style.display = "block";
                    }

                    try {
                        let token = getCsrfToken();
                        if (!token) token = await fetchCsrfToken();
                        const headers = { "Content-Type": "application/json" };
                        if (token) {
                            headers["X-CSRFToken"] = token;
                            headers["X-CSRF-Token"] = token;
                        }
                        const payload = { force: true };
                        if (token) payload["csrf_token"] = token;

                        const vRes = await fetch(`/api/claims/${claimId}/verify-cross-source`, {
                            method: "POST",
                            headers: headers,
                            body: JSON.stringify(payload)
                        });
                        const vData = await vRes.json();
                        if (!vRes.ok || !vData.success) {
                            const errObj = new Error(vData.message || "Failed to execute cross-source verification.");
                            errObj.stage = vData.stage;
                            errObj.errorCode = vData.error_code;
                            throw errObj;
                        }
                        displayVerificationResults(vData.verification);
                    } catch (err) {
                        if (verifPendingBanner) {
                            verifPendingBanner.className = "damage-banner banner-danger mt-2";
                            const stagePrefix = err.stage ? `[${err.stage}] ` : "";
                            verifPendingBanner.textContent = `Verification Error: ${stagePrefix}${err.message}`;
                            verifPendingBanner.style.display = "block";
                        }
                    } finally {
                        btnRunVerification.disabled = false;
                        btnRunVerification.innerHTML = `<span class="btn-icon">⚡</span> Run Verification`;
                    }
                };
            }

            // Initial load of verification data
            if (claim.verification) {
                displayVerificationResults(claim.verification);
            } else {
                try {
                    const vGet = await fetch(`/api/claims/${claimId}/verification`);
                    if (vGet.ok) {
                        const vJson = await vGet.json();
                        if (vJson.verified && vJson.verification) {
                            displayVerificationResults(vJson.verification);
                        } else {
                            displayVerificationResults(null);
                        }
                    } else {
                        displayVerificationResults(null);
                    }
                } catch {
                    displayVerificationResults(null);
                }
            }

        } catch (err) {
            document.getElementById("detail-description").textContent = `Error: ${err.message}`;
        }
    }

    async function openClaimEvidenceModal(claimId) {
        if (!modalClaimEvidence) return;

        const idSpan = document.getElementById("modal-evidence-id");
        if (idSpan) idSpan.textContent = claimId;

        const evidenceList = document.getElementById("modal-evidence-list");
        if (evidenceList) {
            evidenceList.innerHTML = `<div class="empty-state">Loading evidence packages for ${escapeHtml(claimId)}...</div>`;
        }

        modalClaimEvidence.style.display = "flex";

        try {
            const res = await fetch(`/api/claims/${claimId}`);
            const json = await res.json();
            if (!res.ok || !json.success) throw new Error(json.message || "Failed to load evidence.");

            const claim = json.data;
            const docs = claim.documents || [];
            const imgs = claim.images || [];

            let cardsHtml = "";

            // Helper to get doc
            const findDoc = (type) => docs.find((d) => d.document_type === type);

            const policyDoc = findDoc("POLICY_DOCUMENT") || docs[0];
            const claimFormDoc = findDoc("CLAIM_FORM") || docs[1];
            const invoiceDoc = findDoc("INVOICE") || docs[2];
            const vehicleImg = imgs[0];

            cardsHtml += `
                <div class="evidence-card">
                    <div class="evidence-card-header">
                        <span class="evidence-type-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></span>
                        <div class="evidence-title-block">
                            <span class="evidence-type-title">Policy Document</span>
                            <span class="evidence-filename">${escapeHtml(policyDoc ? policyDoc.original_filename : "policy_document.pdf")}</span>
                        </div>
                    </div>
                    <div class="evidence-meta-row">
                        <span>Format: <strong>${escapeHtml((policyDoc ? policyDoc.file_extension : "pdf").toUpperCase())}</strong></span>
                        <span>Size: ${formatBytes(policyDoc ? policyDoc.file_size : 124000)}</span>
                    </div>
                    <a href="/api/claims/${claimId}/evidence/policy?download=1" target="_blank" class="btn btn-secondary btn-sm full-width mt-2">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        <span>Download Document</span>
                    </a>
                </div>

                <div class="evidence-card">
                    <div class="evidence-card-header">
                        <span class="evidence-type-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect></svg></span>
                        <div class="evidence-title-block">
                            <span class="evidence-type-title">Claim Application Form</span>
                            <span class="evidence-filename">${escapeHtml(claimFormDoc ? claimFormDoc.original_filename : "signed_claim_form.pdf")}</span>
                        </div>
                    </div>
                    <div class="evidence-meta-row">
                        <span>Format: <strong>${escapeHtml((claimFormDoc ? claimFormDoc.file_extension : "pdf").toUpperCase())}</strong></span>
                        <span>Size: ${formatBytes(claimFormDoc ? claimFormDoc.file_size : 98000)}</span>
                    </div>
                    <a href="/api/claims/${claimId}/evidence/claim_form?download=1" target="_blank" class="btn btn-secondary btn-sm full-width mt-2">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        <span>Download Document</span>
                    </a>
                </div>

                <div class="evidence-card">
                    <div class="evidence-card-header">
                        <span class="evidence-type-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"></rect><line x1="2" y1="10" x2="22" y2="10"></line></svg></span>
                        <div class="evidence-title-block">
                            <span class="evidence-type-title">Repair Invoice / Estimate</span>
                            <span class="evidence-filename">${escapeHtml(invoiceDoc ? invoiceDoc.original_filename : "garage_estimate.pdf")}</span>
                        </div>
                    </div>
                    <div class="evidence-meta-row">
                        <span>Format: <strong>${escapeHtml((invoiceDoc ? invoiceDoc.file_extension : "pdf").toUpperCase())}</strong></span>
                        <span>Size: ${formatBytes(invoiceDoc ? invoiceDoc.file_size : 76000)}</span>
                    </div>
                    <a href="/api/claims/${claimId}/evidence/invoice?download=1" target="_blank" class="btn btn-secondary btn-sm full-width mt-2">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        <span>Download Document</span>
                    </a>
                </div>

                <div class="evidence-card">
                    <div class="evidence-card-header">
                        <span class="evidence-type-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg></span>
                        <div class="evidence-title-block">
                            <span class="evidence-type-title">Vehicle Accident Photo</span>
                            <span class="evidence-filename">${escapeHtml(vehicleImg ? vehicleImg.original_filename : "rear_bumper_damage.jpg")}</span>
                        </div>
                    </div>
                    <div class="evidence-preview-box">
                        <img src="/api/claims/${claimId}/evidence/image" alt="Vehicle Damage Preview" class="evidence-preview-img" onerror="this.style.display='none';">
                    </div>
                    <div class="evidence-meta-row">
                        <span>Format: <strong>${escapeHtml((vehicleImg ? vehicleImg.file_extension : "jpg").toUpperCase())}</strong></span>
                        <span>Size: ${formatBytes(vehicleImg ? vehicleImg.file_size : 245000)}</span>
                    </div>
                    <a href="/api/claims/${claimId}/evidence/image?download=1" target="_blank" class="btn btn-secondary btn-sm full-width mt-2">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        <span>Download Photograph</span>
                    </a>
                </div>
            `;

            if (evidenceList) evidenceList.innerHTML = cardsHtml;

        } catch (err) {
            if (evidenceList) evidenceList.innerHTML = `<div class="empty-state">Error: ${escapeHtml(err.message)}</div>`;
        }
    }

    // -------------------------------------------------------------
    // 11. HTML Escaping Utility (XSS Prevention)
    // -------------------------------------------------------------
    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    // Set initial view to dashboard
    switchView("dashboard");
}

if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initClaimSenseApp);
    } else {
        initClaimSenseApp();
    }
}
