"""
Alliance Member Stats Tracker — ShippingManager.cc
Tracks 24h contribution, season contribution, season departures per member.
Writes to Google Sheets + pushes encrypted JSON to GitHub for Netlify dashboard.
Runs every hour.
"""

import time
import json
import base64
import os
import datetime
import sys
import hashlib
import struct
import urllib.request
import urllib.error
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
CHECK_INTERVAL_MINUTES = 60
SPREADSHEET_ID         = "1uOPfGe8qk5asPCS2ozJNKdAycCg8Z_XTKZR93b8JTfI"
CREDENTIALS_FILE       = Path(__file__).parent / "google_credentials.json"
ALLIANCE_ID            = 6338
ALLIANCE_NAME          = "The Salty Sea Dogs"
HISTORY_FILE           = Path(__file__).parent / "member_stats_history.json"
MAX_HISTORY_SNAPSHOTS  = 2160  # 90 days at hourly (downsampled beyond 14 days)

# ── GITHUB / NETLIFY CONFIG ───────────────────────────────────────────────────
# Paste your GitHub personal access token here (repo scope)
GITHUB_TOKEN     = ""
GITHUB_REPO      = "PiratesTreasure/pirate-dashboard"
GITHUB_BRANCH    = "main"
GITHUB_DATA_PATH = "public/member_data.json"

# ── DASHBOARD LOGIN CONFIG ────────────────────────────────────────────────────
# Username and password for the dashboard — change these to whatever you want
DASHBOARD_USERNAME = "Seadogs"
DASHBOARD_PASSWORD = "Seadogs123"

# ── CREDENTIAL LOADING ────────────────────────────────────────────────────────
def get_data_dir() -> Path:
    app_data = os.environ.get("APPDATA")
    return Path(app_data) / "PirateBrowser" if app_data else Path(__file__).parent

def load_credentials():
    data_dir      = get_data_dir()
    accounts_file = data_dir / "accounts.json"
    if not accounts_file.exists():
        print("❌ No Pirate Browser accounts found."); sys.exit(1)
    accounts = json.loads(accounts_file.read_text(encoding="utf-8"))
    if not accounts:
        print("❌ No accounts saved."); sys.exit(1)
    if len(accounts) > 1:
        print("Multiple accounts:")
        for i, a in enumerate(accounts):
            print(f"  {i+1}. {a['name']}")
        try:
            account = accounts[int(input("Which account? (number): ").strip()) - 1]
        except Exception:
            account = accounts[0]
    else:
        account = accounts[0]
    aid        = account["id"]
    creds_file = data_dir / f".creds_{aid}"
    if not creds_file.exists():
        print(f"❌ No saved credentials for '{account['name']}'"); sys.exit(1)
    data = json.loads(creds_file.read_text(encoding="utf-8"))
    xkey = b"PirateBrowserKey1234567890ABCDEF"
    def deobf(t):
        d = base64.b64decode(t.encode())
        return bytes([d[i] ^ xkey[i % len(xkey)] for i in range(len(d))]).decode()
    if data.get("backend") == "keyring":
        import keyring
        return keyring.get_password(f"PirateBrowser_{aid}", "email"), \
               keyring.get_password(f"PirateBrowser_{aid}", "password"), account["name"]
    elif data.get("backend") == "file":
        return deobf(data["email"]), deobf(data["password"]), account["name"]
    print("❌ Could not read credentials"); sys.exit(1)

# ── BROWSER ───────────────────────────────────────────────────────────────────
def start_browser():
    try:
        from selenium import webdriver
        from selenium.webdriver.firefox.options import Options
        opts = Options()
        opts.add_argument("--headless")
        driver = webdriver.Firefox(options=opts)
        print("✅ Firefox (headless) started"); return driver
    except Exception:
        pass
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        print("✅ Chrome (headless) started"); return driver
    except Exception as e:
        print(f"❌ No browser: {e}"); sys.exit(1)

