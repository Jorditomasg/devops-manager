# Performance Diagnosis — Tray Restore & Long-Uptime Slowdown

**Status:** Phase 4 (Instrument) complete. Awaiting data from key computer.

**Branch is THROWAWAY.** It exists only to transfer this context across machines. After diagnosis + fix lands on `master`, delete this branch. The single source of truth for this investigation is this file plus the `perf_probe.log` it produces.

This document is fully self-contained. It does **not** depend on engram memory (which is per-machine in Claude Code) or on the original chat history. Everything needed to continue is below.

## 0. First message to paste into Claude on the OTHER computer

After you `git checkout perf/diagnose-tray-uptime` on the key computer and run the data-collection procedure (§4), open Claude Code in the repo root and paste this verbatim:

> Estoy continuando una sesión de `/diagnose` sobre performance en devops-manager. El contexto completo (problema, hipótesis, instrumentación, procedimiento, mapa de interpretación, fixes pre-planeados) está en `PERF_DIAGNOSIS.md` en la raíz del repo. La instrumentación ya está aplicada en la rama `perf/diagnose-tray-uptime`. Acabo de correr la app siguiendo la sección §4 y tengo el archivo `perf_probe.log`. Por favor:
>
> 1. Leé `PERF_DIAGNOSIS.md` completo.
> 2. Leé `perf_probe.log` completo.
> 3. Para cada métrica en §5 decime qué confirma o descarta.
> 4. Identificá la(s) hipótesis confirmada(s) y procedé con la fase 5 (fix + regresión) usando los fixes pre-planeados en §6.
> 5. Cuando termines de aplicar el fix, repetí el procedimiento §4 y verificá la regresión según §7. Después actualizá §10 ("Findings") de este doc con qué confirmó qué.

## 1. Problem

Two perf complaints reported by the user on **Windows** with **~10 repo cards** in the typical workspace:

- **A — Tray restore slow.** Restoring the app window from the system tray feels sluggish — content takes noticeable time to render. Happens **every time**, independent of uptime.
- **B — Long-uptime slowdown.** After the laptop has been plugged in for **several days** with services running in the background, the whole UI gets slower over time.

When both happen together (services running + app open for days + restore from tray), the worst case stacks.

User asked whether picking customtkinter was the wrong choice. **CTk is not the suspected root cause.** It contributes (canvas-based rounded corners are expensive to repaint), but "after days of uptime" is accumulation — logic-level, not framework-level. Switching frameworks would be a 4-week rewrite for an unproven win; first prove which sub-system actually leaks.

### Architectural facts to know before reading hypotheses

- The app uses **customtkinter** (Tk under the hood) for the UI.
- **Each repo card** is a composite widget with a header, expandable panel, status badges, combos, multiple buttons.
- **Background work per card:** a git-badge refresh on a 30 s timer, a docker-compose status poller (when compose files exist), branch fetching, status detection from log streams.
- **System tray** uses `pystray`. `_on_window_unmap` creates a `pystray.Icon` and calls `run_detached()`; `_restore_window` calls `stop()` on it.
- **Global stdout/stderr is redirected** to a thread-safe queue and drained every 100 ms onto the main thread into a CTkTextbox capped at 1000 lines. Any `print` from anywhere in the app (including services started by the app via `subprocess`) flows through this queue.
- **Constants** that govern poll cadences live in `gui/constants.py`:
  - `BADGE_REFRESH_MS = 30_000`
  - `DOCKER_POLL_MS = 15_000`
  - `GIT_BADGE_SEMAPHORE_COUNT = 3` (limits concurrent `git status` subprocesses).
- **No test suite exists** in this repo. Verification is empirical — re-run the probe.

## 2. Ranked hypotheses

Each hypothesis must be falsifiable. The predictions below tell you what the data should look like if the hypothesis is true.

