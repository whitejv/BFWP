# Ingest LaunchAgent

macOS launchd supervises ingest. The committed file is a template
(`com.bfwp.ingest.plist.example`). `bfwp-start.sh` at the repo root fills in this
machine's paths and installs the result at `~/Library/LaunchAgents/com.bfwp.ingest.plist`.

The agent runs `bfwp-ingest run` in the foreground from the ingest virtualenv.

- `RunAtLoad` starts it at login.
- `KeepAlive` restarts it if the process exits.
- `ThrottleInterval` is 10 seconds, so a crash loop does not respawn immediately.
- Logs go to `~/BFWP-data/logs/ingest.log`.

The Mac mini user must be logged in to the GUI. The agent is a user agent (`gui/$UID`),
which is the right scope for a machine that stays logged in. Cursor starts the MCP server
itself. The twin is started by hand.

```bash
./bfwp-start.sh
./bfwp-stop.sh
```