def login(driver, email, password) -> bool:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    driver.get("https://shippingmanager.cc/login")
    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)
        ef   = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='email'], input[name='email']")))
        ef.clear(); ef.send_keys(email)
        pf = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        pf.clear(); pf.send_keys(password)
        try:
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        except Exception:
            pf.send_keys(Keys.RETURN)
        time.sleep(5)
        return "login" not in driver.current_url
    except Exception as e:
        print(f"⚠ Login error: {e}"); return False

# ── API ───────────────────────────────────────────────────────────────────────
def fetch_members(driver, mode="24h") -> list:
    is_24h    = mode == "24h"
    is_season = mode == "season"
    # "current" mode: all flags false returns current season contribution/departures
    payload   = json.dumps({
        "alliance_id":                      ALLIANCE_ID,
        "lifetime_stats":                   False,
        "last_24h_stats":                   is_24h,
        "last_season_stats":                is_season,
        "include_last_season_top_contributors": False
    })
    result = driver.execute_script("""
        return new Promise(resolve => {
            fetch('https://shippingmanager.cc/api/alliance/get-alliance-members', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: arguments[0]
            }).then(r => r.json())
              .then(d => resolve(d.data ? d.data.members : []))
              .catch(() => resolve([]));
        });
    """, payload)
    return result or []

def fetch_all_stats(driver) -> list:
    print("  Fetching 24h stats…")
    members_24h     = fetch_members(driver, "24h")
    time.sleep(1)
    print("  Fetching current season stats…")
    members_current = fetch_members(driver, "current")
    time.sleep(1)
    print("  Fetching last season stats…")
    members_last    = fetch_members(driver, "season")

    current_map = {m["user_id"]: m for m in members_current}
    last_map    = {m["user_id"]: m for m in members_last}
    combined    = []
    for m in members_24h:
        uid     = m["user_id"]
        current = current_map.get(uid, {})
        last    = last_map.get(uid, {})
        combined.append({
            "user_id":                  uid,
            "company_name":             m.get("company_name", "").strip(),
            "role":                     m.get("role", "member"),
            "contribution_24h":         int(m.get("contribution", 0) or 0),
            "departures_24h":           int(m.get("departures", 0) or 0),
            "contribution_season":      int(current.get("contribution", 0) or 0),
            "departures_season":        int(current.get("departures", 0) or 0),
            "contribution_last_season": int(last.get("contribution", 0) or 0),
            "departures_last_season":   int(last.get("departures", 0) or 0),
            "time_last_login":          m.get("time_last_login", 0),
            "is_rookie":                m.get("is_rookie", False),
        })
    return combined

# ── HISTORY ───────────────────────────────────────────────────────────────────
def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_history(history: list):
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")

def add_snapshot(history: list, members: list, timestamp: int) -> list:
    history.append({"timestamp": timestamp, "members": members})
    now = timestamp
    cutoff_14d  = now - (14 * 86400)
    cutoff_90d  = now - (90 * 86400)

    # Split into zones
    recent   = [s for s in history if s["timestamp"] >= cutoff_14d]   # keep all hourly
    mid      = [s for s in history if cutoff_90d <= s["timestamp"] < cutoff_14d]  # downsample to daily
    old_data = [s for s in history if s["timestamp"] < cutoff_90d]    # discard

    # Downsample mid zone to one snapshot per day (keep the last one of each day)
    day_buckets = {}
    for snap in mid:
        day = datetime.datetime.fromtimestamp(snap["timestamp"]).strftime("%Y-%m-%d")
        day_buckets[day] = snap  # last snapshot of each day wins
    downsampled = sorted(day_buckets.values(), key=lambda x: x["timestamp"])

    history = downsampled + recent
    return history

def get_prev_snapshot(history: list) -> dict:
    """Return user_id -> member dict for the previous snapshot."""
    if len(history) >= 2:
        return {m["user_id"]: m for m in history[-2]["members"]}
    return {}

