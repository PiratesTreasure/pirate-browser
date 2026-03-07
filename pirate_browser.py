"""
Pirate Browser
- Multiple accounts running simultaneously
- Each account has its own browser window, settings and logs
- Selenium auto-detects Chrome, Edge or Firefox
- CustomTkinter dashboard with per-account tabs
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

# ── DATA DIRECTORY ────────────────────────────────────────────────────────────
def _get_data_dir() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data:
        d = Path(app_data) / "PirateBrowser"
    else:
        d = Path(__file__).parent
    d.mkdir(parents=True, exist_ok=True)
    return d

DATA_DIR = _get_data_dir()

# ── KEYRING ───────────────────────────────────────────────────────────────────
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# ── VERSION & UPDATE ──────────────────────────────────────────────────────────
CURRENT_VERSION = "0.0.3"
GITHUB_RELEASES = "https://api.github.com/repos/PiratesTreasure/pirate-browser/releases/latest"
RELEASES_PAGE   = "https://github.com/PiratesTreasure/pirate-browser/releases/latest"
GAME_URL        = "https://shippingmanager.cc"

def check_for_updates():
    try:
        req = urllib.request.Request(GITHUB_RELEASES,
                                     headers={"User-Agent": "PirateBrowser"})
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
                  command=popup.destroy).pack(side="left", padx=6)

# ── COLOURS ───────────────────────────────────────────────────────────────────
C = {
    "bg":    "#0a0f1e", "panel":  "#0d1530", "card":   "#111827",
    "border":"#1e2d4a", "accent": "#0db8f4", "green":  "#22c55e",
    "red":   "#ef4444", "yellow": "#f59e0b", "text":   "#e2e8f0",
    "dim":   "#64748b", "muted":  "#334155",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── DEFAULT SETTINGS ──────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "fuel_mode":        "off",
    "fuel_threshold":   500,
    "fuel_min_cash":    1_000_000,
    "co2_mode":         "off",
    "co2_threshold":    10,
    "co2_min_cash":     1_000_000,
    "auto_depart":      False,
    "check_interval":   60,
    "min_utilization":  50,
    "low_util_action":  "skip",
}

# ── ACCOUNT MANAGER ───────────────────────────────────────────────────────────
ACCOUNTS_FILE = DATA_DIR / "accounts.json"

class AccountManager:
    """Manages list of accounts and their per-account settings/credentials."""

    @staticmethod
    def load_accounts() -> list:
        if ACCOUNTS_FILE.exists():
            try:
                return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    @staticmethod
    def save_accounts(accounts: list):
        ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2), encoding="utf-8")

    @staticmethod
    def add_account(name: str) -> dict:
        accounts = AccountManager.load_accounts()
        account_id = f"account_{int(time.time())}"
        account = {"id": account_id, "name": name}
        accounts.append(account)
        AccountManager.save_accounts(accounts)
        return account

    @staticmethod
    def remove_account(account_id: str):
        accounts = AccountManager.load_accounts()
        accounts = [a for a in accounts if a["id"] != account_id]
        AccountManager.save_accounts(accounts)
        # Clean up settings and creds
        sf = DATA_DIR / f"settings_{account_id}.json"
        cf = DATA_DIR / f".creds_{account_id}"
        for f in [sf, cf]:
            if f.exists():
                f.unlink()

    @staticmethod
    def get_settings(account_id: str) -> dict:
        sf = DATA_DIR / f"settings_{account_id}.json"
        if sf.exists():
            try:
                saved = json.loads(sf.read_text(encoding="utf-8"))
                merged = DEFAULT_SETTINGS.copy()
                merged.update(saved)
                return merged
            except Exception:
                pass
        return DEFAULT_SETTINGS.copy()

    @staticmethod
    def save_settings(account_id: str, settings: dict):
        sf = DATA_DIR / f"settings_{account_id}.json"
        sf.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    @staticmethod
    def save_credentials(account_id: str, email: str, password: str):
        key = f"PirateBrowser_{account_id}"
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(key, "email", email)
                keyring.set_password(key, "password", password)
                cf = DATA_DIR / f".creds_{account_id}"
                cf.write_text(json.dumps({"backend": "keyring"}), encoding="utf-8")
                return
            except Exception:
                pass
        # Fallback obfuscated file
        xkey = b"PirateBrowserKey1234567890ABCDEF"
        def obf(t):
            d = t.encode()
            return base64.b64encode(bytes([d[i] ^ xkey[i % len(xkey)] for i in range(len(d))])).decode()
        cf = DATA_DIR / f".creds_{account_id}"
        cf.write_text(json.dumps({"backend": "file", "email": obf(email), "password": obf(password)}), encoding="utf-8")

    @staticmethod
    def load_credentials(account_id: str):
        cf = DATA_DIR / f".creds_{account_id}"
        if not cf.exists():
            return None, None
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
            if data.get("backend") == "keyring" and KEYRING_AVAILABLE:
                key = f"PirateBrowser_{account_id}"
                return keyring.get_password(key, "email"), keyring.get_password(key, "password")
            elif data.get("backend") == "file":
                xkey = b"PirateBrowserKey1234567890ABCDEF"
                def deobf(t):
                    d = base64.b64decode(t.encode())
                    return bytes([d[i] ^ xkey[i % len(xkey)] for i in range(len(d))]).decode()
                return deobf(data["email"]), deobf(data["password"])
        except Exception:
            pass
        return None, None

    @staticmethod
    def clear_credentials(account_id: str):
        if KEYRING_AVAILABLE:
            try:
                key = f"PirateBrowser_{account_id}"
                keyring.delete_password(key, "email")
                keyring.delete_password(key, "password")
            except Exception:
                pass
        cf = DATA_DIR / f".creds_{account_id}"
        if cf.exists():
            cf.unlink()


# ── LOGIN SCREEN ──────────────────────────────────────────────────────────────
def show_login_dialog(parent, account_name: str, on_login):
    """Shows a modal login dialog on top of the main window."""
    popup = ctk.CTkToplevel(parent)
    popup.title(f"Pirate Browser — {account_name}")
    popup.geometry("380x460")
    popup.resizable(False, False)
    popup.configure(fg_color="#0a0f1e")
    popup.grab_set()
    popup.lift()
    popup.focus_force()

    submitted = [False]

    ctk.CTkLabel(popup, text="🏴‍☠️",
                 font=("Segoe UI", 48)).pack(pady=(28, 4))
    ctk.CTkLabel(popup, text="PIRATE BROWSER",
                 font=("Segoe UI", 16, "bold"),
                 text_color="#0db8f4").pack()
    ctk.CTkLabel(popup, text=account_name,
                 font=("Segoe UI", 11),
                 text_color="#334155").pack(pady=(2, 16))

    form = ctk.CTkFrame(popup, fg_color="#0d1530", corner_radius=12)
    form.pack(fill="x", padx=30)

    ctk.CTkLabel(form, text="Email", font=("Segoe UI", 10),
                 text_color="#64748b", anchor="w").pack(fill="x", padx=16, pady=(16, 2))
    email_entry = ctk.CTkEntry(form, placeholder_text="your@email.com",
                               font=("Segoe UI", 11), height=38,
                               fg_color="#111827", text_color="#e2e8f0",
                               border_color="#1e2d4a")
    email_entry.pack(fill="x", padx=16, pady=(0, 10))

    ctk.CTkLabel(form, text="Password", font=("Segoe UI", 10),
                 text_color="#64748b", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
    pass_entry = ctk.CTkEntry(form, placeholder_text="••••••••",
                              show="•", font=("Segoe UI", 11), height=38,
                              fg_color="#111827", text_color="#e2e8f0",
                              border_color="#1e2d4a")
    pass_entry.pack(fill="x", padx=16, pady=(0, 10))

    remember_var = tk.BooleanVar(value=True)
    ctk.CTkCheckBox(form, text="Remember me", variable=remember_var,
                    font=("Segoe UI", 10), text_color="#64748b",
                    fg_color="#0db8f4", checkmark_color="white").pack(
        anchor="w", padx=16, pady=(0, 16))

    error_var = tk.StringVar(value="")
    ctk.CTkLabel(popup, textvariable=error_var,
                 font=("Segoe UI", 10), text_color="#ef4444").pack(pady=(6, 0))

    def _submit():
        email    = email_entry.get().strip()
        password = pass_entry.get().strip()
        if not email or not password:
            error_var.set("Please enter your email and password")
            return
        if "@" not in email:
            error_var.set("Please enter a valid email address")
            return
        submitted[0] = True
        on_login(email, password, remember_var.get())
        popup.destroy()

    ctk.CTkButton(popup, text="Login & Launch  🚀",
                  font=("Segoe UI", 12, "bold"),
                  fg_color="#0db8f4", hover_color="#0a9bd0",
                  height=42, corner_radius=8,
                  command=_submit).pack(fill="x", padx=30, pady=10)

    popup.bind("<Return>", lambda e: _submit())
    parent.wait_window(popup)
    return submitted[0]


# ── SHARED BROWSER (single window, one tab per account) ──────────────────────
class SharedBrowser:
    """One browser window shared across all accounts. Each account gets a tab."""
    _instance = None
    _lock     = threading.Lock()

    @classmethod
    def get(cls, log_fn=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(log_fn)
            return cls._instance

    def __init__(self, log_fn):
        self.driver   = None
        self.log      = log_fn or print
        self._lock    = threading.Lock()
        self.ready    = False

    def start(self):
        if self.ready:
            return
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
                self.ready   = True
                launched     = True
                self.log("✅ Chrome opened")
            except Exception as e:
                errors.append(f"Chrome: {e}")

        # ── Edge ──────────────────────────────────────────────────────────────
        if not launched:
            try:
                from selenium import webdriver
                from selenium.webdriver.edge.service import Service as ES
                from selenium.webdriver.edge.options import Options as EO
                EDGE_BINARY  = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                local_driver = Path(__file__).parent / "msedgedriver.exe"
                edge_driver  = str(local_driver) if local_driver.exists() else "msedgedriver"
                opts = EO()
                opts.add_argument("--disable-blink-features=AutomationControlled")
                opts.add_argument("--no-sandbox")
                opts.binary_location = EDGE_BINARY
                self.log("⬇ Trying Edge…")
                self.driver = webdriver.Edge(service=ES(edge_driver), options=opts)
                self.driver.set_window_position(380, 0)
                self.driver.set_window_size(1100, 860)
                self.ready   = True
                launched     = True
                self.log("✅ Edge opened")
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
                self.log("⬇ Trying Firefox…")
                self.driver = webdriver.Firefox(
                    service=FS(GeckoDriverManager().install()), options=opts)
                self.driver.set_window_position(380, 0)
                self.driver.set_window_size(1100, 860)
                self.ready   = True
                launched     = True
                self.log("✅ Firefox opened")
            except Exception as e:
                errors.append(f"Firefox: {e}")

        if not launched:
            self.log("❌ No browser found. Please install Chrome, Edge or Firefox.")
            return

        # Open initial tab
        self.driver.get(GAME_URL)

    def new_tab(self) -> str:
        """Opens a new browser tab and returns its handle."""
        with self._lock:
            self.driver.execute_script("window.open(arguments[0], '_blank');", GAME_URL)
            time.sleep(0.5)
            return self.driver.window_handles[-1]

    def close(self):
        """Close just this account's tab."""
        try:
            if self.driver and self.tab_handle:
                self._switch()
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                # Don't quit the whole browser — SharedBrowser.close() does that
        except Exception:
            pass
        SharedBrowser._instance = None


