"""
Pirate Browser
- Selenium auto-detects Chrome, Edge or Firefox
- CustomTkinter dashboard sidebar
- Auto fuel/CO2 rebuy + auto depart on a timer
"""

import threading
import time
import json
import datetime
import tkinter as tk
import customtkinter as ctk
import urllib.request
import webbrowser
import base64
import os
from pathlib import Path

# Credential storage
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

CRED_SERVICE  = "PirateBrowser"
CRED_USER_KEY = "pb_email"
CRED_PASS_KEY = "pb_password"
CREDS_FILE    = Path(__file__).parent / ".pb_creds"

SETTINGS_FILE = Path(__file__).parent / "settings.json"
GAME_URL      = "https://shippingmanager.cc"

# ── VERSION & UPDATE CHECK ────────────────────────────────────────────────────
CURRENT_VERSION  = "0.0.1"
GITHUB_RELEASES  = "https://api.github.com/repos/PiratesTreasure/pirate-browser/releases/latest"
RELEASES_PAGE    = "https://github.com/PiratesTreasure/pirate-browser/releases/latest"


def check_for_updates():
    """Returns (latest_version, download_url) or (None, None) on failure."""
    try:
        req = urllib.request.Request(
            GITHUB_RELEASES,
            headers={"User-Agent": "PirateBrowser"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
        latest = data.get("tag_name", "").lstrip("v")
        return latest, RELEASES_PAGE
    except Exception:
        return None, None


def version_tuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def show_update_dialog(latest_version):
    """Shows a popup telling the user a new version is available."""
    popup = ctk.CTkToplevel()
    popup.title("Update Available")
    popup.geometry("380x200")
    popup.resizable(False, False)
    popup.configure(fg_color="#0a0f1e")
    popup.grab_set()
    popup.lift()

    ctk.CTkLabel(popup, text="🏴‍☠️  Update Available!",
                 font=("Segoe UI", 14, "bold"),
                 text_color="#0db8f4").pack(pady=(24, 6))

    ctk.CTkLabel(popup,
                 text=f"Version {latest_version} is available.\nYou are running {CURRENT_VERSION}.",
                 font=("Segoe UI", 11), text_color="#64748b",
                 justify="center").pack(pady=4)

    btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
    btn_frame.pack(pady=16)

    ctk.CTkButton(btn_frame, text="⬇  Download Update",
                  font=("Segoe UI", 11, "bold"),
                  fg_color="#0db8f4", hover_color="#0a9bd0",
                  width=160, height=36,
                  command=lambda: [webbrowser.open(RELEASES_PAGE), popup.destroy()]
                  ).pack(side="left", padx=6)

    ctk.CTkButton(btn_frame, text="Later",
                  font=("Segoe UI", 11),
                  fg_color="#1e2d4a", hover_color="#334155",
                  text_color="#e2e8f0", width=80, height=36,
                  command=popup.destroy
                  ).pack(side="left", padx=6)

DEFAULT_SETTINGS = {
    "fuel_mode":       "off",
    "fuel_threshold":  500,
    "fuel_min_cash":   1_000_000,
    "co2_mode":        "off",
    "co2_threshold":   10,
    "co2_min_cash":    1_000_000,
    "auto_depart":     False,
    "check_interval":  60,
}

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
            merged = DEFAULT_SETTINGS.copy()
            merged.update(saved)
            return merged
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(s):
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))

C = {
    "bg":    "#0a0f1e", "panel":  "#0d1530", "card":   "#111827",
    "border":"#1e2d4a", "accent": "#0db8f4", "green":  "#22c55e",
    "red":   "#ef4444", "yellow": "#f59e0b", "text":   "#e2e8f0",
    "dim":   "#64748b", "muted":  "#334155",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── BROWSER CONTROLLER ────────────────────────────────────────────────────────
# ── CREDENTIAL MANAGER ───────────────────────────────────────────────────────
class CredentialManager:
    """Saves/loads email+password using Windows Credential Manager if available,
    falling back to a simple encrypted local file."""

    @staticmethod
    def _obfuscate(text: str) -> str:
        """Basic obfuscation — not true encryption but better than plaintext."""
        key = b"PirateBrowserKey1234567890ABCDEF"
        data = text.encode()
        result = bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])
        return base64.b64encode(result).decode()

    @staticmethod
    def _deobfuscate(text: str) -> str:
        key = b"PirateBrowserKey1234567890ABCDEF"
        data = base64.b64decode(text.encode())
        result = bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])
        return result.decode()

    @classmethod
    def save(cls, email: str, password: str):
        """Save credentials — try keyring first, fall back to file."""
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(CRED_SERVICE, CRED_USER_KEY, email)
                keyring.set_password(CRED_SERVICE, CRED_PASS_KEY, password)
                # Mark that keyring was used
                CREDS_FILE.write_text(json.dumps({"backend": "keyring"}))
                return
            except Exception:
                pass
        # Fallback: obfuscated file
        data = {
            "backend":  "file",
            "email":    cls._obfuscate(email),
            "password": cls._obfuscate(password),
        }
        CREDS_FILE.write_text(json.dumps(data))

    @classmethod
    def load(cls) -> tuple:
        """Returns (email, password) or (None, None) if not saved."""
        if not CREDS_FILE.exists():
            return None, None
        try:
            data = json.loads(CREDS_FILE.read_text())
            if data.get("backend") == "keyring" and KEYRING_AVAILABLE:
                email    = keyring.get_password(CRED_SERVICE, CRED_USER_KEY)
                password = keyring.get_password(CRED_SERVICE, CRED_PASS_KEY)
                return email, password
            elif data.get("backend") == "file":
                email    = cls._deobfuscate(data["email"])
                password = cls._deobfuscate(data["password"])
                return email, password
        except Exception:
            pass
        return None, None

    @classmethod
    def clear(cls):
        """Remove all saved credentials."""
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(CRED_SERVICE, CRED_USER_KEY)
                keyring.delete_password(CRED_SERVICE, CRED_PASS_KEY)
            except Exception:
                pass
        if CREDS_FILE.exists():
            CREDS_FILE.unlink()