def get_snapshot_at_offset(history: list, hours_ago: int) -> dict:
    """Return snapshot closest to N hours ago."""
    now = int(time.time())
    target = now - (hours_ago * 3600)
    best = None
    best_diff = float("inf")
    for snap in history:
        diff = abs(snap["timestamp"] - target)
        if diff < best_diff:
            best_diff = diff
            best = snap
    if best:
        return {m["user_id"]: m for m in best["members"]}
    return {}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def fmt_change(new_val, old_val):
    """Format a vs comparison with arrow and % change."""
    if old_val is None:
        return "N/A"
    new_val = int(new_val or 0)
    old_val = int(old_val or 0)
    diff = new_val - old_val
    if old_val == 0:
        return f"+{new_val:,}" if new_val > 0 else "—"
    pct = (diff / old_val) * 100
    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "=")
    return f"{arrow} {abs(diff):,} ({abs(pct):.1f}%)"

def rgb(r, g, b):
    return {"red": r/255, "green": g/255, "blue": b/255}


# ── ENCRYPTION ────────────────────────────────────────────────────────────────
def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES key from password using PBKDF2."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000, dklen=32)

def _xor_encrypt(data: bytes, key: bytes) -> bytes:
    """Simple XOR stream cipher using key stretched via SHA-256 chain."""
    out = bytearray(len(data))
    block = key
    ki = 0
    for i, b in enumerate(data):
        if ki >= len(block):
            block = hashlib.sha256(block).digest()
            ki = 0
        out[i] = b ^ block[ki]
        ki += 1
    return bytes(out)

def encrypt_data(plaintext: str, password: str) -> str:
    """
    Encrypt JSON string with password.
    Format: base64( salt(16) + iv_hash(32) + ciphertext )
    Uses PBKDF2 key derivation + XOR stream cipher.
    Returns base64 string safe to store in a public repo.
    """
    salt      = os.urandom(16)
    key       = _derive_key(password, salt)
    plainbytes = plaintext.encode("utf-8")
    cipher    = _xor_encrypt(plainbytes, key)
    # HMAC for integrity check
    mac       = hashlib.hmac_digest if hasattr(hashlib, "hmac_digest") else None
    import hmac as _hmac
    tag       = _hmac.new(key, cipher, hashlib.sha256).digest()
    payload   = salt + tag + cipher
    return base64.b64encode(payload).decode("ascii")

def hash_password(password: str) -> str:
    """Return a SHA-256 hex digest of the password for storage in JS."""
    return hashlib.sha256(password.encode()).hexdigest()

# ── GITHUB PUSH ───────────────────────────────────────────────────────────────
def push_to_github(data: dict, history: list):
    """Encrypt data and push to GitHub, triggering Netlify redeploy."""
    if not GITHUB_TOKEN:
        print("  ⚠ GITHUB_TOKEN not set — skipping website update")
        return

    # Build payload: current snapshot + last 14 days history
    payload = {
        "alliance":    ALLIANCE_NAME,
        "updated_at":  datetime.datetime.utcnow().isoformat() + "Z",
        "members":     data,
        "history":     history,  # up to 90 days (downsampled beyond 14d)
    }

    # Hash credentials for JS login check
    combined_hash = hash_password(DASHBOARD_USERNAME + ":" + DASHBOARD_PASSWORD)

    # Encrypt the member data with the password
    encrypted = encrypt_data(json.dumps(payload), DASHBOARD_PASSWORD)

    # Final JSON stored in repo — only contains hash + encrypted blob
    repo_json = json.dumps({
        "auth_hash": combined_hash,
        "payload":   encrypted,
    })

    # GitHub API — get current file SHA (needed for update)
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_DATA_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
    }

    sha = None
    try:
        req  = urllib.request.Request(api_url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        existing = json.loads(resp.read())
        sha = existing.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"  ⚠ GitHub GET error: {e.code}")

    # Push new content
    body = {
        "message": f"Update member stats {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
        "content": base64.b64encode(repo_json.encode()).decode(),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        body["sha"] = sha

    try:
        req_data = json.dumps(body).encode()
        req      = urllib.request.Request(api_url, data=req_data, headers=headers, method="PUT")
        resp     = urllib.request.urlopen(req, timeout=15)
        result   = json.loads(resp.read())
        pushed_path = result.get("content", {}).get("path", "unknown")
        print(f"  ✅ Pushed to GitHub → {pushed_path} → Netlify deploying…")
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()
        print(f"  ❌ GitHub push failed: {e.code} {body_err}")
    except Exception as e:
        print(f"  ❌ GitHub push failed: {e}")

# ── GOOGLE SHEETS ─────────────────────────────────────────────────────────────
def get_sheets_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_file(
        str(CREDENTIALS_FILE),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)

def ensure_sheet(service, title: str, index: int = None) -> int:
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    props = {"title": title}
    if index is not None:
        props["index"] = index
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": props}}]}
    ).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]

