# Project Execution Preferences

## Persistent Mode

Keep the user-selected full development mode: complete the authorized task and appropriate verification autonomously. Do not expand unrelated scope or repeatedly ask for already-granted permission.

## Daily Development

- The user works in CMD and prefers copyable startup commands in every code-change handoff.
- Use `scripts\dev.cmd` for daily development. Without arguments it opens three interactive service terminals; `web`, `ai`, and `api` run one service in the current terminal.
- Vue runs with Vite HMR on 127.0.0.1:5173. Do not restart or production-build the frontend just to make ordinary Vue/CSS changes visible.
- Python runs with Uvicorn reload on 127.0.0.1:8091. Reload interrupts in-process recognition tasks; check for active tasks before deliberately restarting it. Preserve results and explain task recovery when needed.
- Java runs from source using `spring-boot:run` on 127.0.0.1:8090. Java still needs compilation; the current setup has no file watcher or automatic compilation. After Java edits, instruct the user to stop that terminal with Ctrl+C and rerun `scripts\dev.cmd api`.
- Do not use Maven package or the packaged jar as the routine development launch path. Run builds/tests at relevant validation points, not as a mandatory step on every service start or after every tiny edit.
- Keep `scripts/start.ps1 -Build` for jar-based delivery validation. Do not describe `spring-boot:run` alone as automatic Java hot reload.
- State whether changes are already live and identify the specific service that needs restarting. When no service restart is needed, say so.
- Always provide a copyable CMD command after code changes, with `cd /d "C:\Users\LJL\Documents\ChatGPT\只会教学平台开发"` when needed. If only frontend code changed, explain that Vite should update it automatically and use `scripts\dev.cmd web` only if the server is not running.

## Startup Safety

- Check ownership and in-progress jobs before stopping a listener; do not kill unrelated node/java/python processes.
- Ports are fixed; occupied ports must fail clearly rather than silently start a second app on another port.
- Never expose `.env` credentials in logs, docs, commits, or tool output.
