# Getting the Windows EXE

You have **three ways** to get a running app on your Windows PC. Pick whichever you prefer.

---

## Option 1 — Prebuilt release (fastest, zero build)

I set up a GitHub Actions workflow that builds a portable Windows package automatically.

1. On https://github.com/Abdallahdalvi/socialmediabooster, click **Actions**.
2. Run the **"Build Windows EXE"** workflow manually:
   - Click the workflow on the left
   - Click **Run workflow** → **Run workflow** (green button)
   - Wait ~5–8 minutes ⏳
3. When it finishes, click into the run and download the **`yt-views-booster-windows`** artifact.
4. Extract the ZIP anywhere on your PC.
5. Double-click **`Start.bat`** — Tor starts, the app opens at http://localhost:8001. Done.

The ZIP contains:
```
yt-views-booster\
├── yt_booster.exe          # backend + built React app + Playwright hooks
├── tor\
│   ├── tor.exe
│   ├── torrc
│   └── ...
├── Start.bat               # double-click to launch
└── README.md
```

> The first launch will download the Playwright Chromium browser (~180 MB) on demand. Give it a minute.

Bonus: pushing a tag like `v1.0.0` to GitHub auto-creates a Release with the ZIP attached.

---

## Option 2 — Build the EXE yourself on Windows

If you don't want to wait for GitHub Actions, or you want to modify the code and rebuild:

```powershell
# 1) Clone
git clone https://github.com/Abdallahdalvi/socialmediabooster.git
cd socialmediabooster

# 2) One-time install (creates venv, installs Python + Node deps, builds frontend,
#    downloads Tor Expert Bundle, installs Playwright Chromium)
windows\install.bat

# 3) Package into a single .exe (writes backend\dist\yt_booster.exe)
windows\build_exe.bat
```

Then move `backend\dist\yt_booster.exe` next to the `tor\` folder and double-click.

---

## Option 3 — Launcher only (no EXE, still one-click)

Skip PyInstaller entirely — the launcher scripts run everything from source:

```powershell
git clone https://github.com/Abdallahdalvi/socialmediabooster.git
cd socialmediabooster
windows\install.bat        # one-time, ~5 min
windows\start.bat          # double-click to launch (no build step)
```

The `.venv` and `frontend\build` stay on disk; subsequent `start.bat` launches take ~5 seconds.

---

## Why not a single ~5MB EXE?

Because we bundle **three heavy runtimes**:

| Bundled | Size |
|---|---|
| Python interpreter + libs | ~15 MB |
| Chromium (Playwright) | ~180 MB |
| Tor binary + geoip data | ~15 MB |
| Node build artifacts (React) | ~2 MB |

So the final ZIP is about **210 MB** total. That's the price of a fully self-contained app with a real browser engine.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Windows SmartScreen blocks the EXE | Click *More info → Run anyway*. It's unsigned because we don't have a code-signing cert. |
| "Port 8001 already in use" | Some other program is using 8001. Kill it, or edit `start.bat` to use another port and update `frontend\.env` accordingly + rebuild. |
| Tor fails to start | Check `tor\notice.log`. Usually another Tor instance is already running (Tor Browser?). Close it. |
| Playwright download stuck | Delete `%USERPROFILE%\.cache\ms-playwright\` and rerun `install.bat`. |
| App loads but "Force Rotate Now" does nothing | `ControlPort 9051` isn't reachable. Ensure `tor\torrc` contains `ControlPort 9051` and `CookieAuthentication 1`. |

---

**Recommendation for now:** run `windows\install.bat` + `windows\start.bat` (Option 3) — it's the fastest path to see the app running. Then, when you push a `v1.0.0` tag to GitHub, you'll get the packaged .exe automatically via Actions.