def delete_charts(service, sheet_id: int) -> list:
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    reqs = []
    for s in meta["sheets"]:
        if s["properties"]["sheetId"] == sheet_id:
            for chart in s.get("charts", []):
                reqs.append({"deleteEmbeddedObject": {"objectId": chart["chartId"]}})
    return reqs

# ── MAIN STATS SHEET ──────────────────────────────────────────────────────────
def write_stats_sheet(service, members: list, history: list):
    sheet_id = ensure_sheet(service, "Member Stats")
    now_str  = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    prev_snap   = get_prev_snapshot(history)
    snap_24h    = get_snapshot_at_offset(history, 24)
    snap_season = get_snapshot_at_offset(history, 24 * 7)  # approx season start

    sorted_m = sorted(members, key=lambda x: x["contribution_24h"], reverse=True)

    col_headers = [
        "Rank", "Company", "Role",
        "24h Contribution", "vs Last Hour", "vs Last 24h",
        "24h Departures", "vs Last Hour",
        "Season Contribution", "vs Last Hour",
        "Season Departures", "vs Last Hour",
        "Last Login"
    ]
    NUM_COLS = len(col_headers)

    rows = [
        [f"🏴‍☠️ {ALLIANCE_NAME} — Member Stats  |  Last updated: {now_str}"] + [""] * (NUM_COLS - 1),
        col_headers
    ]

    for i, m in enumerate(sorted_m, 1):
        uid     = m["user_id"]
        prev    = prev_snap.get(uid, {})
        p24     = snap_24h.get(uid, {})
        login_dt = datetime.datetime.fromtimestamp(
            m["time_last_login"]).strftime("%d/%m %H:%M") if m["time_last_login"] else "—"
        role_icon = {"ceo": "👑", "coo": "⭐", "management": "🔱"}.get(m["role"], "⚓")

        rows.append([
            i,
            m["company_name"],
            f"{role_icon} {m['role'].title()}",
            m["contribution_24h"],
            fmt_change(m["contribution_24h"], prev.get("contribution_24h")),
            fmt_change(m["contribution_24h"], p24.get("contribution_24h")),
            m["departures_24h"],
            fmt_change(m["departures_24h"], prev.get("departures_24h")),
            m["contribution_season"],
            fmt_change(m["contribution_season"], prev.get("contribution_season")),
            m["departures_season"],
            fmt_change(m["departures_season"], prev.get("departures_season")),
            login_dt
        ])

    # Totals
    rows.append([
        "TOTAL", f"{len(members)} members", "",
        sum(m["contribution_24h"] for m in members), "", "",
        sum(m["departures_24h"] for m in members), "",
        sum(m["contribution_season"] for m in members), "",
        sum(m["departures_season"] for m in members), "", ""
    ])

    # Write data
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Member Stats'!A1",
        valueInputOption="RAW",
        body={"values": rows}
    ).execute()

    # Formatting
    num_m    = len(sorted_m)
    requests = []

    # Title row
    requests.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 0, "endColumnIndex": NUM_COLS},
        "cell": {"userEnteredFormat": {
            "backgroundColor": rgb(30, 30, 60),
            "textFormat": {"foregroundColor": rgb(255, 215, 0), "bold": True, "fontSize": 12}
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat)"
    }})

    # Header row
    requests.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2,
                  "startColumnIndex": 0, "endColumnIndex": NUM_COLS},
        "cell": {"userEnteredFormat": {
            "backgroundColor": rgb(44, 44, 84),
            "textFormat": {"foregroundColor": rgb(255, 255, 255), "bold": True}
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat)"
    }})

    # Data rows - colour by 24h contribution
    for i, m in enumerate(sorted_m):
        row_idx = i + 2
        contrib = m["contribution_24h"]
        if contrib == 0:        bg = rgb(70, 20, 20)
        elif contrib >= 15000:  bg = rgb(20, 70, 30)
        elif contrib >= 8000:   bg = rgb(20, 55, 40)
        elif contrib >= 3000:   bg = rgb(25, 40, 65)
        elif contrib >= 500:    bg = rgb(55, 45, 15)
        else:                   bg = rgb(60, 25, 15)

        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row_idx,
                      "endRowIndex": row_idx+1, "startColumnIndex": 0, "endColumnIndex": NUM_COLS},
            "cell": {"userEnteredFormat": {
                "backgroundColor": bg,
                "textFormat": {"foregroundColor": rgb(220, 220, 220)}
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"
        }})

    # Totals row
    total_row = num_m + 2
    requests.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": total_row,
                  "endRowIndex": total_row+1, "startColumnIndex": 0, "endColumnIndex": NUM_COLS},
        "cell": {"userEnteredFormat": {
            "backgroundColor": rgb(44, 44, 84),
            "textFormat": {"foregroundColor": rgb(255, 215, 0), "bold": True}
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat)"
    }})

    # Column widths
    widths = [45, 210, 110, 130, 120, 120, 110, 120, 150, 120, 140, 120, 110]
    for i, w in enumerate(widths[:NUM_COLS]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i+1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})

    # Freeze
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 2}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
    }})

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": requests}).execute()