# ── LOGIN SCREEN ──────────────────────────────────────────────────────────────
class LoginScreen:
    """Shown on first launch or when credentials are cleared."""

    def __init__(self, on_login):
        self.on_login  = on_login   # callback(email, password, remember)
        self.root      = ctk.CTk()
        self.root.title("Pirate Browser — Login")
        self.root.geometry("380x480+0+0")
        self.root.resizable(False, False)
        self.root.configure(fg_color="#0a0f1e")
        self._build()

    def _build(self):
        # Header
        ctk.CTkLabel(self.root, text="🏴‍☠️",
                     font=("Segoe UI", 48)).pack(pady=(36, 4))
        ctk.CTkLabel(self.root, text="PIRATE BROWSER",
                     font=("Segoe UI", 16, "bold"),
                     text_color="#0db8f4").pack()
        ctk.CTkLabel(self.root, text="ShippingManager.cc Automation",
                     font=("Segoe UI", 10),
                     text_color="#334155").pack(pady=(2, 28))

        # Form
        form = ctk.CTkFrame(self.root, fg_color="#0d1530", corner_radius=12)
        form.pack(fill="x", padx=30)

        ctk.CTkLabel(form, text="Email", font=("Segoe UI", 10),
                     text_color="#64748b", anchor="w").pack(
            fill="x", padx=16, pady=(16, 2))
        self._email = ctk.CTkEntry(form, placeholder_text="your@email.com",
                                   font=("Segoe UI", 11), height=38,
                                   fg_color="#111827", text_color="#e2e8f0",
                                   border_color="#1e2d4a")
        self._email.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(form, text="Password", font=("Segoe UI", 10),
                     text_color="#64748b", anchor="w").pack(
            fill="x", padx=16, pady=(0, 2))
        self._password = ctk.CTkEntry(form, placeholder_text="••••••••",
                                      show="•", font=("Segoe UI", 11), height=38,
                                      fg_color="#111827", text_color="#e2e8f0",
                                      border_color="#1e2d4a")
        self._password.pack(fill="x", padx=16, pady=(0, 10))

        self._remember = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(form, text="Remember me", variable=self._remember,
                        font=("Segoe UI", 10), text_color="#64748b",
                        fg_color="#0db8f4", hover_color="#0a9bd0",
                        checkmark_color="white").pack(
            anchor="w", padx=16, pady=(0, 16))

        self._error_var = tk.StringVar(value="")
        self._error_lbl = ctk.CTkLabel(self.root, textvariable=self._error_var,
                                        font=("Segoe UI", 10),
                                        text_color="#ef4444")
        self._error_lbl.pack(pady=(8, 0))

        ctk.CTkButton(self.root, text="Login & Launch  🚀",
                      font=("Segoe UI", 12, "bold"),
                      fg_color="#0db8f4", hover_color="#0a9bd0",
                      height=42, corner_radius=8,
                      command=self._submit).pack(
            fill="x", padx=30, pady=12)

        # Bind Enter key
        self.root.bind("<Return>", lambda e: self._submit())

    def _submit(self):
        email    = self._email.get().strip()
        password = self._password.get().strip()
        if not email or not password:
            self._error_var.set("Please enter your email and password")
            return
        if "@" not in email:
            self._error_var.set("Please enter a valid email address")
            return
        self._error_var.set("")
        self.on_login(email, password, self._remember.get())
        self.root.destroy()

    def show_error(self, msg: str):
        self._error_var.set(msg)

    def run(self):
        self.root.mainloop()


