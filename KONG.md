# Kong AI Gateway

Last updated: 2026-11-16

Kong AI Gateway is an optional OpenAI-compatible front door for the local
Qwen model. Its data plane runs on this PC as a Docker container. It gets
configuration from Kong Konnect, Kong's hosted control plane in the EU
region. Prompts and replies stay on the PC. Konnect stores routes, providers,
models, and settings, and receives usage statistics. On 2026-11-15 the owner
chose Konnect as an explicit exception to the local-only rule; this
exception covers gateway configuration and analytics only.

```text
local client ──► Kong data plane (127.0.0.1:8100/v1) ──► vLLM (127.0.0.1:8000)
                       │  adds the vLLM key itself
                       └─ outbound only: config sync + usage stats ──► Konnect (EU)
```

Konnect never connects to vLLM and cannot send requests into the PC. If
Konnect or the internet is unavailable, the running data plane keeps serving
its last configuration; changes apply after it reconnects.

## Current state

Verified 2026-11-16 unless marked otherwise.

| Item | Value |
|---|---|
| Container | `kong-ai-gateway`, image `kong/kong-ai-gateway:2.3.0-distroless`, Docker host networking |
| Client endpoint | `http://127.0.0.1:8100/v1`, loopback only |
| Upstream | vLLM `http://127.0.0.1:8000/v1/chat/completions`, unchanged |
| Konnect gateway | `ello-ai-gateway`; node `ello-lin` Connected, In sync, Compatible (owner-observed) |
| Model provider | `ello-lin-vllm`: type vLLM, authentication "Provided by AI gateway", header `Authorization` |
| AI model | `qwen3.8-27b`, reached at base path `/v1`; no client auth strategy yet |
| Upstream key | Container env `PLLM_VLLM_AUTH` = `Bearer <.secrets/vllm-api-key>`; intended Konnect value `{vault://env/pllm-vllm-auth}` |

Tests passed:

- A non-streaming chat sent with no client key returned 200.
- A streaming chat sent with a dummy client key also returned 200.
- vLLM itself returns 401 without its key. Kong therefore adds a valid key
  and overrides any `Authorization` header the client sends.
- Kong's own added latency was about 2 ms per request.
- Port 8100 refuses connections on the LAN, Tailscale, and Docker-bridge
  addresses.

Kong answers `/v1/models` with 404, so clients cannot list models through
it. These tests do not show whether Konnect holds the vault reference or a
pasted key. Click the eye icon on the provider's header value to confirm
it reads `{vault://env/pllm-vllm-auth}`.

Not done yet:

- Open WebUI still calls vLLM directly; switching it to Kong is pending.
- No Kong consumers or auth strategy are configured.
- The container's restart policy is unknown.
- Kong is not managed by pLLM Control.

## Using it

Both Qwen (pLLM Control → Qwen) and the Kong container must be running.

```bash
curl http://127.0.0.1:8100/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Hello"}]}'
```

OpenAI-compatible clients on this PC use these settings:

- Base URL: `http://127.0.0.1:8100/v1`.
- Model: `qwen3.8-27b`.
- API key: any placeholder, until an auth strategy exists.

Clients that need a model list must have `qwen3.8-27b` entered manually.
Streaming works.

| Symptom | Meaning |
|---|---|
| Connection refused on :8100 | Kong container not running: `docker start kong-ai-gateway` |
| `502 Bad Gateway` | Kong is up, but vLLM on :8000 is not running or not ready |
| `404 no Route matched` | Wrong path or model name, or Konnect configuration not synced |
| `401` from upstream | Kong is sending a wrong or missing vLLM key; check the provider header and `PLLM_VLLM_AUTH` |

## Switching Open WebUI to Kong (pending)

Open WebUI stores connection settings in its database (`.data/open-webui`).
Those saved values override the environment variables in
`scripts/serve-webui.sh`, so change them in the UI.

1. Open WebUI → Admin Panel → Settings → Connections → OpenAI API. Open the
   settings of the `http://127.0.0.1:8000/v1` connection.
2. Set URL to `http://127.0.0.1:8100/v1`.
3. Set Key to a placeholder such as `kong`. Open WebUI then stops holding
   the vLLM key.
4. Under Model IDs, add `qwen3.8-27b`. Without it, Open WebUI shows no model,
   because Kong does not answer `/v1/models`. The connection-verify button
   fails for the same reason; that is expected.
5. Save and send a message. A reply proves the Kong path, because Open WebUI
   no longer has vLLM's address or key.