# ── BROWSER CONTROLLER ────────────────────────────────────────────────────────
class BrowserController:
    """Controls one tab within the shared browser window."""

    def __init__(self, log_fn, account_id: str, shared: SharedBrowser, tab_handle: str = None):
        self.shared      = shared
        self.log         = log_fn
        self._lock       = threading.Lock()
        self.ready       = False
        self.account_id  = account_id
        self.tab_handle  = tab_handle   # set after tab is opened

    @property
    def driver(self):
        return self.shared.driver

    def _switch(self):
        """Switch browser focus to this account's tab."""
        if self.tab_handle and self.driver:
            try:
                self.driver.switch_to.window(self.tab_handle)
            except Exception:
                pass

    def start(self):
        """Wait for shared browser to be ready, then set up this account's tab."""
        for _ in range(60):
            if self.shared.ready: break
            time.sleep(1)
        if not self.shared.ready:
            self.log("❌ Browser never became ready")
            return
        self.ready = True
        self.log("✅ Browser tab ready — please log in")

    def run_js(self, js: str):
        with self._lock:
            if not self.driver or not self.ready:
                return None
            try:
                self._switch()
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
                var u = us.user; var st = us.userSettings || {};
                return {
                    fuel:    (u.fuel    || 0) / 1000,
                    co2:     (u.co2     || 0) / 1000,
                    cash:     u.cash   || 0,
                    maxFuel: (st.max_fuel || 1000000) / 1000,
                    maxCO2:  (st.max_co2  || 1000000) / 1000
                };
            } catch(e) { return null; }
        """)

    def fetch_prices_sync(self):
        return self.run_js("""
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/bunker/get-prices', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send('{}');
                var d = JSON.parse(xhr.responseText);
                if (!d.data || !d.data.prices) return null;
                var now = new Date(); var h = now.getUTCHours();
                var slot = (h<10?'0':'')+h+':'+(now.getUTCMinutes()<30?'00':'30');
                var e = d.data.prices.find(function(p){return p.time===slot;}) || d.data.prices[0];
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
                var vessels = (d.data && d.data.user_vessels) ? d.data.user_vessels : [];
                vessels.forEach(function(v) {
                    var cap = v.capacity || v.cargo_capacity || 0;
                    var cargo = v.route_cargo || v.current_cargo || 0;
                    if (cap > 0) {
                        v._utilization = Math.round((cargo / cap) * 100);
                    } else {
                        var ri = v.route_info || v.active_route || {};
                        var demand = ri.demand || ri.port_demand || 0;
                        var maxCargo = ri.max_cargo || cap || 0;
                        v._utilization = maxCargo > 0 ? Math.round((demand / maxCargo) * 100) : 100;
                    }
                });
                return vessels;
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
                xhr.send(JSON.stringify({{user_vessel_id:{vessel_id},speed:{speed},guards:{guards or 0},history:0}}));
                var d = JSON.parse(xhr.responseText);
                if (d.data && d.data.depart_info) {{
                    var di = d.data.depart_info;
                    return {{success:true,income:di.depart_income,fuelUsed:di.fuel_usage/1000,co2Used:di.co2_emission/1000,harbor:di.harbor_fee}};
                }}
                return {{success:false, error: d.error || 'unknown'}};
            }} catch(e) {{ return {{success:false, error:e.message}}; }}
        """)

    def moor_vessel_sync(self, vessel_id):
        return self.run_js(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/vessel/moor', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send(JSON.stringify({{user_vessel_id:{vessel_id}}}));
                var d = JSON.parse(xhr.responseText);
                return d.success ? 'ok' : (d.error || 'failed');
            }} catch(e) {{ return 'error:'+e.message; }}
        """)

    def auto_login(self, email: str, password: str) -> bool:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.keys import Keys
            self._switch()
            self.driver.get("https://shippingmanager.cc/login")
            time.sleep(2)
            wait = WebDriverWait(self.driver, 10)
            email_field = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='email'], input[name='email']")))
            email_field.clear(); email_field.send_keys(email)
            time.sleep(0.5)
            pass_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            pass_field.clear(); pass_field.send_keys(password)
            time.sleep(0.5)
            clicked = False
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                btn.click(); clicked = True
            except Exception:
                pass
            if not clicked:
                try:
                    for btn in self.driver.find_elements(By.TAG_NAME, "button"):
                        if any(w in btn.text.lower() for w in ["login","sign in","log in"]):
                            btn.click(); clicked = True; break
                except Exception:
                    pass
            if not clicked:
                pass_field.send_keys(Keys.RETURN)
            time.sleep(4)
            return "login" not in self.driver.current_url
        except Exception as e:
            self.log(f"⚠ Auto-login error: {e}")
            return False

    def is_logged_in(self):
        self._switch()
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

    def close(self):
        """Close just this account's tab."""
        try:
            if self.driver and self.tab_handle:
                self._switch()
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                # Don't quit the whole browser — SharedBrowser.close() does that
        except Exception:
            pass