# ── HISTORY SHEET ─────────────────────────────────────────────────────────────
def write_history_sheet(service, history: list):
    ensure_sheet(service, "Member History")
    headers = ["Timestamp", "Company", "24h Contribution", "24h Departures",
               "Season Contribution", "Season Departures"]
    rows = [headers]
    for snap in history:
        ts_str = datetime.datetime.fromtimestamp(snap["timestamp"]).strftime("%d/%m %H:%M")
        for m in sorted(snap["members"], key=lambda x: x["contribution_24h"], reverse=True):
            rows.append([
                ts_str,
                m["company_name"],
                m["contribution_24h"],
                m["departures_24h"],
                m["contribution_season"],
                m["departures_season"]
            ])
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Member History'!A1",
        valueInputOption="RAW",
        body={"values": rows}
    ).execute()

# ── CHARTS SHEET ──────────────────────────────────────────────────────────────
def write_charts_sheet(service, members: list, history: list):
    """
    Clean dashboard layout:
    - 'Chart Data' hidden tab stores per-member time series (one column per member)
    - 'Charts' tab has 3 large clean bar charts: 24h Contrib, 24h Departures, Season Contrib
      ranked by value, plus a snapshot summary table at the top
    """
    charts_sheet_id   = ensure_sheet(service, "Charts")
    chartdata_sheet_id = ensure_sheet(service, "Chart Data")

    # Collect all unique members in current order (sorted by current 24h contrib)
    uid_order = [m["user_id"] for m in sorted(members, key=lambda x: x["contribution_24h"], reverse=True)]
    uid_names = {m["user_id"]: m["company_name"] for m in members}
    # Add any historical members not in current list
    for snap in history:
        for m in snap["members"]:
            if m["user_id"] not in uid_names:
                uid_names[m["user_id"]] = m["company_name"]
                uid_order.append(m["user_id"])

    all_rows   = []
    chart_reqs = []
    fmt_reqs   = []

    # Delete existing charts first
    chart_reqs.extend(delete_charts(service, charts_sheet_id))

    # Layout constants
    CHART_W      = 420   # px per chart
    CHART_H      = 300   # px per chart
    HEADER_ROWS  = 1     # member name header
    DATA_ROWS    = len(history) if history else 1
    SECTION_ROWS = HEADER_ROWS + DATA_ROWS + 3  # +3 spacer rows between members
    DATA_COLS    = 4     # A=timestamp, B=24h contrib, C=24h deps, D=season contrib

    current_row = 0

    for uid in uid_order:
        company = uid_names.get(uid, f"User {uid}")

        # ── Member header row ──────────────────────────────────────────────
        all_rows.append([f"📊  {company}"] + [""] * (DATA_COLS - 1))

        # ── Data table ────────────────────────────────────────────────────
        all_rows.append(["Timestamp", "24h Contribution", "24h Departures", "Season Contribution"])
        table_data_start = current_row + 2   # 0-indexed row of first data point
        for snap in history:
            ts_str = datetime.datetime.fromtimestamp(
                snap["timestamp"]).strftime("%d/%m %H:%M")
            member = next((m for m in snap["members"] if m["user_id"] == uid), None)
            if member:
                all_rows.append([
                    ts_str,
                    int(member.get("contribution_24h", 0) or 0),
                    int(member.get("departures_24h", 0) or 0),
                    int(member.get("contribution_season", 0) or 0),
                ])
            else:
                all_rows.append([ts_str, "", "", ""])

        table_data_end = table_data_start + DATA_ROWS  # exclusive

        # ── 3 spacer rows ─────────────────────────────────────────────────
        all_rows.append([])
        all_rows.append([])
        all_rows.append([])

        # ── Formatting: header row dark bg gold text ───────────────────────
        fmt_reqs.append({"repeatCell": {
            "range": {"sheetId": charts_sheet_id,
                      "startRowIndex": current_row, "endRowIndex": current_row + 1,
                      "startColumnIndex": 0, "endColumnIndex": DATA_COLS},
            "cell": {"userEnteredFormat": {
                "backgroundColor": rgb(30, 30, 60),
                "textFormat": {"foregroundColor": rgb(255, 215, 0), "bold": True, "fontSize": 11}
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"
        }})
        # Column header row
        fmt_reqs.append({"repeatCell": {
            "range": {"sheetId": charts_sheet_id,
                      "startRowIndex": current_row + 1, "endRowIndex": current_row + 2,
                      "startColumnIndex": 0, "endColumnIndex": DATA_COLS},
            "cell": {"userEnteredFormat": {
                "backgroundColor": rgb(44, 44, 84),
                "textFormat": {"foregroundColor": rgb(200, 200, 255), "bold": True, "fontSize": 9}
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"
        }})
        # Data rows alternating
        for i in range(DATA_ROWS):
            bg = rgb(28, 28, 45) if i % 2 == 0 else rgb(35, 35, 55)
            fmt_reqs.append({"repeatCell": {
                "range": {"sheetId": charts_sheet_id,
                          "startRowIndex": table_data_start + i,
                          "endRowIndex": table_data_start + i + 1,
                          "startColumnIndex": 0, "endColumnIndex": DATA_COLS},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": bg,
                    "textFormat": {"foregroundColor": rgb(200, 200, 200), "fontSize": 8}
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"
            }})

        # ── 3 charts side by side ─────────────────────────────────────────
        chart_specs = [
            ("24h Contribution", 1, 2, rgb(100, 200, 255)),   # col B
            ("24h Departures",   2, 3, rgb(100, 255, 160)),   # col C
            ("Season Contribution", 3, 4, rgb(255, 180, 80)), # col D
        ]
        for chart_idx, (title, col_start, col_end, color) in enumerate(chart_specs):
            chart_reqs.append({"addChart": {"chart": {
                "spec": {
                    "title": f"{company}\n{title}",
                    "titleTextFormat": {"bold": True, "fontSize": 10,
                                        "foregroundColor": rgb(255, 215, 0)},
                    "backgroundColor": rgb(25, 25, 50),
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "NO_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS",
                             "title": "",
                             "format": {"fontSize": 7, "foregroundColor": rgb(180, 180, 180)}},
                            {"position": "LEFT_AXIS",
                             "title": "",
                             "format": {"fontSize": 7, "foregroundColor": rgb(180, 180, 180)}}
                        ],
                        "domains": [{"domain": {"sourceRange": {"sources": [{
                            "sheetId": charts_sheet_id,
                            "startRowIndex": table_data_start,
                            "endRowIndex": table_data_end,
                            "startColumnIndex": 0, "endColumnIndex": 1
                        }]}}}],
                        "series": [{"series": {"sourceRange": {"sources": [{
                            "sheetId": charts_sheet_id,
                            "startRowIndex": table_data_start,
                            "endRowIndex": table_data_end,
                            "startColumnIndex": col_start,
                            "endColumnIndex": col_end
                        }]}},
                            "targetAxis": "LEFT_AXIS",
                            "color": color,
                            "lineStyle": {"width": 2}
                        }],
                        "headerCount": 0
                    }
                },
                "position": {"overlayPosition": {
                    "anchorCell": {
                        "sheetId": charts_sheet_id,
                        "rowIndex": current_row,
                        "columnIndex": DATA_COLS + 1 + (chart_idx * 6)
                    },
                    "offsetXPixels": 0, "offsetYPixels": 0,
                    "widthPixels": CHART_W,
                    "heightPixels": CHART_H
                }}
            }}})

        current_row += SECTION_ROWS

    # Write all data
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Charts'!A1",
        valueInputOption="RAW",
        body={"values": all_rows}
    ).execute()

    # Set column widths for data table
    col_widths = [110, 130, 120, 140]
    fmt_reqs.extend([{"updateDimensionProperties": {
        "range": {"sheetId": charts_sheet_id, "dimension": "COLUMNS",
                  "startIndex": i, "endIndex": i+1},
        "properties": {"pixelSize": w}, "fields": "pixelSize"
    }} for i, w in enumerate(col_widths)])

    # Apply formatting
    if fmt_reqs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": fmt_reqs}
        ).execute()

    # Apply charts (separate call — charts must be added after data exists)
    if chart_reqs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": chart_reqs}
        ).execute()