Existing chats keep working because the model name is unchanged. After the
switch, Chat depends on the Kong container as well as Qwen.
`scripts/serve-webui.sh` still seeds `:8000` for a fresh database; update
it when this becomes the default.

## Managing access

Access has two layers.

1. **Who can reach Kong.** Kong listens only on `127.0.0.1:8100`, so only
   programs on this PC can call it. To allow owner devices, share it through
   Tailscale Serve, as Open WebUI is shared. Never expose it on the LAN or
   the internet.
2. **Who Kong lets through.** These are configured in Konnect, on the AI
   gateway:

| Konnect entity | Purpose | Where |
|---|---|---|
| Consumer | One person, device, or app with its own API key. Konnect shows a generated key only once. | Consumers tab → New consumer → API key |
| Auth strategy | Require a valid key (or OpenID Connect) on a model | Auth strategies tab; select it in the model's "Authentication and access" section |
| Consumer group + ACL | Limit which groups may use which model | Group consumers; enable "Restrict access with an ACL" on the model |
| Policies | Per-consumer rate limits and token budgets | Policies tab |

A model without an auth strategy accepts every request that reaches Kong.
That is safe today only because Kong is loopback-only.

Revoke access by deleting that consumer's key or the consumer.

OpenAI-style clients send `Authorization: Bearer <key>`, but Kong's key
check reads an `apikey` header by default. Set the strategy's key name to
match the clients, and test before relying on it.

Kong guards only traffic that goes through Kong:

- vLLM still accepts any local program holding the shared key in
  `.secrets/vllm-api-key`.
- Open WebUI has its own logins.
- Through Open WebUI, Kong sees only Open WebUI itself, from `127.0.0.1`,
  with one key. It cannot tell which device or user is behind a request;
  see ARCHITECTURE.md. Per-device identity requires each device to call
  Kong directly with its own consumer key.

## Why it is set up this way

- **Port 8100, not 8000.** vLLM, Open WebUI, pLLM Control, and the tests all
  use `:8000`. pLLM Control also treats any listener on `:8000` as Qwen.
  Kong originally published 8000 and 8443, which blocked vLLM and made the
  control app report Qwen as running.
- **Host networking.** Kong can reach vLLM on loopback, so vLLM never has
  to listen on another interface. Kong's proxy is pinned to `127.0.0.1`.
  The admin API, Kong Manager, and status listeners are turned off, so
  nothing new opens on the LAN or Tailscale.
- **Environment vault for the vLLM key.** The key stays in the container on
  this PC instead of being stored in Konnect.

## Operations

- **Status:** Konnect → AI Gateways → `ello-ai-gateway` → Data plane nodes.
- **Start/stop:** `docker start kong-ai-gateway` and
  `docker stop kong-ai-gateway`.
- **Logs:** `docker logs --tail 50 kong-ai-gateway`.
- **Boot behavior:** check with
  `docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' kong-ai-gateway`.
  `no` means manual start after reboot. Any other value starts Kong with
  Docker, which conflicts with the project's off-by-default boot
  preference unless the owner accepts it.
- **Recreating the container** (new key, image upgrade, listener change):
  carry over every `KONG_*` variable, including the Konnect endpoints and
  data-plane certificate. SETUP_LOG.md §22 has the equivalent `docker run`.
- **Rotating the vLLM key:**
  1. Write a new key to `.secrets/vllm-api-key`.
  2. Restart Qwen.
  3. Recreate the Kong container so `PLLM_VLLM_AUTH` carries the new key.
  4. Update any client that still calls vLLM directly, for example Open
     WebUI before its switch.

  The current key was exposed in an assistant session on 2026-11-16, so
  rotation is pending.
- **Data-plane certificate:** `~/kong-ai/cluster.crt` and `cluster.key`
  (`CN=local-kong-ai`, valid until 2027-11-15). Konnect lists two
  data-plane certificates. Delete the one that does not match the local
  certificate after confirming which one is in use.

## References

- [Kong vLLM provider](https://developer.konghq.com/ai-gateway/ai-providers/vllm/)
- [AI Model Providers](https://developer.konghq.com/ai-gateway/entities/ai-model-provider/)
- [AI Auth Strategies](https://developer.konghq.com/ai-gateway/entities/ai-auth-strategy/)
- [AI Consumers](https://developer.konghq.com/ai-gateway/entities/ai-consumer/)
- [AI Gateway 2.x concepts](https://developer.konghq.com/ai-gateway/ai-gateway-v2-concepts/)
- [Configure AI Gateway on-prem](https://developer.konghq.com/ai-gateway/configure-on-prem/) (the fully local alternative not chosen)
