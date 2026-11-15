# Control pLLM from the iPhone

The private controller and chat website have separate links:

| Use | URL | What must be running |
|---|---|---|
| Start/stop instances and use their optional terminal | `https://ello-lin.tailad2999.ts.net:8443` | Tailscale and the lightweight control app |
| Chat with Qwen | `https://ello-lin.tailad2999.ts.net` | Qwen, Chat, and foreground chat sharing |

The persistent controller route does not depend on chat sharing. Stopping
Qwen, Chat, or chat sharing leaves the controls reachable. Qwen and Chat
never start just because the PC or controller starts.

## One-time setup on the PC

Current verified setup (2026-10-16): the persistent :8443 route is active,
the controller user service is enabled/running, and pre-login lingering is
enabled. Real HTTPS page/API access and a harmless shell start/input/stop
round trip passed. A real reboot and iPhone/cellular test remain pending.

For reproducing this setup on the PC, persistent sharing requires the
owner's Ubuntu password:

```bash
cd ~/Projects/pLLM
bash scripts/setup-phone-control.sh
```

Enter the password at sudo's prompt, not in chat. The command:

1. Reads the PC's Tailscale identity and restricts remote access to that
   exact owner account. Tagged devices are rejected by this setup.
2. Installs a user-level `pllm-control.service` for the controller only.
3. Enables private persistent HTTPS :8443 → local controller :8787, leaving
   the existing chat route on :443 independent.
4. Enables controller startup and user lingering for pre-login availability.
   It does not start the model/UI or change sleep settings.

Use `bash scripts/setup-phone-control.sh --after-login` instead if controller
availability after desktop login is enough. Fresh installations do not
enable either mode until this explicit setup is run. `--prepare-only`
writes the protected configuration and disabled unit without enabling
sharing/startup.

## Daily use

1. Turn on the PC and let Ubuntu boot. It must stay awake and online.
2. Connect Tailscale on the iPhone using the PC owner's account.
3. Open <https://ello-lin.tailad2999.ts.net:8443> in Safari.
4. Start Qwen and Chat. Wait for their statuses to become Running.
5. Start **Phone access** for chat sharing. If sudo requests a password,
   expand its terminal and use masked input.
6. Open Chat from the app, or visit <https://ello-lin.tailad2999.ts.net>.
7. Stop Qwen/Chat when finished. The lightweight controller stays available.

Safari's Share → Add to Home Screen can provide a control-app launcher.
No separate control password is needed: Tailscale Serve supplies the
authenticated identity and the app checks that it matches the configured
owner. Other tailnet users and requests without that identity are denied
before page content or API tokens are returned.

## Automatic startup setting

Expand **Control settings** and change **Start control app automatically**.
Turning it off disables future controller autostart without stopping the
current session or its instances. Turning it on enables the installed user
service. Models still start only through their Start buttons.

Pre-login mode uses `loginctl enable-linger` for the owner, keeping the
systemd user manager available without a login. Disabling pLLM autostart
does not disable lingering for unrelated user services.

Quit control app remains a desktop action. It is hidden/blocked through
the phone link to preserve the controller needed to start things again.
Each managed instance can still be stopped remotely.

## Access and recovery

The backend still binds only to localhost. Tailscale terminates HTTPS and
supplies the owner identity. API tokens, strict Host/Origin checks, and
framing restrictions remain. The trusted proxy is the local Tailscale
daemon; local programs retain the PC user's existing privileges.

Check on the PC if the phone controls are unavailable:

```bash
systemctl --user status pllm-control.service
tailscale serve status
```

Start a deliberately stopped controller:

```bash
systemctl --user start pllm-control.service
```

Remove just the persistent remote-control route:

```bash
sudo tailscale serve --bg --https=8443 off
```

This leaves the :443 chat route alone. Avoid `tailscale serve reset` for
this operation because it removes unrelated sharing configuration too.

Configuration: ignored `.data/control/remote.json` (0600), with owner login,
exact origin, and login mode. Unit: `~/.config/systemd/user/pllm-control.service`.
Reboot/iPhone/cellular acceptance remains an owner test; unit verification
does not establish those results.

## Sources

- [Tailscale Serve identity headers](https://tailscale.com/docs/features/tailscale-serve)
- [Persistent Serve and reboot behavior](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [systemd user lingering](https://www.freedesktop.org/software/systemd/man/252/loginctl.html)
