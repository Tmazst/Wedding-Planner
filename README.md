# Wedding Planner

A simple wedding-planning web app for Eswatini couples. The first MVP focuses on financial planning: couples can create a wedding, add budget categories, collect vendor quotations and select the quotation they want to use.

## Current MVP

- Account registration and login
- Basic wedding setup
- Budget target and live financial summary
- Budget categories
- Multiple vendor quotations per category
- Selected quotation tracking
- Free plan with a configurable four-budget-item limit
- E40 Standard project upgrade through MojaPOS / MTN MoMo
- E30 stakeholder access with owner-pays or invitee-pays choice
- Private, expiring invitation links and shared project access
- Live budget totals while quotations are added and selected
- Couple profile photo with a friendly placeholder
- Account details, active plan and payment history
- Font Awesome-enhanced navigation and actions
- Installable UMSHADO PWA with branded app icons
- The PWA never caches private wedding pages or payment flows; planning requires a connection
- Responsive, simple interface
- Professional on-screen wedding report and downloadable PDF
- Live, wedding-specific team presence and planning activity updates
- Persistent activity history for joined members and budget decisions
- Page progress feedback for forms and internal navigation

## Run locally

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
flask --app run db upgrade
pytest -q
flask --app run run --debug
```

Open `http://127.0.0.1:5000`.

## First database migration

The initial Alembic migration is included. For later model changes:

```bash
flask --app run db migrate -m "Describe the change"
flask --app run db upgrade
```

## Next small milestones

1. Wedding programme planning
2. Invitation and guest list
3. Selected information sharing through openWA

## Pricing configuration

Pricing and free-tier limits are controlled from `.env`:

```ini
FREE_BUDGET_ITEM_LIMIT=4
OWNER_PLAN_PRICE=40.00
STAKEHOLDER_PRICE=30.00
```

Local proofing uses MojaPOS mock mode. Before production, set both mock options to
`false`, add the real API key and configure `/api/payment/callback` in MojaPOS.

## Payment tracing during live testing

The server writes a private, rotating `instance/payments.log` (2 MB, two
backups) and the same short events to the Gunicorn journal. Only payment IDs,
transaction references, mode, HTTP status and timing are logged; never API keys,
phone numbers, or gateway payloads. Ensure the Gunicorn user can write to
`instance/`, then follow the log:

```bash
sudo tail -f /var/www/wedding-planner/Wedding-Planner/instance/payments.log
```

`gateway_accepted mode=mock` means **no HTTP request was made**. Live gateway
acceptance shows `mode=live`, an HTTP status, and gateway ID. The app reuses
pending records to avoid double charging; confirm their state with MojaPOS before
retrying. Do not share the log publicly. Before taking real payments, confirm
webhook signature verification against MojaPOS's actual signing scheme.

## Realtime production setup

Apply the latest migration before restarting the app:

```bash
flask --app run db upgrade
```

For the current small VPS, run one threaded Gunicorn worker so WebSocket
connections stay on the same process:

```bash
gunicorn --workers 1 --threads 100 --timeout 120 --bind 127.0.0.1:8000 run:app
```

Nginx must pass WebSocket upgrade headers for `/socket.io/`:

```nginx
location /socket.io/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "Upgrade";
    proxy_set_header Host $host;
}
```

The single-worker setup is recommended initially. If the app later runs across
multiple processes or servers, configure `SOCKETIO_MESSAGE_QUEUE` with Redis
and add sticky sessions at the load balancer before increasing worker count.