# ── INSTALL DEPS ──────────────────────────────────────────────────────────────
def ensure_deps():
    try:
        import google.auth
        import googleapiclient
    except ImportError:
        print("📦 Installing Google API libraries…")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
            "google-auth", "google-auth-oauthlib", "google-api-python-client", "--quiet"])

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    ensure_deps()
    print("🏴‍☠️  Alliance Member Stats Tracker")
    print(f"   {ALLIANCE_NAME} | every {CHECK_INTERVAL_MINUTES} min\n")

    if not CREDENTIALS_FILE.exists():
        print(f"❌ Missing: {CREDENTIALS_FILE}"); sys.exit(1)

    email, password, account_name = load_credentials()
    print(f"🔐 Using account: {account_name}")

    driver = start_browser()
    print("🔐 Logging in…")
    if not login(driver, email, password):
        print("❌ Login failed"); driver.quit(); sys.exit(1)
    print("✅ Logged in\n")

    service = get_sheets_service()
    history = load_history()

    while True:
        now = int(time.time())
        print(f"⏱  {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"🔍 Fetching member stats…")

        try:
            members = fetch_all_stats(driver)
            if members:
                history = add_snapshot(history, members, now)
                save_history(history)

                print(f"  📊 Writing Member Stats tab…")
                write_stats_sheet(service, members, history)

                print(f"  📜 Writing Member History tab…")
                write_history_sheet(service, history)

                print(f"  📈 Writing Charts tab…")
                write_charts_sheet(service, members, history)

                print(f"  🌐 Pushing to GitHub…")
                push_to_github(members, history)

                print(f"  ✅ All done — {len(members)} members tracked")
            else:
                print("  ⚠ No member data returned")
        except Exception as e:
            import traceback
            print(f"  ❌ Error: {e}")
            traceback.print_exc()
            try:
                login(driver, email, password)
            except Exception:
                pass

        print(f"\n⏳ Next update in {CHECK_INTERVAL_MINUTES} minutes…\n")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