# ── AUTO MANAGER ──────────────────────────────────────────────────────────────
class AutoManager:
    def __init__(self, browser, account_id, log_fn, on_bunker, on_prices, on_depart):
        self.browser      = browser
        self.account_id   = account_id
        self.log          = log_fn
        self.on_bunker    = on_bunker
        self.on_prices    = on_prices
        self.on_depart    = on_depart
        self._running     = False

    def get_settings(self):
        return AccountManager.get_settings(self.account_id)

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def run_now(self):
        threading.Thread(target=self._cycle, daemon=True).start()

    def _loop(self):
        for _ in range(60):
            if not self._running: return
            if self.browser.ready: break
            time.sleep(1)
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
            for _ in range(int(s.get("check_interval", 60)) * 2):
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
                self.log("⚠ Couldn't read game data"); return

            fp = prices.get("fuelPrice"); cp = prices.get("co2Price")
            cash = bunker.get("cash", 0); fuel = bunker.get("fuel", 0)
            co2  = bunker.get("co2",  0); mf   = bunker.get("maxFuel", 0)
            mc   = bunker.get("maxCO2", 0)

            if s["fuel_mode"] != "off" and fp is not None:
                ft = s["fuel_threshold"]; space = mf - fuel
                afford = max(0, cash - s["fuel_min_cash"]) / fp if fp > 0 else 0
                if fp <= ft and space >= 1:
                    amt = min(int(space), int(afford))
                    if amt > 0:
                        self.log(f"⛽ Buying {amt:,}t fuel @ ${fp}/t")
                        r = self.browser.purchase_fuel_sync(amt)
                        if r == "ok":
                            self.log(f"✅ Fuel bought: {amt:,}t")
                            b2 = self.browser.fetch_bunker()
                            if b2: self.on_bunker(b2); cash = b2["cash"]
                        else: self.log(f"❌ Fuel failed: {r}")
                else: self.log(f"⛽ Fuel ${fp}/t threshold ${ft} — skip")

            if s["co2_mode"] != "off" and cp is not None:
                ct = s["co2_threshold"]; space = mc - co2
                afford = max(0, cash - s["co2_min_cash"]) / cp if cp > 0 else 0
                if cp <= ct and space >= 1:
                    amt = min(int(space), int(afford))
                    if amt > 0:
                        self.log(f"🌿 Buying {amt:,}t CO2 @ ${cp}/t")
                        r = self.browser.purchase_co2_sync(amt)
                        if r == "ok":
                            self.log(f"✅ CO2 bought: {amt:,}t")
                            b2 = self.browser.fetch_bunker()
                            if b2: self.on_bunker(b2); cash = b2["cash"]
                        else: self.log(f"❌ CO2 failed: {r}")
                else: self.log(f"🌿 CO2 ${cp}/t threshold ${ct} — skip")

            if s["auto_depart"]:
                vessels     = self.browser.fetch_vessels_sync()
                min_util    = int(s.get("min_utilization", 50))
                util_action = s.get("low_util_action", "skip")
                ready = [v for v in (vessels or [])
                         if v.get("status") == "port"
                         and not v.get("is_parked")
                         and v.get("route_destination")]
                self.log(f"🚢 {len(ready)} vessel(s) in port")
                for v in ready:
                    name = v.get("name", "?"); util = v.get("_utilization", 100)
                    if util < min_util:
                        if util_action == "moor":
                            self.log(f"⚓ {name} util {util}% < {min_util}% — mooring")
                            self.browser.moor_vessel_sync(v["id"])
                        else:
                            self.log(f"⏭ {name} util {util}% < {min_util}% — skipping")
                        time.sleep(0.5); continue
                    r = self.browser.depart_vessel_sync(
                        v["id"], v.get("route_speed", 20), v.get("route_guards", 0))
                    if isinstance(r, dict) and r.get("success"):
                        entry = {"timestamp": int(time.time()*1000), "vessel": name,
                                 "income": r.get("income",0), "fuelUsed": r.get("fuelUsed",0),
                                 "co2Used": r.get("co2Used",0), "util": util}
                        self.on_depart(entry)
                        self.log(f"✅ Departed {name} ({util}% util) +${entry['income']:,}")
                    else:
                        err = r.get("error","?") if isinstance(r,dict) else r
                        self.log(f"❌ Depart failed {name}: {err}")
                    time.sleep(0.5)
        except Exception as e:
            self.log(f"❌ Cycle error: {e}")


# ── HELPERS ───────────────────────────────────────────────────────────────────
def fmt_cash(n):
    try:
        v = int(n)
        if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
        if v >= 1_000:     return f"${v/1_000:.0f}K"
        return f"${v}"
    except: return "—"

def fmt_ts(ts_ms):
    try: return datetime.datetime.fromtimestamp(ts_ms/1000).strftime("%H:%M:%S")
    except: return "—"