class BrowserController:
    def __init__(self, log_fn):
        self.driver = None
        self.log    = log_fn
        self._lock  = threading.Lock()
        self.ready  = False

    def start(self):
        """Try Chrome → Edge → Firefox, use whichever is installed."""
        if self.ready:
            return   # prevent double-start
        launched = False
        errors   = []

        # ── Chrome ────────────────────────────────────────────────────────────
        if not launched:
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service as CS
                from selenium.webdriver.chrome.options import Options as CO
                from webdriver_manager.chrome import ChromeDriverManager
                opts = CO()
                opts.add_argument("--disable-blink-features=AutomationControlled")
                opts.add_experimental_option("excludeSwitches", ["enable-automation"])
                opts.add_experimental_option("useAutomationExtension", False)
                self.log("⬇ Trying Chrome…")
                self.driver = webdriver.Chrome(
                    service=CS(ChromeDriverManager().install()), options=opts)
                self.driver.set_window_position(380, 0)
                self.driver.set_window_size(1100, 860)
                self.driver.get(GAME_URL)
                self.ready   = True
                launched     = True
                self.log("✅ Chrome opened — please log in to the game")
            except Exception as e:
                errors.append(f"Chrome: {e}")

        # ── Edge ──────────────────────────────────────────────────────────────
        if not launched:
            try:
                from selenium import webdriver
                from selenium.webdriver.edge.service import Service as ES
                from selenium.webdriver.edge.options import Options as EO

                EDGE_BINARY  = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                # Look for msedgedriver.exe next to this script first, then in PATH
                local_driver = Path(__file__).parent / "msedgedriver.exe"
                edge_driver  = str(local_driver) if local_driver.exists() else "msedgedriver"

                opts = EO()
                opts.add_argument("--disable-blink-features=AutomationControlled")
                opts.add_argument("--no-sandbox")
                opts.binary_location = EDGE_BINARY

                self.log("⬇ Trying Edge…")
                svc = ES(edge_driver)
                self.driver = webdriver.Edge(service=svc, options=opts)
                self.driver.set_window_position(380, 0)
                self.driver.set_window_size(1100, 860)
                self.driver.get(GAME_URL)
                self.ready   = True
                launched     = True
                self.log("✅ Edge opened — please log in to the game")
            except Exception as e:
                errors.append(f"Edge: {e}")
                self.driver = None

        # ── Firefox ───────────────────────────────────────────────────────────
        if not launched:
            try:
                from selenium import webdriver
                from selenium.webdriver.firefox.service import Service as FS
                from selenium.webdriver.firefox.options import Options as FO
                from webdriver_manager.firefox import GeckoDriverManager
                opts = FO()
                opts.add_argument("--width=1100")
                opts.add_argument("--height=860")
                self.log("⬇ Trying Firefox…")
                self.driver = webdriver.Firefox(
                    service=FS(GeckoDriverManager().install()), options=opts)
                self.driver.set_window_position(380, 0)
                self.driver.set_window_size(1100, 860)
                self.driver.get(GAME_URL)
                self.ready   = True
                launched     = True
                self.log("✅ Firefox opened — please log in to the game")
            except Exception as e:
                errors.append(f"Firefox: {e}")

        if not launched:
            self.log("❌ No browser found. Please install Chrome, Edge or Firefox.")
            for err in errors:
                self.log(f"   {err}")

    def run_js(self, js: str):
        with self._lock:
            if not self.driver or not self.ready:
                return None
            try:
                return self.driver.execute_script(js)
            except Exception as e:
                self.log(f"⚠ JS error: {e}")
                return None

    def fetch_bunker(self):
        return self.run_js("""
            try {
                var app = document.querySelector('#app');
                if (!app || !app.__vue_app__) return null;
                var pinia = app.__vue_app__._context.provides.pinia
                         || app.__vue_app__.config.globalProperties.$pinia;
                if (!pinia) return null;
                var us = pinia._s.get('user');
                if (!us || !us.user) return null;
                var u = us.user;
                var st = us.userSettings || {};
                return {
                    fuel:    (u.fuel    || 0) / 1000,
                    co2:     (u.co2     || 0) / 1000,
                    cash:     u.cash   || 0,
                    maxFuel: (st.max_fuel || 1000000) / 1000,
                    maxCO2:  (st.max_co2  || 1000000) / 1000
                };
            } catch(e) { return null; }
        """)

    def fetch_prices(self):
        return self.run_js("""
            var done = false, result = null;
            fetch('https://shippingmanager.cc/api/bunker/get-prices', {
                method:'POST', credentials:'include',
                headers:{'Content-Type':'application/json'}, body:'{}'
            }).then(r=>r.json()).then(d=>{
                if (!d.data || !d.data.prices) return;
                var now = new Date();
                var h = now.getUTCHours();
                var slot = (h<10?'0':'')+h+':'+(now.getUTCMinutes()<30?'00':'30');
                var e = d.data.prices.find(p=>p.time===slot) || d.data.prices[0];
                result = {
                    fuelPrice: d.data.discounted_fuel !== undefined ? d.data.discounted_fuel : e.fuel_price,
                    co2Price:  d.data.discounted_co2  !== undefined ? d.data.discounted_co2  : e.co2_price
                };
            }).catch(()=>{}).finally(()=>{ done=true; });
            var t = Date.now();
            while (!done && Date.now()-t < 5000) {}
            return result;
        """)

    def fetch_prices_sync(self):
        """Fetch prices using synchronous XHR (more reliable in Selenium)."""
        return self.run_js("""
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/bunker/get-prices', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send('{}');
                var d = JSON.parse(xhr.responseText);
                if (!d.data || !d.data.prices) return null;
                var now = new Date();
                var h = now.getUTCHours();
                var slot = (h<10?'0':'')+h+':'+(now.getUTCMinutes()<30?'00':'30');
                var e = d.data.prices.find(function(p){ return p.time===slot; }) || d.data.prices[0];
                return {
                    fuelPrice: d.data.discounted_fuel !== undefined ? d.data.discounted_fuel : e.fuel_price,
                    co2Price:  d.data.discounted_co2  !== undefined ? d.data.discounted_co2  : e.co2_price
                };
            } catch(e) { return null; }
        """)

    def fetch_vessels_sync(self):
        return self.run_js("""
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/vessel/get-all-user-vessels', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send(JSON.stringify({include_routes:true}));
                var d = JSON.parse(xhr.responseText);
                return (d.data && d.data.user_vessels) ? d.data.user_vessels : [];
            } catch(e) { return []; }
        """)

    def purchase_fuel_sync(self, amount_tons):
        amount_kg = int(amount_tons * 1000)
        return self.run_js(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/bunker/purchase-fuel', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send(JSON.stringify({{amount:{amount_kg}}}));
                var d = JSON.parse(xhr.responseText);
                return d.user ? 'ok' : (d.error || 'failed');
            }} catch(e) {{ return 'error:'+e.message; }}
        """)

    def purchase_co2_sync(self, amount_tons):
        amount_kg = int(amount_tons * 1000)
        return self.run_js(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/bunker/purchase-co2', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send(JSON.stringify({{amount:{amount_kg}}}));
                var d = JSON.parse(xhr.responseText);
                return d.user ? 'ok' : (d.error || 'failed');
            }} catch(e) {{ return 'error:'+e.message; }}
        """)

    def depart_vessel_sync(self, vessel_id, speed, guards):
        return self.run_js(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/route/depart', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send(JSON.stringify({{
                    user_vessel_id:{vessel_id},
                    speed:{speed},
                    guards:{guards or 0},
                    history:0
                }}));
                var d = JSON.parse(xhr.responseText);
                if (d.data && d.data.depart_info) {{
                    var di = d.data.depart_info;
                    return {{
                        success:true,
                        income:  di.depart_income,
                        fuelUsed:di.fuel_usage   / 1000,
                        co2Used: di.co2_emission / 1000,
                        harbor:  di.harbor_fee
                    }};
                }}
                return {{success:false, error: d.error || 'unknown'}};
            }} catch(e) {{ return {{success:false, error:e.message}}; }}
        """)

    def is_logged_in(self):
        result = self.run_js("""
            try {
                var app = document.querySelector('#app');
                if (!app || !app.__vue_app__) return false;
                var pinia = app.__vue_app__._context.provides.pinia
                         || app.__vue_app__.config.globalProperties.$pinia;
                if (!pinia) return false;
                var us = pinia._s.get('user');
                return !!(us && us.user && us.user.id);
            } catch(e) { return false; }
        """)
        return bool(result)

    def auto_login(self, email: str, password: str) -> bool:
        """Attempts to log in using the game's login form. Returns True on success."""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.keys import Keys

            # Navigate to login page
            self.driver.get("https://shippingmanager.cc/login")
            time.sleep(2)

            wait = WebDriverWait(self.driver, 10)

            # Fill email
            email_field = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='email' i], input[placeholder*='Email' i]")))
            email_field.clear()
            email_field.send_keys(email)
            time.sleep(0.5)

            # Fill password
            pass_field = self.driver.find_element(
                By.CSS_SELECTOR, "input[type='password']")
            pass_field.clear()
            pass_field.send_keys(password)
            time.sleep(0.5)

            # Try clicking submit button — multiple strategies
            clicked = False

            # Strategy 1: button[type=submit]
            if not clicked:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    btn.click()
                    clicked = True
                except Exception:
                    pass

            # Strategy 2: any button containing login/sign in text
            if not clicked:
                try:
                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        txt = btn.text.lower()
                        if any(w in txt for w in ["login", "sign in", "log in", "submit"]):
                            btn.click()
                            clicked = True
                            break
                except Exception:
                    pass

            # Strategy 3: press Enter on the password field
            if not clicked:
                try:
                    pass_field.send_keys(Keys.RETURN)
                    clicked = True
                except Exception:
                    pass

            if not clicked:
                self.log("⚠ Could not find login button — trying Enter key")
                pass_field.send_keys(Keys.RETURN)

            # Wait for redirect away from login page
            time.sleep(4)
            success = "login" not in self.driver.current_url
            return success

        except Exception as e:
            self.log(f"⚠ Auto-login error: {e}")
            return False

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass


# ── AUTO MANAGER ──────────────────────────────────────────────────────────────
class AutoManager:
    def __init__(self, browser, get_settings, log_fn,
                 on_bunker, on_prices, on_depart):
        self.browser      = browser
        self.get_settings = get_settings
        self.log          = log_fn
        self.on_bunker    = on_bunker
        self.on_prices    = on_prices
        self.on_depart    = on_depart
        self._running     = False

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def run_now(self):
        threading.Thread(target=self._cycle, daemon=True).start()

    def _loop(self):
        # Wait for browser to be ready first
        for _ in range(60):
            if not self._running: return
            if self.browser.ready: break
            time.sleep(1)
        else:
            self.log("❌ Browser never became ready"); return

        self.log("⏳ Waiting for login…")
        for _ in range(180):
            if not self._running: return
            if self.browser.is_logged_in(): break
            time.sleep(2)
        else:
            self.log("❌ Timed out waiting for login"); return

        self.log("✅ Logged in — auto-manager active")
        while self._running:
            self._cycle()
            s = self.get_settings()
            secs = int(s.get("check_interval", 60))
            for _ in range(secs * 2):
                if not self._running: return
                time.sleep(0.5)

    def _cycle(self):
        try:
            s      = self.get_settings()
            bunker = self.browser.fetch_bunker()
            prices = self.browser.fetch_prices_sync()

            if bunker: self.on_bunker(bunker)
            if prices: self.on_prices(prices)

            if not bunker or not prices:
                self.log("⚠ Couldn't read game data — is game loaded?")
                return

            fp   = prices.get("fuelPrice")
            cp   = prices.get("co2Price")
            cash = bunker.get("cash", 0)
            fuel = bunker.get("fuel", 0)
            co2  = bunker.get("co2",  0)
            mf   = bunker.get("maxFuel", 0)
            mc   = bunker.get("maxCO2",  0)

            # ── Fuel ──────────────────────────────────────────────────────────
            if s["fuel_mode"] != "off" and fp is not None:
                ft    = s["fuel_threshold"]
                space = mf - fuel
                afford = max(0, cash - s["fuel_min_cash"]) / fp if fp > 0 else 0
                if fp <= ft and space >= 1:
                    amt = min(int(space), int(afford))
                    if amt > 0:
                        self.log(f"⛽ Buying {amt:,}t fuel @ ${fp}/t")
                        r = self.browser.purchase_fuel_sync(amt)
                        if r == "ok":
                            self.log(f"✅ Fuel bought: {amt:,}t")
                            b2 = self.browser.fetch_bunker()
                            if b2:
                                self.on_bunker(b2)
                                cash = b2["cash"]; fuel = b2["fuel"]
                        else:
                            self.log(f"❌ Fuel failed: {r}")
                else:
                    self.log(f"⛽ Fuel ${fp}/t  threshold ${ft} — skip")

            # ── CO2 ───────────────────────────────────────────────────────────
            if s["co2_mode"] != "off" and cp is not None:
                ct    = s["co2_threshold"]
                space = mc - co2
                afford = max(0, cash - s["co2_min_cash"]) / cp if cp > 0 else 0
                if cp <= ct and space >= 1:
                    amt = min(int(space), int(afford))
                    if amt > 0:
                        self.log(f"🌿 Buying {amt:,}t CO2 @ ${cp}/t")
                        r = self.browser.purchase_co2_sync(amt)
                        if r == "ok":
                            self.log(f"✅ CO2 bought: {amt:,}t")
                            b2 = self.browser.fetch_bunker()
                            if b2:
                                self.on_bunker(b2)
                                cash = b2["cash"]
                        else:
                            self.log(f"❌ CO2 failed: {r}")
                else:
                    self.log(f"🌿 CO2 ${cp}/t  threshold ${ct} — skip")

            # ── Depart ────────────────────────────────────────────────────────
            if s["auto_depart"]:
                vessels = self.browser.fetch_vessels_sync()
                ready   = [v for v in (vessels or [])
                           if v.get("status") == "port"
                           and not v.get("is_parked")
                           and v.get("route_destination")]
                self.log(f"🚢 {len(ready)} vessel(s) ready")
                for v in ready:
                    r = self.browser.depart_vessel_sync(
                        v["id"], v.get("route_speed", 20), v.get("route_guards", 0))
                    if isinstance(r, dict) and r.get("success"):
                        entry = {
                            "timestamp": int(time.time() * 1000),
                            "vessel":    v.get("name", "?"),
                            "income":    r.get("income", 0),
                            "fuelUsed":  r.get("fuelUsed", 0),
                            "co2Used":   r.get("co2Used", 0),
                        }
                        self.on_depart(entry)
                        self.log(f"✅ Departed {v.get('name')} +${entry['income']:,}")
                    else:
                        err = r.get("error","?") if isinstance(r,dict) else r
                        self.log(f"❌ Depart failed {v.get('name')}: {err}")
                    time.sleep(0.5)
        except Exception as e:
            self.log(f"❌ Cycle error: {e}")


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
def fmt_cash(n):
    try:
        v = int(n)
        if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
        if v >= 1_000:     return f"${v/1_000:.0f}K"
        return f"${v}"
    except: return "—"

