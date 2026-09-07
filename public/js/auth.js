let isSetupMode = false;
let selectedMode = "all-in-one";

async function checkAuthStatus() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await res.json();
    if (data.authenticated) {
      window.location.href = "/";
      return;
    }
    if (!data.setup_completed) {
      isSetupMode = true;
      document.getElementById("setupHeader").style.display = "block";
      document.getElementById("loginHeader").style.display = "none";
      document.getElementById("confirmPasswordGroup").style.display = "block";
      document.getElementById("submitBtn").textContent = "Complete Setup & Launch";
      document.getElementById("password").setAttribute("autocomplete", "new-password");
    }
  } catch (err) {
    console.error("Failed to check auth status:", err);
  }
}

function selectIntegrationMode(mode) {
  selectedMode = mode;
  document.getElementById("wizardCardAllInOne").classList.toggle("selected", mode === "all-in-one");
  document.getElementById("wizardCardExisting").classList.toggle("selected", mode === "existing");
  
  const existingFields = document.getElementById("existingBlockyFields");
  if (existingFields) {
    existingFields.style.display = (mode === "existing" && isSetupMode) ? "block" : "none";
  }
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const errorBox = document.getElementById("authError");
  errorBox.style.display = "none";

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  if (isSetupMode) {
    const confirmPassword = document.getElementById("confirmPassword").value;
    if (password !== confirmPassword) {
      errorBox.textContent = "Passwords do not match";
      errorBox.style.display = "block";
      return;
    }
    if (password.length < 6) {
      errorBox.textContent = "Password must be at least 6 characters";
      errorBox.style.display = "block";
      return;
    }

    const blockyApiUrl = document.getElementById("blockyApiUrl") ? document.getElementById("blockyApiUrl").value.trim() : "http://localhost:4000";

    try {
      const res = await fetch("/api/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          integration_mode: selectedMode,
          blocky_api_url: blockyApiUrl
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Setup failed");
      window.location.href = "/";
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "block";
    }
  } else {
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Sign in failed");
      window.location.href = "/";
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "block";
    }
  }
}

document.addEventListener("DOMContentLoaded", checkAuthStatus);