# ── ACCOUNT TAB ───────────────────────────────────────────────────────────────
class AccountTab(ctk.CTkFrame):
    """A full dashboard panel for one account."""

    def __init__(self, parent, account: dict, browser: BrowserController,
                 manager: AutoManager, **kw):
        super().__init__(parent, fg_color=C["bg"], corner_radius=0, **kw)
        self.account    = account
        self.browser    = browser
        self.manager    = manager
        self.account_id = account["id"]
        self._session_income  = 0
        self._session_departs = 0
        self._status_var = tk.StringVar(value="Starting…")
        self._build()

    def _build(self):
        # Sub-tab bar
        tab_bar = ctk.CTkFrame(self, fg_color=C["panel"], height=32, corner_radius=0)
        tab_bar.pack(fill="x")
        tab_bar.pack_propagate(False)
        self._pages    = {}
        self._tab_btns = {}
        for tid, label in [("status","📊 Status"),("logs","📋 Logs"),("settings","⚙ Settings")]:
            b = ctk.CTkButton(tab_bar, text=label, font=("Segoe UI", 10),
                              width=90, height=28, corner_radius=0,
                              fg_color="transparent", hover_color=C["border"],
                              text_color=C["dim"],
                              command=lambda t=tid: self._show(t))
            b.pack(side="left", padx=1)
            self._tab_btns[tid] = b

        self._content = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self._content.pack(fill="both", expand=True)

        self._build_status()
        self._build_logs()
        self._build_settings()
        self._show("status")

        ctk.CTkLabel(self, textvariable=self._status_var,
                     font=("Consolas", 9), text_color=C["dim"],
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
        f.pack(fill="x", padx=10, pady=(10, 2))
        ctk.CTkLabel(f, text=title.upper(), font=("Segoe UI", 8, "bold"),
                     text_color=C["muted"]).pack(side="left")
        ctk.CTkFrame(f, height=1, fg_color=C["border"]).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    def _build_status(self):
        page = ctk.CTkScrollableFrame(self._content, fg_color=C["bg"],
                                       scrollbar_button_color=C["border"])
        self._pages["status"] = page

        def stat(label, var):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 10),
                         text_color=C["dim"]).pack(side="left", padx=10, pady=8)
            lbl = ctk.CTkLabel(f, textvariable=var, font=("Consolas", 11, "bold"),
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
                     font=("Segoe UI", 10), text_color=C["dim"],
                     anchor="w", wraplength=340).pack(fill="x", padx=12, pady=4)

        self._sec(page, "Actions")
        ctk.CTkButton(page, text="▶  Run Check Now",
                      font=("Segoe UI", 11, "bold"),
                      fg_color=C["accent"], hover_color="#0a9bd0",
                      height=38, corner_radius=8,
                      command=self.manager.run_now).pack(fill="x", padx=10, pady=3)
        ctk.CTkButton(page, text="🔄  Refresh Status",
                      font=("Segoe UI", 10),
                      fg_color=C["border"], hover_color=C["card"],
                      text_color=C["text"], height=32, corner_radius=8,
                      command=self._refresh).pack(fill="x", padx=10, pady=3)

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
        ctk.CTkLabel(hdr, text="DEPARTURE LOG", font=("Segoe UI", 8, "bold"),
                     text_color=C["muted"]).pack(side="left")
        ctk.CTkButton(hdr, text="Clear", font=("Segoe UI", 9), width=48, height=22,
                      fg_color=C["red"], hover_color="#b91c1c", text_color="white",
                      corner_radius=4, command=self._clear_logs).pack(side="right")
        self._log_scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"], scrollbar_button_color=C["border"])
        self._log_scroll.pack(fill="both", expand=True, padx=6)

    def _add_log(self, entry):
        row = ctk.CTkFrame(self._log_scroll, fg_color=C["card"], corner_radius=6)
        row.pack(fill="x", pady=2)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(5, 0))
        ctk.CTkLabel(top, text=f"{fmt_ts(entry.get('timestamp',0))}  {entry.get('vessel','?')}",
                     font=("Segoe UI", 10), text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(top, text=f"+${entry.get('income',0):,}",
                     font=("Consolas", 10, "bold"), text_color=C["green"]).pack(side="right")
        bot = ctk.CTkFrame(row, fg_color="transparent")
        bot.pack(fill="x", padx=8, pady=(0, 5))
        util_str = f"  util {entry.get('util','')}%" if entry.get('util') else ""
        ctk.CTkLabel(bot, text=f"⛽ {entry.get('fuelUsed',0):.0f}t  🌿 {entry.get('co2Used',0):.0f}t{util_str}",
                     font=("Segoe UI", 9), text_color=C["muted"]).pack(side="left")

    def _clear_logs(self):
        for w in self._log_scroll.winfo_children(): w.destroy()
        self._session_income = 0; self._session_departs = 0
        self._v_session.set("No departures yet")

    def _build_settings(self):
        page = ctk.CTkScrollableFrame(self._content, fg_color=C["bg"],
                                       scrollbar_button_color=C["border"])
        self._pages["settings"] = page
        s = AccountManager.get_settings(self.account_id)

        def field(lbl, var, width=90):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI", 10),
                         text_color=C["text"]).pack(side="left", padx=10, pady=7)
            ctk.CTkEntry(f, textvariable=var, width=width, font=("Consolas", 10),
                         fg_color=C["border"], text_color=C["text"],
                         border_color=C["border"]).pack(side="right", padx=10, pady=5)

        def toggle(lbl, var):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI", 10),
                         text_color=C["text"]).pack(side="left", padx=10, pady=7)
            ctk.CTkSwitch(f, variable=var, text="", width=40,
                          fg_color=C["border"], progress_color=C["green"],
                          button_color=C["text"]).pack(side="right", padx=10)

        def dropdown(lbl, var, values):
            f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI", 10),
                         text_color=C["text"]).pack(side="left", padx=10, pady=7)
            ctk.CTkOptionMenu(f, variable=var, values=values, font=("Segoe UI", 10),
                              width=110, fg_color=C["border"], button_color=C["accent"],
                              text_color=C["text"]).pack(side="right", padx=10, pady=5)

        self._sec(page, "⛽ Fuel")
        self._sv_fm = tk.StringVar(value=s["fuel_mode"])
        self._sv_ft = tk.StringVar(value=str(s["fuel_threshold"]))
        self._sv_fc = tk.StringVar(value=str(s["fuel_min_cash"]))
        dropdown("Mode",                  self._sv_fm, ["off","basic","intelligent"])
        field   ("Price Threshold ($/t)", self._sv_ft)
        field   ("Min Cash Reserve ($)",  self._sv_fc, 110)

        self._sec(page, "🌿 CO2")
        self._sv_cm = tk.StringVar(value=s["co2_mode"])
        self._sv_ct = tk.StringVar(value=str(s["co2_threshold"]))
        self._sv_cc = tk.StringVar(value=str(s["co2_min_cash"]))
        dropdown("Mode",                  self._sv_cm, ["off","basic"])
        field   ("Price Threshold ($/t)", self._sv_ct)
        field   ("Min Cash Reserve ($)",  self._sv_cc, 110)

        self._sec(page, "🚢 Auto-Depart")
        self._sv_ad  = tk.BooleanVar(value=s["auto_depart"])
        self._sv_ci  = tk.StringVar(value=str(s["check_interval"]))
        self._sv_mu  = tk.StringVar(value=str(s.get("min_utilization", 50)))
        self._sv_lua = tk.StringVar(value=s.get("low_util_action", "skip"))
        toggle  ("Enable Auto-Depart",    self._sv_ad)
        field   ("Check Interval (secs)", self._sv_ci)
        field   ("Min Utilization (%)",   self._sv_mu, 70)
        dropdown("Low Util Action",       self._sv_lua, ["skip","moor"])

        self._sec(page, "🔐 Account")
        ctk.CTkButton(page, text="🗑  Forget Saved Login",
                      font=("Segoe UI", 10),
                      fg_color=C["red"], hover_color="#b91c1c",
                      text_color="white", height=34, corner_radius=8,
                      command=self._forget_login).pack(fill="x", padx=10, pady=4)

        ctk.CTkButton(page, text="💾  Save Settings",
                      font=("Segoe UI", 11, "bold"),
                      fg_color=C["green"], hover_color="#16a34a",
                      height=38, corner_radius=8,
                      command=self._save).pack(fill="x", padx=10, pady=14)

    def _save(self):
        try:
            s = AccountManager.get_settings(self.account_id)
            s.update({
                "fuel_mode":       self._sv_fm.get(),
                "fuel_threshold":  int(self._sv_ft.get()),
                "fuel_min_cash":   int(self._sv_fc.get()),
                "co2_mode":        self._sv_cm.get(),
                "co2_threshold":   int(self._sv_ct.get()),
                "co2_min_cash":    int(self._sv_cc.get()),
                "auto_depart":     self._sv_ad.get(),
                "check_interval":  int(self._sv_ci.get()),
                "min_utilization": int(self._sv_mu.get()),
                "low_util_action": self._sv_lua.get(),
            })
            AccountManager.save_settings(self.account_id, s)
            self.set_status("✅ Settings saved")
        except ValueError as e:
            self.set_status(f"❌ Bad value: {e}")

    def _forget_login(self):
        AccountManager.clear_credentials(self.account_id)
        self.set_status("✅ Login cleared — will ask next launch")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def on_bunker(self, d):
        def _u():
            self._v_fuel.set(f"{d.get('fuel',0):,.0f} / {d.get('maxFuel',0):,.0f} t")
            self._v_co2.set( f"{d.get('co2', 0):,.0f} / {d.get('maxCO2', 0):,.0f} t")
            self._v_cash.set(fmt_cash(d.get("cash", 0)))
        self.after(0, _u)

    def on_prices(self, d):
        def _u():
            s = AccountManager.get_settings(self.account_id)
            fp = d.get("fuelPrice"); cp = d.get("co2Price")
            if fp is not None:
                self._v_fp.set(f"${fp}/t")
                self._lbl_fp.configure(
                    text_color=C["green"] if fp <= s["fuel_threshold"] else C["red"])
            if cp is not None:
                self._v_cp.set(f"${cp}/t")
                self._lbl_cp.configure(
                    text_color=C["green"] if cp <= s["co2_threshold"] else C["red"])
        self.after(0, _u)

    def on_depart(self, entry):
        self._session_departs += 1
        self._session_income  += entry.get("income", 0)
        def _u():
            self._v_session.set(
                f"{self._session_departs} departure(s)  •  +${self._session_income:,}")
            self._add_log(entry)
        self.after(0, _u)

    def set_status(self, msg):
        self.after(0, lambda: self._status_var.set(msg))

    def log(self, msg):
        self.set_status(msg)
        print(f"[{self.account['name']}] {msg}")