def fmt_ts(ts_ms):
    try:
        return datetime.datetime.fromtimestamp(ts_ms/1000).strftime("%H:%M:%S")
    except: return "—"


class PirateBrowserDashboard:
    def __init__(self, browser, manager, get_settings, save_settings_fn):
        self.browser          = browser
        self.manager          = manager
        self.get_settings     = get_settings
        self.save_settings_fn = save_settings_fn
        self._session_income  = 0
        self._session_departs = 0

        self.root = ctk.CTk()
        self.root.title("Pirate Browser")
        self.root.geometry("380x900+0+0")
        self.root.resizable(False, True)
        self.root.configure(fg_color=C["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self.root, fg_color=C["panel"], height=54, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🏴‍☠️  PIRATE BROWSER",
                     font=("Segoe UI",13,"bold"),
                     text_color=C["accent"]).place(relx=0.5,rely=0.5,anchor="center")

        # Tabs
        tab_bar = ctk.CTkFrame(self.root, fg_color=C["panel"], height=34, corner_radius=0)
        tab_bar.pack(fill="x"); tab_bar.pack_propagate(False)
        self._pages = {}; self._tab_btns = {}
        for tid, label in [("status","📊 Status"),("logs","📋 Logs"),("settings","⚙ Settings")]:
            b = ctk.CTkButton(tab_bar, text=label, font=("Segoe UI",10),
                              width=90, height=30, corner_radius=0,
                              fg_color="transparent", hover_color=C["border"],
                              text_color=C["dim"],
                              command=lambda t=tid: self._show(t))
            b.pack(side="left", padx=1)
            self._tab_btns[tid] = b

        self._content = ctk.CTkFrame(self.root, fg_color=C["bg"], corner_radius=0)
        self._content.pack(fill="both", expand=True)

        self._build_status()
        self._build_logs()
        self._build_settings()
        self._show("status")

        self._status_var = tk.StringVar(value="Starting…")
        ctk.CTkLabel(self.root, textvariable=self._status_var,
                     font=("Consolas",9), text_color=C["dim"],
                     anchor="w").pack(fill="x", padx=8, pady=2)

    def _show(self, tab_id):
        for tid, page in self._pages.items():
            if tid == tab_id:
                page.pack(fill="both", expand=True)
                self._tab_btns[tid].configure(text_color=C["accent"], fg_color=C["border"])
            else:
                page.pack_forget()
                self._tab_btns[tid].configure(text_color=C["dim"], fg_color="transparent")

    def _sec(self, parent, title):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=(10,2))
        ctk.CTkLabel(f, text=title.upper(), font=("Segoe UI",8,"bold"),
                     text_color=C["muted"]).pack(side="left")
        ctk.CTkFrame(f, height=1, fg_color=C["border"]).pack(
            side="left", fill="x", expand=True, padx=(6,0))

    def _build_status(self):
        page = ctk.CTkScrollableFrame(self._content, fg_color=C["bg"],
                                       scrollbar_button_color=C["border"])
        self._pages["status"] = page

        def stat(label, var):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=label, font=("Segoe UI",10),
                         text_color=C["dim"]).pack(side="left", padx=10, pady=8)
            lbl = ctk.CTkLabel(f, textvariable=var, font=("Consolas",11,"bold"),
                               text_color=C["accent"])
            lbl.pack(side="right", padx=10)
            return lbl

        self._sec(page, "Bunker")
        self._v_fuel = tk.StringVar(value="—")
        self._v_co2  = tk.StringVar(value="—")
        self._v_cash = tk.StringVar(value="—")
        stat("⛽  Fuel",  self._v_fuel)
        stat("🌿  CO2",   self._v_co2)
        stat("💰  Cash",  self._v_cash)

        self._sec(page, "Market Prices")
        self._v_fp = tk.StringVar(value="—")
        self._v_cp = tk.StringVar(value="—")
        self._lbl_fp = stat("⛽  Fuel Price", self._v_fp)
        self._lbl_cp = stat("🌿  CO2 Price",  self._v_cp)

        self._sec(page, "Session")
        self._v_session = tk.StringVar(value="No departures yet")
        ctk.CTkLabel(page, textvariable=self._v_session,
                     font=("Segoe UI",10), text_color=C["dim"],
                     anchor="w", wraplength=340).pack(fill="x", padx=12, pady=4)

        self._sec(page, "Actions")
        ctk.CTkButton(page, text="▶  Run Check Now",
                      font=("Segoe UI",11,"bold"),
                      fg_color=C["accent"], hover_color="#0a9bd0",
                      height=38, corner_radius=8,
                      command=self.manager.run_now
                      ).pack(fill="x", padx=10, pady=3)
        ctk.CTkButton(page, text="🔄  Refresh Status",
                      font=("Segoe UI",10),
                      fg_color=C["border"], hover_color=C["card"],
                      text_color=C["text"], height=32, corner_radius=8,
                      command=self._refresh
                      ).pack(fill="x", padx=10, pady=3)

    def _refresh(self):
        def _do():
            b = self.browser.fetch_bunker()
            p = self.browser.fetch_prices_sync()
            if b: self.on_bunker(b)
            if p: self.on_prices(p)
        threading.Thread(target=_do, daemon=True).start()

    def _build_logs(self):
        page = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)
        self._pages["logs"] = page
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(hdr, text="DEPARTURE LOG", font=("Segoe UI",8,"bold"),
                     text_color=C["muted"]).pack(side="left")
        ctk.CTkButton(hdr, text="Clear", font=("Segoe UI",9), width=48, height=22,
                      fg_color=C["red"], hover_color="#b91c1c", text_color="white",
                      corner_radius=4, command=self._clear_logs).pack(side="right")
        self._log_scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"], scrollbar_button_color=C["border"])
        self._log_scroll.pack(fill="both", expand=True, padx=6)

    def _add_log(self, entry):
        row = ctk.CTkFrame(self._log_scroll, fg_color=C["card"], corner_radius=6)
        row.pack(fill="x", pady=2)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(5,0))
        ctk.CTkLabel(top, text=f"{fmt_ts(entry.get('timestamp',0))}  {entry.get('vessel','?')}",
                     font=("Segoe UI",10), text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(top, text=f"+${entry.get('income',0):,}",
                     font=("Consolas",10,"bold"), text_color=C["green"]).pack(side="right")
        bot = ctk.CTkFrame(row, fg_color="transparent")
        bot.pack(fill="x", padx=8, pady=(0,5))
        ctk.CTkLabel(bot, text=f"⛽ {entry.get('fuelUsed',0):.0f}t  🌿 {entry.get('co2Used',0):.0f}t",
                     font=("Segoe UI",9), text_color=C["muted"]).pack(side="left")

    def _clear_logs(self):
        for w in self._log_scroll.winfo_children(): w.destroy()
        self._session_income = 0; self._session_departs = 0
        self._v_session.set("No departures yet")

    def _build_settings(self):
        page = ctk.CTkScrollableFrame(self._content, fg_color=C["bg"],
                                       scrollbar_button_color=C["border"])
        self._pages["settings"] = page
        s = self.get_settings()

        def field(lbl, var, width=90):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI",10),
                         text_color=C["text"]).pack(side="left", padx=10, pady=7)
            ctk.CTkEntry(f, textvariable=var, width=width,
                         font=("Consolas",10), fg_color=C["border"],
                         text_color=C["text"], border_color=C["border"]
                         ).pack(side="right", padx=10, pady=5)

        def toggle(lbl, var):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI",10),
                         text_color=C["text"]).pack(side="left", padx=10, pady=7)
            ctk.CTkSwitch(f, variable=var, text="", width=40,
                          fg_color=C["border"], progress_color=C["green"],
                          button_color=C["text"]).pack(side="right", padx=10)

        def dropdown(lbl, var, values):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI",10),
                         text_color=C["text"]).pack(side="left", padx=10, pady=7)
            ctk.CTkOptionMenu(f, variable=var, values=values,
                              font=("Segoe UI",10), width=110,
                              fg_color=C["border"], button_color=C["accent"],
                              text_color=C["text"]).pack(side="right", padx=10, pady=5)

        self._sec(page, "⛽ Fuel Auto-Rebuy")
        self._sv_fm  = tk.StringVar(value=s["fuel_mode"])
        self._sv_ft  = tk.StringVar(value=str(s["fuel_threshold"]))
        self._sv_fc  = tk.StringVar(value=str(s["fuel_min_cash"]))
        dropdown("Mode",                 self._sv_fm, ["off","basic","intelligent"])
        field   ("Price Threshold ($/t)",self._sv_ft)
        field   ("Min Cash Reserve ($)", self._sv_fc, 110)

        self._sec(page, "🌿 CO2 Auto-Rebuy")
        self._sv_cm  = tk.StringVar(value=s["co2_mode"])
        self._sv_ct  = tk.StringVar(value=str(s["co2_threshold"]))
        self._sv_cc  = tk.StringVar(value=str(s["co2_min_cash"]))
        dropdown("Mode",                 self._sv_cm, ["off","basic"])
        field   ("Price Threshold ($/t)",self._sv_ct)
        field   ("Min Cash Reserve ($)", self._sv_cc, 110)

        self._sec(page, "🚢 Auto-Depart")
        self._sv_ad  = tk.BooleanVar(value=s["auto_depart"])
        self._sv_ci  = tk.StringVar(value=str(s["check_interval"]))
        toggle("Enable Auto-Depart",    self._sv_ad)
        field ("Check Interval (secs)", self._sv_ci)

        ctk.CTkButton(page, text="💾  Save Settings",
                      font=("Segoe UI",11,"bold"),
                      fg_color=C["green"], hover_color="#16a34a",
                      height=38, corner_radius=8,
                      command=self._save
                      ).pack(fill="x", padx=10, pady=14)

        self._sec(page, "🔐 Account")
        ctk.CTkButton(page, text="🗑  Forget Saved Login",
                      font=("Segoe UI", 10),
                      fg_color=C["red"], hover_color="#b91c1c",
                      text_color="white", height=34, corner_radius=8,
                      command=self._forget_login
                      ).pack(fill="x", padx=10, pady=4)

    def _forget_login(self):
        CredentialManager.clear()
        self.set_status("✅ Saved login cleared — you'll be asked next launch")

    def _save(self):
        try:
            s = self.get_settings()
            s.update({
                "fuel_mode":      self._sv_fm.get(),
                "fuel_threshold": int(self._sv_ft.get()),
                "fuel_min_cash":  int(self._sv_fc.get()),
                "co2_mode":       self._sv_cm.get(),
                "co2_threshold":  int(self._sv_ct.get()),
                "co2_min_cash":   int(self._sv_cc.get()),
                "auto_depart":    self._sv_ad.get(),
                "check_interval": int(self._sv_ci.get()),
            })
            self.save_settings_fn(s)
            self.set_status("✅ Settings saved")
        except ValueError as e:
            self.set_status(f"❌ Bad value: {e}")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def on_bunker(self, d):
        def _u():
            self._v_fuel.set(f"{d.get('fuel',0):,.0f} / {d.get('maxFuel',0):,.0f} t")
            self._v_co2.set( f"{d.get('co2', 0):,.0f} / {d.get('maxCO2', 0):,.0f} t")
            self._v_cash.set(fmt_cash(d.get("cash",0)))
        self.root.after(0, _u)

    def on_prices(self, d):
        def _u():
            s  = self.get_settings()
            fp = d.get("fuelPrice")
            cp = d.get("co2Price")
            if fp is not None:
                self._v_fp.set(f"${fp}/t")
                self._lbl_fp.configure(
                    text_color=C["green"] if fp <= s["fuel_threshold"] else C["red"])
            if cp is not None:
                self._v_cp.set(f"${cp}/t")
                self._lbl_cp.configure(
                    text_color=C["green"] if cp <= s["co2_threshold"] else C["red"])
        self.root.after(0, _u)

    def on_depart(self, entry):
        self._session_departs += 1
        self._session_income  += entry.get("income", 0)
        def _u():
            self._v_session.set(
                f"{self._session_departs} departure(s)  •  +${self._session_income:,}")
            self._add_log(entry)
        self.root.after(0, _u)

    def set_status(self, msg):
        self.root.after(0, lambda: self._status_var.set(msg))

    def log(self, msg):
        self.set_status(msg)
        print(f"[Pirate Browser] {msg}")

    def _on_close(self):
        self.browser.close()
        self.manager.stop()
        self.root.destroy()

    def run(self):
        # Check for updates in background so it doesn't slow startup
        threading.Thread(target=self._check_updates, daemon=True).start()
        self.root.mainloop()

    def _check_updates(self):
        time.sleep(3)   # wait for UI to fully load first
        latest, url = check_for_updates()
        if latest and version_tuple(latest) > version_tuple(CURRENT_VERSION):
            self.root.after(0, lambda: show_update_dialog(latest))


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    settings = load_settings()
    def get_s():    return settings
    def save_s(s):  settings.update(s); save_settings(s)

    dash_ref    = [None]
    saved_creds = [None, None]   # [email, password]

    def log_fn(msg):
        if dash_ref[0]:
            dash_ref[0].log(msg)  # dashboard.log() handles the print
        else:
            print(f"[Pirate Browser] {msg}")

    browser = BrowserController(log_fn)
    manager = AutoManager(
        browser      = browser,
        get_settings = get_s,
        log_fn       = log_fn,
        on_bunker    = lambda d: dash_ref[0].on_bunker(d)  if dash_ref[0] else None,
        on_prices    = lambda d: dash_ref[0].on_prices(d)  if dash_ref[0] else None,
        on_depart    = lambda d: dash_ref[0].on_depart(d)  if dash_ref[0] else None,
    )

    # ── Check for saved credentials ───────────────────────────────────────────
    email, password = CredentialManager.load()

    if not email or not password:
        # No saved creds — show login screen first
        def on_login(em, pw, remember):
            saved_creds[0] = em
            saved_creds[1] = pw
            if remember:
                CredentialManager.save(em, pw)

        login = LoginScreen(on_login)
        login.run()

        # If user closed login without submitting, exit
        if not saved_creds[0]:
            return

        email    = saved_creds[0]
        password = saved_creds[1]
    else:
        log_fn("🔐 Saved credentials found — auto-login enabled")

    # ── Start browser, auto-login, then manager — all in one thread ─────────
    def start_browser():
        browser.start()
        if browser.ready and email and password:
            log_fn("🔐 Attempting auto-login…")
            success = browser.auto_login(email, password)
            if success:
                log_fn("✅ Auto-login successful")
            else:
                log_fn("⚠ Auto-login failed — please log in manually")
        # Start manager only after browser is ready
        manager.start()

    threading.Thread(target=start_browser, daemon=True).start()

    dash = PirateBrowserDashboard(browser, manager, get_s, save_s)
    dash_ref[0] = dash
    dash.run()

if __name__ == "__main__":
    main()