| # | Hypothesis | Where in code | Falsifying prediction |
|---|---|---|---|
| **H1** | Thread / timer accumulation. `_refresh_badge` spawns a fresh `threading.Thread` per card every 30 s. With 10 cards × 24 h that is ~28 800 daemon threads spawned. Plus a `while True` compose-status thread per card. | `gui/repo_card/_git.py:62`, `gui/repo_card/_docker.py:148` | `threads=` and `after=` grow **monotonically** with uptime. RSS grows >50 MB / 30 min. |
| **H2** | Tray restore = full Tk repaint. `_restore_window` does `withdraw()` → `deiconify()`. Tk on Windows must recreate HWNDs; CTk's rounded-corner canvases repaint all at once. | `gui/app.py:_restore_window` | `restore#N took=Xms` is **flat across restores** (~the same #1 and #10), but X scales with card count. |
| **H3** | Stdout redirect saturates main loop when services are noisy. `StreamRedirector` queues every byte of stdout/stderr; a 100 ms timer drains it onto the main thread into a CTkTextbox. | `gui/app.py:StreamRedirector`, `gui/app.py:_setup_global_log_redirect`, `gui/app.py:_poll_global_log` | Frequent `drain_burst count=`>100 lines. `queue=` >50 sustained. Slowdown correlates with services being up vs down. |
| **H4** | `pystray.Icon` leak. Each minimize creates a **new** `pystray.Icon` + `run_detached()`. If `stop()` does not fully release the Win shell tray slot, accumulating Win32 message pumps slow restore. | `gui/app.py:_on_window_unmap` (creates Icon), `gui/app.py:_restore_window` (stops Icon) | `restore#N took=Xms` **grows monotonically** across consecutive restores #1 → #10. |
| H5 | `_check_tray_status` cost. Walks all children every 5 s. Discarded as low-impact — kept here for completeness. | `gui/app.py:_check_tray_status` | Negligible. |

## 3. Instrumentation in place (`[DEBUG-perf]`)

| File | Symbol | Purpose |
|---|---|---|
| `gui/_perf_probe.py` (NEW, throwaway) | `perf_snapshot`, `time_restore`, `log_drain` | Self-contained probe module. Writes to console **and** `perf_probe.log` at repo root so silent-launcher users (`run.vbs`) still get output. |
| `gui/app.py` `_do_update_tray_status` | calls `perf_snapshot(self)` | Periodic snapshot every ~30 s (every 6th tick of the 5 s tray timer). |
| `gui/app.py` `_drain_global_log_queue` | calls `log_drain(len(items))` | Tracks stdout/stderr volume; prints `drain_burst` only when >100. |
| `gui/app.py` `_restore_window._show` | wraps body with `time_restore()` + `update_idletasks()` | Times user-perceived restore latency including paint. |

### Snapshot line format

```
[DEBUG-perf] t=<uptime_s> threads=<N> after=<pending_after_callbacks> rss=<MB> cards=<N> queue=<qsize> buf=<global_log_buf_len> drain_max=<max_single_drain> drain_total=<cumulative_lines>
```

### Restore line format

```
[DEBUG-perf] restore#<N> took=<ms>
```

## 4. How to collect data (on the key computer)

```cmd
git fetch origin
git checkout perf/diagnose-tray-uptime
scripts\win\install.bat   # only if first run on this machine
scripts\win\run.bat       # IMPORTANT: use .bat (console), not run.vbs — but log file is written either way
```

Then:

1. Start the app, leave default workspace loaded (~10 cards).
2. Start 2–3 noisy services (Spring Boot is ideal — verbose stdout).
3. Use the app normally for **20–30 min**. Optional: leave it running longer if you can reproduce the days-of-uptime feel.
4. **Minimize → restore via tray icon 10 times in a row.** Pace it normal — not as fast as possible.
5. Stop services. Close app.
6. Send back the contents of `perf_probe.log` at the repo root.

## 5. Data interpretation

Look at the `perf_probe.log`:

| Observed pattern | Confirms |
|---|---|
| `threads=` grows monotonically (e.g. 12 → 18 → 25 → 33 over 30 min) | **H1** |
| `after=` grows monotonically | **H1** |
| `rss=` grows >50 MB over 30 min with stable card count | **H1** or **H3** |
| `drain_burst count=` appears frequently, `queue=` stays >50 | **H3** |
| `restore#N took=` is roughly constant (~the same #1..#10) | **H2** is the cause for tray slowness |
| `restore#N took=` grows monotonically across restores | **H4** (pystray leak) |
| `restore#N took=` correlates with `threads=` value at restore time | mixed H1+H2 |

## 6. Likely fixes (Phase 5)

Do **not** apply blindly — wait for data to confirm which hypothesis is real. These are pre-planned remedies so the next session can move fast.

- **If H1 confirmed:** introduce a single `ThreadPoolExecutor(max_workers=2)` shared across cards for badge refresh. Replace per-cycle `threading.Thread(target=_run, daemon=True).start()` in `_refresh_badge` (`gui/repo_card/_git.py:62`) and in `_start_compose_status_thread` (`gui/repo_card/_docker.py:148`) with submissions to the pool. Audit other `threading.Thread(...).start()` calls in repo_card for the same pattern.

- **If H2 confirmed:** the cheapest fix is to avoid `withdraw()`+`deiconify()` round-trip and just `iconify()`/`deiconify()` (Tk keeps HWNDs alive). Cost: app stays on the taskbar instead of being purely tray-bound — needs UX decision. Alternative: keep the window mapped, just hide it off-screen via `geometry('+9999+9999')`, restore by replaying the saved geometry. Less invasive but feels hackish. Most invasive: rebuild restore path so cards repaint progressively, not all at once.

- **If H3 confirmed:** stop redirecting stdout/stderr globally to a Tk textbox. Either drop the global log feature, or write to a rotating file on a background thread and only show the tail in the UI when the user opens the detached log window. Code: `_setup_global_log_redirect` (`gui/app.py:442`), `_poll_global_log` (`gui/app.py:471`).

- **If H4 confirmed:** create the `pystray.Icon` **once** at startup and reuse it across minimize cycles. Update its image/title instead of recreating. Code: `_on_window_unmap` (`gui/app.py:759-764`).

## 7. Regression test

There is no Python test suite in this repo. The "feedback loop" for Phase 5 is the same `perf_probe.log` — after applying a fix, repeat the data collection procedure and compare the relevant metric:

- H1 fix → `threads=` should plateau (not grow with time) and `after=` should stay bounded.
- H2 fix → `restore#N took=` should drop substantially (target: <150 ms for 10 cards).
- H3 fix → `drain_burst` lines should disappear or become rare even with noisy services.
- H4 fix → `restore#N took=` should be identical across restores #1..#10.

## 8. Cleanup when done

This branch is throwaway. Recommended flow:

1. On the key computer, cherry-pick or re-implement the confirmed fix(es) onto a **new** branch off `master` (e.g. `fix/perf-thread-pool` or `fix/perf-tray-restore`). Do **NOT** include the `[DEBUG-perf]` instrumentation in the fix branch.
2. PR the fix branch into master. Verify with a fresh probe run on the fix branch (you can temporarily cherry-pick the probe commit `0718132` to validate, then drop).
3. Delete this branch locally and on origin: `git branch -D perf/diagnose-tray-uptime && git push origin --delete perf/diagnose-tray-uptime`.

If for some reason you DO want to keep the probe but strip it cleanly:

```bash
rm gui/_perf_probe.py
rm PERF_DIAGNOSIS.md
rm perf_probe.log
# revert the [DEBUG-perf] hunks in gui/app.py (3 locations)
grep -rn '\[DEBUG-perf\]' gui/   # should return zero matches
```

## 9. Memory note

Engram is **per-machine**. The original session ran on a WSL host that no longer has authority over this diagnosis. **Do not** rely on `mem_search` to recover context — assume the engram store on the key computer is empty for this topic. This Markdown file is the canonical source of truth.

(For historical reference only, the original session saved memory under topic key `devops-manager/perf/2026-05-12-tray-restore-uptime-slowdown` on its own host. Not portable.)

## 10. Findings (fill in after analysis)

Leave this section blank for now. When the next session interprets `perf_probe.log`, append:

- Date of run, machine, uptime at end of run.
- Per-hypothesis verdict: **confirmed / rejected / inconclusive** with the specific metric line from the log that justified the call.
- Decision: which fix from §6 was applied (or a new approach if data pointed elsewhere).
- Result of regression run after the fix.

This becomes the audit trail for the fix's commit message.