# ── MAIN DASHBOARD ────────────────────────────────────────────────────────────
class PirateBrowserDashboard:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Pirate Browser")
        self.root.geometry("380x900+0+0")
        self.root.resizable(False, True)
        self.root.configure(fg_color=C["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._account_tabs: dict[str, AccountTab] = {}
        self._browsers:     dict[str, BrowserController] = {}
        self._managers:     dict[str, AutoManager] = {}
        self._shared_browser: SharedBrowser = None
        self._build()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self.root, fg_color=C["panel"], height=54, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🏴‍☠️  PIRATE BROWSER",
                     font=("Segoe UI", 13, "bold"),
                     text_color=C["accent"]).place(relx=0.4, rely=0.5, anchor="center")
        ctk.CTkButton(hdr, text="+ Account", font=("Segoe UI", 9),
                      width=80, height=26, corner_radius=6,
                      fg_color=C["border"], hover_color=C["card"],
                      text_color=C["text"],
                      command=self._add_account_dialog).place(relx=0.82, rely=0.5, anchor="center")

        # Top-level nav (Accounts | Chatbot)
        nav = ctk.CTkFrame(self.root, fg_color=C["panel"], height=32, corner_radius=0)
        nav.pack(fill="x")
        nav.pack_propagate(False)
        self._nav_accounts_btn = ctk.CTkButton(
            nav, text="⚓ Accounts", font=("Segoe UI", 10),
            width=100, height=28, corner_radius=0,
            fg_color=C["border"], hover_color=C["border"], text_color=C["accent"],
            command=self._show_accounts)
        self._nav_accounts_btn.pack(side="left", padx=1)
        self._nav_bot_btn = ctk.CTkButton(
            nav, text="🤖 Chatbot", font=("Segoe UI", 10),
            width=100, height=28, corner_radius=0,
            fg_color="transparent", hover_color=C["border"], text_color=C["dim"],
            command=self._show_chatbot)
        self._nav_bot_btn.pack(side="left", padx=1)

        # Account tab bar
        self._acct_bar = ctk.CTkFrame(self.root, fg_color=C["panel"],
                                       height=32, corner_radius=0)
        self._acct_bar.pack(fill="x")

        # Content area
        self._content = ctk.CTkFrame(self.root, fg_color=C["bg"], corner_radius=0)
        self._content.pack(fill="both", expand=True)

        # Chatbot panel (hidden initially)
        self._chatbot_panel = ctk.CTkFrame(self.root, fg_color=C["bg"], corner_radius=0)
        self._chatbot_tab_widget: ChatBotTab = None

        # No accounts placeholder
        self._placeholder = ctk.CTkLabel(
            self._content,
            text="No accounts yet.\nClick '+ Account' to add one.",
            font=("Segoe UI", 12), text_color=C["dim"], justify="center")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self._active_account_id = None

    def _add_account_dialog(self):
        popup = ctk.CTkToplevel(self.root)
        popup.title("Add Account")
        popup.geometry("320x180")
        popup.resizable(False, False)
        popup.configure(fg_color="#0a0f1e")
        popup.grab_set()

        ctk.CTkLabel(popup, text="Account Name",
                     font=("Segoe UI", 11), text_color=C["dim"]).pack(pady=(20, 4))
        name_var = tk.StringVar()
        entry = ctk.CTkEntry(popup, textvariable=name_var,
                             placeholder_text="e.g. Main Account",
                             font=("Segoe UI", 11), height=36,
                             fg_color=C["card"], text_color=C["text"],
                             border_color=C["border"])
        entry.pack(fill="x", padx=20)
        entry.focus()

        def _confirm():
            name = name_var.get().strip()
            if not name:
                return
            popup.destroy()
            account = AccountManager.add_account(name)
            self._launch_account(account)

        ctk.CTkButton(popup, text="Add & Login",
                      font=("Segoe UI", 11, "bold"),
                      fg_color=C["accent"], hover_color="#0a9bd0",
                      height=36, corner_radius=8,
                      command=_confirm).pack(fill="x", padx=20, pady=12)
        popup.bind("<Return>", lambda e: _confirm())

    def _launch_account(self, account: dict):
        aid   = account["id"]
        email, password = AccountManager.load_credentials(aid)

        # Show login dialog if no saved creds
        if not email or not password:
            creds = [None, None]
            def on_login(em, pw, remember):
                creds[0] = em; creds[1] = pw
                if remember:
                    AccountManager.save_credentials(aid, em, pw)
            submitted = show_login_dialog(self.root, account["name"], on_login)
            if not submitted or not creds[0]:
                AccountManager.remove_account(aid)
                return
            email, password = creds[0], creds[1]

        # Get or create shared browser, open a new tab for this account
        if self._shared_browser is None:
            self._shared_browser = SharedBrowser(lambda m: print(f"[Browser] {m}"))
            threading.Thread(target=self._shared_browser.start, daemon=True).start()
            # Wait for browser to be ready before opening first tab
            for _ in range(60):
                if self._shared_browser.ready: break
                time.sleep(1)
            tab_handle = self._shared_browser.driver.window_handles[0]
        else:
            tab_handle = self._shared_browser.new_tab()

        browser = BrowserController(
            lambda m, a=account: self._log(a, m), aid,
            self._shared_browser, tab_handle)
        manager = AutoManager(
            browser     = browser,
            account_id  = aid,
            log_fn      = lambda m, a=account: self._log(a, m),
            on_bunker   = lambda d, a=aid: self._on_bunker(a, d),
            on_prices   = lambda d, a=aid: self._on_prices(a, d),
            on_depart   = lambda d, a=aid: self._on_depart(a, d),
        )

        self._browsers[aid] = browser
        self._managers[aid] = manager

        # Add account button to tab bar
        btn = ctk.CTkButton(
            self._acct_bar, text=account["name"],
            font=("Segoe UI", 10), height=28, corner_radius=0,
            fg_color="transparent", hover_color=C["border"],
            text_color=C["dim"],
            command=lambda a=aid: self._switch_account(a))
        btn.pack(side="left", padx=1)

        # Remove button (right-click)
        def _remove(event, a=aid, b=btn):
            if ctk.CTkInputDialog(text=f"Remove account '{account['name']}'?",
                                  title="Confirm").get_input() is not None:
                self._remove_account(a, b)
        btn.bind("<Button-3>", _remove)

        # Build account tab content
        tab = AccountTab(self._content, account, browser, manager)
        self._account_tabs[aid] = tab

        self._placeholder.place_forget()
        self._switch_account(aid)

        # Start browser + manager
        def _start():
            browser.start()
            if browser.ready and email and password:
                self._log(account, "🔐 Attempting auto-login…")
                if browser.auto_login(email, password):
                    self._log(account, "✅ Auto-login successful")
                else:
                    self._log(account, "⚠ Auto-login failed — please log in manually")
            manager.start()

        threading.Thread(target=_start, daemon=True).start()

    def _switch_account(self, account_id: str):
        self._active_account_id = account_id
        for aid, tab in self._account_tabs.items():
            if aid == account_id:
                tab.pack(fill="both", expand=True)
            else:
                tab.pack_forget()
        # Update tab button colours
        for widget in self._acct_bar.winfo_children():
            name = widget.cget("text")
            accounts = AccountManager.load_accounts()
            match = next((a for a in accounts if a["name"] == name and a["id"] == account_id), None)
            widget.configure(
                text_color=C["accent"] if match else C["dim"],
                fg_color=C["border"] if match else "transparent")

    def _remove_account(self, account_id: str, btn):
        if account_id in self._managers:
            self._managers[account_id].stop()
        if account_id in self._browsers:
            self._browsers[account_id].close()
        if account_id in self._account_tabs:
            self._account_tabs[account_id].destroy()
            del self._account_tabs[account_id]
        AccountManager.remove_account(account_id)
        btn.destroy()
        del self._browsers[account_id]
        del self._managers[account_id]
        if not self._account_tabs:
            self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _show_accounts(self):
        self._chatbot_panel.pack_forget()
        self._acct_bar.pack(fill="x")
        self._content.pack(fill="both", expand=True)
        self._nav_accounts_btn.configure(fg_color=C["border"], text_color=C["accent"])
        self._nav_bot_btn.configure(fg_color="transparent", text_color=C["dim"])

    def _show_chatbot(self):
        self._acct_bar.pack_forget()
        self._content.pack_forget()
        self._chatbot_panel.pack(fill="both", expand=True)
        self._nav_bot_btn.configure(fg_color=C["border"], text_color=C["accent"])
        self._nav_accounts_btn.configure(fg_color="transparent", text_color=C["dim"])
        if self._chatbot_tab_widget is None and self._browsers:
            first_aid = next(iter(self._browsers))
            self._chatbot_tab_widget = ChatBotTab(
                self._chatbot_panel, self._browsers[first_aid], first_aid)
            self._chatbot_tab_widget.pack(fill="both", expand=True)
        elif self._chatbot_tab_widget is None:
            ctk.CTkLabel(self._chatbot_panel,
                         text="Add an account first to use the chatbot",
                         font=("Segoe UI", 12), text_color=C["dim"]).place(
                relx=0.5, rely=0.5, anchor="center")

    def _log(self, account: dict, msg: str):
        print(f"[{account['name']}] {msg}")
        aid = account["id"]
        if aid in self._account_tabs:
            self._account_tabs[aid].log(msg)

    def _on_bunker(self, account_id: str, data: dict):
        if account_id in self._account_tabs:
            self._account_tabs[account_id].on_bunker(data)

    def _on_prices(self, account_id: str, data: dict):
        if account_id in self._account_tabs:
            self._account_tabs[account_id].on_prices(data)

    def _on_depart(self, account_id: str, entry: dict):
        if account_id in self._account_tabs:
            self._account_tabs[account_id].on_depart(entry)

    def _on_close(self):
        for manager in self._managers.values():
            manager.stop()
        if self._shared_browser:
            self._shared_browser.close()
        self.root.destroy()

    def run(self):
        threading.Thread(target=self._check_updates, daemon=True).start()
        # Auto-launch saved accounts
        accounts = AccountManager.load_accounts()
        if accounts:
            for account in accounts:
                self.root.after(100, lambda a=account: self._launch_account(a))
        self.root.mainloop()

    def _check_updates(self):
        time.sleep(3)
        latest, url = check_for_updates()
        if latest and version_tuple(latest) > version_tuple(CURRENT_VERSION):
            self.root.after(0, lambda: show_update_dialog(latest))


# ── CHATBOT ───────────────────────────────────────────────────────────────────
CUSTOM_COMMANDS_FILE = DATA_DIR / "custom_commands.json"
PORT_RANKINGS_CACHE  = DATA_DIR / "port_rankings_cache.json"

WELCOME_MESSAGE = (
    "⚓ Ahoy, {company}! Welcome aboard The Salty Sea Dogs! 🏴‍☠️\n"
    "May yer coffers overflow an' yer sails stay full! "
    "Type !help to see what this here bot can do. Fair winds, Captain! 🌊"
)

def load_custom_commands() -> dict:
    if CUSTOM_COMMANDS_FILE.exists():
        try:
            return json.loads(CUSTOM_COMMANDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_custom_commands(commands: dict):
    CUSTOM_COMMANDS_FILE.write_text(json.dumps(commands, indent=2), encoding="utf-8")

def load_port_rankings() -> list:
    if PORT_RANKINGS_CACHE.exists():
        try:
            data = json.loads(PORT_RANKINGS_CACHE.read_text(encoding="utf-8"))
            return data.get("rankings", [])
        except Exception:
            pass
    return []

def save_port_rankings(rankings: list):
    PORT_RANKINGS_CACHE.write_text(
        json.dumps({"timestamp": int(time.time()), "rankings": rankings}, indent=2),
        encoding="utf-8")


class AllianceChatBot:
    """Polls alliance chat, responds to commands, sends welcome messages."""

    def __init__(self, browser: BrowserController, alliance_id: int,
                 bot_user_id: int, log_fn, on_chat_message):
        self.browser         = browser
        self.alliance_id     = alliance_id
        self.bot_user_id     = bot_user_id
        self.log             = log_fn
        self.on_chat_message = on_chat_message   # callback to update UI
        self._running        = False
        self._last_ts        = int(time.time())  # only handle messages after start
        self._seen_ids       = set()

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        self.log("🤖 Chatbot started")

    def stop(self):
        self._running = False
        self.log("🤖 Chatbot stopped")

    def _loop(self):
        # Wait for browser
        for _ in range(60):
            if not self._running: return
            if self.browser.ready: break
            time.sleep(1)

        while self._running:
            try:
                self._poll()
            except Exception as e:
                self.log(f"⚠ Bot error: {e}")
            for _ in range(30):
                if not self._running: return
                time.sleep(1)

    def _poll(self):
        feed = self.browser.run_js(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/alliance/get-chat-feed', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send(JSON.stringify({{alliance_id: {self.alliance_id}, offset: 0, limit: 50}}));
                var d = JSON.parse(xhr.responseText);
                return d.data ? d.data.chat_feed : [];
            }} catch(e) {{ return []; }}
        """)
        if not feed:
            return

        for entry in reversed(feed):
            ts       = entry.get("time_created", 0)
            uid      = entry.get("user_id")
            msg_type = entry.get("type")
            key      = f"{uid}_{ts}"

            if ts <= self._last_ts or key in self._seen_ids:
                continue
            self._seen_ids.add(key)

            # Member joined
            if msg_type == "feed" and entry.get("feed_type") == "member_joined":
                company = entry.get("replacements", {}).get("company_name", "Captain")
                self.log(f"👋 New member: {company}")
                self.on_chat_message({"type": "join", "company": company, "ts": ts})
                welcome = WELCOME_MESSAGE.format(company=company)
                self.send(welcome)

            # Chat command
            elif msg_type == "chat" and uid != self.bot_user_id:
                text = (entry.get("message") or "").strip()
                self.on_chat_message({"type": "chat", "uid": uid, "text": text, "ts": ts})
                if text.startswith("!"):
                    self._handle_command(text)

        self._last_ts = max((e.get("time_created", 0) for e in feed), default=self._last_ts)

    def _handle_command(self, text: str):
        cmd   = text.split()[0].lower()
        parts = text.split()[1:]

        if cmd == "!help":
            custom = load_custom_commands()
            built_in = "⚓ Ahoy! Here be the available commands:\n"
            built_in += "!ports — Top port rankings\n"
            built_in += "!stats — Alliance stats\n"
            if custom:
                built_in += "\n📜 Custom commands:\n"
                for k in custom:
                    built_in += f"{k}\n"
            self.send(built_in)
            self.log(f"🤖 Responded to !help")

        elif cmd == "!ports":
            self._cmd_ports()

        elif cmd == "!stats":
            self._cmd_stats()

        else:
            # Check custom commands
            custom = load_custom_commands()
            if cmd in custom:
                self.send(custom[cmd])
                self.log(f"🤖 Responded to custom command {cmd}")

    def _cmd_ports(self):
        rankings = load_port_rankings()
        if not rankings:
            self.send("⚓ No port data yet, Cap'n! Run the alliance tracker first.")
            return

        ranked = sorted([r for r in rankings if r.get("rank")], key=lambda x: x["rank"])

        lines = ["🏴‍☠️ The Salty Sea Dogs — Port Rankings 🏴‍☠️\n"]

        # Top 1-4 with medals
        top4 = [r for r in ranked if r["rank"] <= 4]
        if top4:
            lines.append("⚔️ Our finest conquests:")
            medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "🏅"}
            for r in top4:
                medal = medals.get(r["rank"], "🏅")
                name  = r["port_code"].replace("_", " ").title()
                lines.append(f"{medal} #{r['rank']} {name}")

        # Top 20 overall
        top20 = ranked[:20]
        if top20:
            lines.append(f"\n⚓ Top 20 ports ({len(ranked)} total):")
            for r in top20:
                name = r["port_code"].replace("_", " ").title()
                lines.append(f"#{r['rank']} {name}")

        self.send("\n".join(lines))
        self.log("🤖 Responded to !ports")

    def _cmd_stats(self):
        stats = self.browser.run_js(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://shippingmanager.cc/api/alliance/get-alliance', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.withCredentials = true;
                xhr.send(JSON.stringify({{alliance_id: {self.alliance_id}}}));
                var d = JSON.parse(xhr.responseText);
                return d.data ? d.data.alliance : null;
            }} catch(e) {{ return null; }}
        """)
        if not stats:
            self.send("⚓ Couldn't fetch stats, Cap'n! Try again later.")
            return

        s    = stats.get("stats", {})
        dep  = s.get("departures_24h", 0)
        coop = s.get("coops_24h", 0)
        mem  = stats.get("members", 0)
        lvl  = stats.get("benefit_level", 0)

        msg = (
            f"🏴‍☠️ The Salty Sea Dogs — Alliance Stats ⚓\n"
            f"👥 Members: {mem}\n"
            f"⭐ Benefit Level: {lvl}\n"
            f"🚢 Departures (24h): {dep:,}\n"
            f"🤝 Co-ops (24h): {coop:,}"
        )
        self.send(msg)
        self.log("🤖 Responded to !stats")

    def send(self, text: str):
        # Split long messages into chunks of 500 chars
        chunks = [text[i:i+500] for i in range(0, len(text), 500)]
        for chunk in chunks:
            escaped = chunk.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            self.browser.run_js(f"""
                try {{
                    var xhr = new XMLHttpRequest();
                    xhr.open('POST', 'https://shippingmanager.cc/api/alliance/post-chat', false);
                    xhr.setRequestHeader('Content-Type', 'application/json');
                    xhr.withCredentials = true;
                    xhr.send(JSON.stringify({{alliance_id: {self.alliance_id}, text: '{escaped}'}}));
                }} catch(e) {{}}
            """)
            time.sleep(0.5)


