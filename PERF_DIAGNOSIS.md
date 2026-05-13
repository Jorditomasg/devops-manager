# Performance Diagnosis — Tray Restore & Long-Uptime Slowdown

**Status:** Phase 4 (Instrument) complete. Awaiting data from key computer.

This document is a self-contained handoff. A future session (or human) can pick up here without prior chat context. Engram topic key for cross-session recall: `devops-manager/perf/2026-05-12-tray-restore-uptime-slowdown`.

## 1. Problem

Two perf complaints on Windows 10/11 with ~10 repo cards loaded:

- **A — Tray restore slow.** Restoring the app window from the system tray feels sluggish — content takes noticeable time to render.
- **B — Long-uptime slowdown.** After the laptop has been plugged in for days (services running in the background), the whole UI gets slower over time.

User asked whether picking customtkinter was the wrong choice. **CTk is not the suspected root cause.** It contributes (canvas-based rounded corners are expensive to repaint), but "after days of uptime" points to accumulation, which is logic-level, not framework-level.

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

```bash
rm gui/_perf_probe.py
rm PERF_DIAGNOSIS.md
rm perf_probe.log
# revert the [DEBUG-perf] hunks in gui/app.py (3 locations)
grep -rn '[DEBUG-perf]' gui/   # should return zero matches
```

Or simpler: merge the fix into master, then drop this branch entirely.

## 9. Engram

Topic key: `devops-manager/perf/2026-05-12-tray-restore-uptime-slowdown`

A future Claude session should `mem_search` with that key to retrieve full context, including hypothesis tradeoffs and reasoning.
