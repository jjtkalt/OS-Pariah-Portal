# Grid Service Bot — In-World Setup

Deliver calendar announcements, group chat/notices, and follower IMs from the portal queue using a dedicated bot avatar.

## Portal configuration

1. Run migrations `008_calendar_events.sql` and `009_calendar_group_delivery.sql`.
2. In **System Settings → Grid Service Bot**:
   - `grid_bot_uuid` — Robust PrincipalID of the bot avatar
   - `grid_bot_api_token` — long random secret (same value goes in the notecard)
   - `grid_bot_announce_region_uuid` — default region for grid-wide announcements (optional)
   - `grid_bot_announce_group_uuid` — default group for chat/notice announcements (optional)
3. In **Calendar & Events** settings, configure default group chat/notice toggles.
4. Enable timer: `sudo systemctl enable --now pariah-worker-calendar.timer`
5. Monitor the queue at **Admin → Bot Queue** (requires Manage Settings or Manage Events).

## Create the bot avatar

1. Create a grid account (e.g. `Grid Helper`) with high `userLevel` (service tier).
2. Copy its UUID into `grid_bot_uuid`.
3. Do **not** grant portal RBAC; the bot never logs into the website.
4. Rez the bot on your announce region (or a region that hosts most events).
5. Add the bot to your announce group with permission to send group chat and group notices.

## Install the LSL scripts

1. Copy [`GridBotConfig.example.txt`](GridBotConfig.example.txt) to an in-world notecard named exactly **`GridBotConfig`**.
2. Set `PORTAL_URL` (e.g. `https://portal.yourgrid.com`) and `BOT_TOKEN` (matches portal config).
3. Add both scripts to the same object:
   - [`GridServiceBot.lsl`](GridServiceBot.lsl) — polls queue, IM + region chat
   - [`GridServiceBotGroup.lsl`](GridServiceBotGroup.lsl) — group chat + group notices (OpenSim)
4. Reset scripts. Touch the bot to force a manual poll.

### Delivery rules

| `delivery_channel` | In-world action |
|--------------------|-----------------|
| `im` | `llInstantMessage` to `target_uuid` |
| `region` | `llSay` on announce channel when region name matches |
| `group_chat` | `llInstantMessageGroup` (delegated to group script) |
| `group_notice` | `osGroupNotice` with subject (delegated to group script) |

Wrong-region region messages ack with `error=wrong_region` and are automatically re-queued (up to 20 retries).

Per-event overrides: set **Announce group UUID** and group chat/notice toggles when editing an event.

## API reference (for custom bots)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/bot/queue?format=text&token=…` | Pipe-delimited: `id\|type\|target_uuid\|region\|group\|delivery\|subject\|body` |
| `GET /api/bot/queue` + header `X-Grid-Bot-Token` | JSON `{ "messages": [ … ] }` |
| `GET /api/bot/ack/<id>?success=1&token=…` | Mark delivered (LSL-friendly) |
| `GET /api/bot/ack/<id>?error=wrong_region` | Re-queue for retry when bot is on wrong region |
| `POST /api/bot/ack/<id>` | JSON body `{ "success": true }` |
| `GET /api/bot/status?token=…` | Queue counts by status |

## Headless test client (no avatar)

```bash
export GRID_BOT_API_TOKEN='your-token'
python scripts/grid_bot_client.py --url https://portal.example.com --once
python scripts/grid_bot_client.py --url https://portal.example.com --loop --interval 30
```

## systemd units

| Unit | Role |
|------|------|
| `pariah-worker-calendar.timer` | Fires every 15 minutes |
| `pariah-worker-calendar.service` | Runs `worker.py calendar` |

Install with the OS-Pariah RPM or copy from [`../pariah-worker-calendar.service`](../pariah-worker-calendar.service) and [`../pariah-worker-calendar.timer`](../pariah-worker-calendar.timer).