# ── CHATBOT TAB ───────────────────────────────────────────────────────────────
class ChatBotTab(ctk.CTkFrame):
    """Dashboard tab for managing the alliance chatbot."""

    def __init__(self, parent, browser: BrowserController, account_id: str, **kw):
        super().__init__(parent, fg_color=C["bg"], corner_radius=0, **kw)
        self.browser     = browser
        self.account_id  = account_id
        self.bot: AllianceChatBot = None
        self._status_var  = tk.StringVar(value="Bot offline")
        self._alliance_id = None
        self._bot_user_id = None
        self._build()

    def _build(self):
        # Sub-tabs
        tab_bar = ctk.CTkFrame(self, fg_color=C["panel"], height=32, corner_radius=0)
        tab_bar.pack(fill="x")
        tab_bar.pack_propagate(False)
        self._pages    = {}
        self._tab_btns = {}
        for tid, label in [("control","🤖 Bot"), ("commands","📜 Commands"), ("log","💬 Chat Log")]:
            b = ctk.CTkButton(tab_bar, text=label, font=("Segoe UI", 10),
                              width=100, height=28, corner_radius=0,
                              fg_color="transparent", hover_color=C["border"],
                              text_color=C["dim"],
                              command=lambda t=tid: self._show(t))
            b.pack(side="left", padx=1)
            self._tab_btns[tid] = b

        self._content = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self._content.pack(fill="both", expand=True)

        self._build_control()
        self._build_commands()
        self._build_log()
        self._show("control")

        ctk.CTkLabel(self, textvariable=self._status_var,
                     font=("Consolas", 9), text_color=C["dim"],
                     anchor="w").pack(fill="x", padx=8, pady=2)

    def _show(self, tab_id):
        for tid, page in self._pages.items():
            if tid == tab_id:
                page.pack(fill="both", expand=True)
                self._tab_btns[tid].configure(text_color=C["accent"], fg_color=C["border"])
            else:
                page.pack_forget()
                self._tab_btns[tid].configure(text_color=C["dim"], fg_color="transparent")

    def _build_control(self):
        page = ctk.CTkScrollableFrame(self._content, fg_color=C["bg"],
                                       scrollbar_button_color=C["border"])
        self._pages["control"] = page

        # Status card
        status_card = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=10)
        status_card.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(status_card, text="🤖  Alliance Chatbot",
                     font=("Segoe UI", 13, "bold"),
                     text_color=C["accent"]).pack(pady=(12, 2))
        self._status_lbl = ctk.CTkLabel(status_card, textvariable=self._status_var,
                                         font=("Segoe UI", 10), text_color=C["dim"])
        self._status_lbl.pack(pady=(0, 12))

        # Alliance ID input
        f = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
        f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f, text="Alliance ID", font=("Segoe UI", 10),
                     text_color=C["text"]).pack(side="left", padx=10, pady=7)
        self._sv_aid = tk.StringVar(value="6338")
        ctk.CTkEntry(f, textvariable=self._sv_aid, width=90,
                     font=("Consolas", 10), fg_color=C["border"],
                     text_color=C["text"], border_color=C["border"]).pack(
            side="right", padx=10, pady=5)

        # Separator
        ctk.CTkFrame(page, fg_color=C["border"], height=1).pack(
            fill="x", padx=10, pady=8)

        # Welcome message editor
        ctk.CTkLabel(page, text="WELCOME MESSAGE",
                     font=("Segoe UI", 8, "bold"),
                     text_color=C["muted"], anchor="w").pack(fill="x", padx=12)
        ctk.CTkLabel(page, text="Use {company} for the new member's name",
                     font=("Segoe UI", 9), text_color=C["dim"],
                     anchor="w").pack(fill="x", padx=12, pady=(2, 4))
        self._welcome_text = ctk.CTkTextbox(page, height=80, font=("Segoe UI", 10),
                                             fg_color=C["card"], text_color=C["text"],
                                             border_color=C["border"], border_width=1)
        self._welcome_text.pack(fill="x", padx=10, pady=(0, 8))
        self._welcome_text.insert("1.0", WELCOME_MESSAGE)

        # Buttons
        self._start_btn = ctk.CTkButton(
            page, text="▶  Start Bot",
            font=("Segoe UI", 11, "bold"),
            fg_color=C["green"], hover_color="#16a34a",
            height=38, corner_radius=8,
            command=self._start_bot)
        self._start_btn.pack(fill="x", padx=10, pady=3)

        self._stop_btn = ctk.CTkButton(
            page, text="⏹  Stop Bot",
            font=("Segoe UI", 11, "bold"),
            fg_color=C["red"], hover_color="#b91c1c",
            height=38, corner_radius=8,
            state="disabled",
            command=self._stop_bot)
        self._stop_btn.pack(fill="x", padx=10, pady=3)

        ctk.CTkButton(page, text="📢  Send !ports Now",
                      font=("Segoe UI", 10),
                      fg_color=C["border"], hover_color=C["card"],
                      text_color=C["text"], height=32, corner_radius=8,
                      command=self._send_ports_now).pack(fill="x", padx=10, pady=3)

    def _build_commands(self):
        page = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)
        self._pages["commands"] = page

        ctk.CTkLabel(page, text="Custom Commands",
                     font=("Segoe UI", 12, "bold"),
                     text_color=C["accent"]).pack(pady=(12, 2))
        ctk.CTkLabel(page, text="Members type !command in chat to trigger a response",
                     font=("Segoe UI", 9), text_color=C["dim"]).pack(pady=(0, 8))

        # Add new command
        add_frame = ctk.CTkFrame(page, fg_color=C["card"], corner_radius=8)
        add_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(add_frame, text="Command (with !)",
                     font=("Segoe UI", 9), text_color=C["dim"],
                     anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        self._sv_cmd = tk.StringVar()
        ctk.CTkEntry(add_frame, textvariable=self._sv_cmd,
                     placeholder_text="!example",
                     font=("Segoe UI", 10), height=32,
                     fg_color=C["border"], text_color=C["text"],
                     border_color=C["border"]).pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(add_frame, text="Response text",
                     font=("Segoe UI", 9), text_color=C["dim"],
                     anchor="w").pack(fill="x", padx=10, pady=(4, 2))
        self._cmd_response = ctk.CTkTextbox(
            add_frame, height=60, font=("Segoe UI", 10),
            fg_color=C["border"], text_color=C["text"],
            border_color=C["border"], border_width=1)
        self._cmd_response.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkButton(add_frame, text="➕  Add Command",
                      font=("Segoe UI", 10, "bold"),
                      fg_color=C["accent"], hover_color="#0a9bd0",
                      height=32, corner_radius=6,
                      command=self._add_command).pack(fill="x", padx=10, pady=(0, 10))

        # Existing commands list
        ctk.CTkLabel(page, text="SAVED COMMANDS",
                     font=("Segoe UI", 8, "bold"),
                     text_color=C["muted"], anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        self._cmd_list = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"], scrollbar_button_color=C["border"])
        self._cmd_list.pack(fill="both", expand=True, padx=6, pady=4)
        self._refresh_cmd_list()

    def _build_log(self):
        page = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)
        self._pages["log"] = page
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(hdr, text="CHAT LOG", font=("Segoe UI", 8, "bold"),
                     text_color=C["muted"]).pack(side="left")
        ctk.CTkButton(hdr, text="Clear", font=("Segoe UI", 9), width=48, height=22,
                      fg_color=C["red"], hover_color="#b91c1c", text_color="white",
                      corner_radius=4,
                      command=self._clear_log).pack(side="right")
        self._log_scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"], scrollbar_button_color=C["border"])
        self._log_scroll.pack(fill="both", expand=True, padx=6)

    def _clear_log(self):
        for w in self._log_scroll.winfo_children():
            w.destroy()

    def _add_log_entry(self, entry: dict):
        def _do():
            ts   = datetime.datetime.fromtimestamp(
                entry.get("ts", time.time())).strftime("%H:%M:%S")
            row  = ctk.CTkFrame(self._log_scroll, fg_color=C["card"], corner_radius=6)
            row.pack(fill="x", pady=2)
            if entry["type"] == "join":
                text = f"👋 {entry['company']} joined"
                col  = C["green"]
            else:
                text = entry.get("text", "")
                col  = C["text"]
            ctk.CTkLabel(row, text=f"[{ts}] {text}",
                         font=("Segoe UI", 9), text_color=col,
                         anchor="w", wraplength=320).pack(
                fill="x", padx=8, pady=4)
        self.after(0, _do)

    def _refresh_cmd_list(self):
        for w in self._cmd_list.winfo_children():
            w.destroy()
        commands = load_custom_commands()
        if not commands:
            ctk.CTkLabel(self._cmd_list, text="No custom commands yet",
                         font=("Segoe UI", 10), text_color=C["dim"]).pack(pady=10)
            return
        for cmd, response in commands.items():
            row = ctk.CTkFrame(self._cmd_list, fg_color=C["card"], corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=cmd, font=("Consolas", 10, "bold"),
                         text_color=C["accent"]).pack(side="left", padx=10, pady=6)
            preview = response[:40] + "…" if len(response) > 40 else response
            ctk.CTkLabel(row, text=preview, font=("Segoe UI", 9),
                         text_color=C["dim"]).pack(side="left", padx=4)
            ctk.CTkButton(row, text="✕", width=28, height=24,
                          font=("Segoe UI", 9),
                          fg_color=C["red"], hover_color="#b91c1c",
                          text_color="white", corner_radius=4,
                          command=lambda c=cmd: self._delete_command(c)
                          ).pack(side="right", padx=6, pady=4)

    def _add_command(self):
        cmd      = self._sv_cmd.get().strip()
        response = self._cmd_response.get("1.0", "end").strip()
        if not cmd or not response:
            self._status_var.set("⚠ Enter both command and response")
            return
        if not cmd.startswith("!"):
            cmd = "!" + cmd
        commands = load_custom_commands()
        commands[cmd.lower()] = response
        save_custom_commands(commands)
        self._sv_cmd.set("")
        self._cmd_response.delete("1.0", "end")
        self._refresh_cmd_list()
        self._status_var.set(f"✅ Command {cmd} saved")

    def _delete_command(self, cmd: str):
        commands = load_custom_commands()
        commands.pop(cmd, None)
        save_custom_commands(commands)
        self._refresh_cmd_list()
        self._status_var.set(f"🗑 Command {cmd} removed")

    def _start_bot(self):
        try:
            alliance_id = int(self._sv_aid.get().strip())
        except ValueError:
            self._status_var.set("⚠ Invalid Alliance ID")
            return

        # Get bot user ID from browser
        def _do():
            uid = self.browser.run_js("""
                try {
                    var app = document.querySelector('#app');
                    var pinia = app.__vue_app__._context.provides.pinia
                             || app.__vue_app__.config.globalProperties.$pinia;
                    var us = pinia._s.get('user');
                    return us && us.user ? us.user.id : null;
                } catch(e) { return null; }
            """)
            self._bot_user_id = uid
            self._alliance_id = alliance_id
            self.bot = AllianceChatBot(
                browser      = self.browser,
                alliance_id  = alliance_id,
                bot_user_id  = uid,
                log_fn       = lambda m: self.after(0, lambda: self._status_var.set(m)),
                on_chat_message = self._add_log_entry,
            )
            # Override welcome message with current text box value
            global WELCOME_MESSAGE
            WELCOME_MESSAGE = self._welcome_text.get("1.0", "end").strip()
            self.bot.start()
            self.after(0, lambda: [
                self._start_btn.configure(state="disabled"),
                self._stop_btn.configure(state="normal"),
                self._status_var.set(f"✅ Bot running — watching alliance {alliance_id}"),
                self._status_lbl.configure(text_color=C["green"]),
            ])
        threading.Thread(target=_do, daemon=True).start()

    def _stop_bot(self):
        if self.bot:
            self.bot.stop()
            self.bot = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._status_var.set("Bot offline")
        self._status_lbl.configure(text_color=C["dim"])

    def _send_ports_now(self):
        if not self.bot:
            self._status_var.set("⚠ Start the bot first")
            return
        threading.Thread(target=self.bot._cmd_ports, daemon=True).start()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    dash = PirateBrowserDashboard()
    dash.run()

if __name__ == "__main__":
    main()
