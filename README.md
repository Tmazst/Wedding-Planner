# Wedding Planner

A simple wedding-planning web app for Eswatini couples. The first MVP focuses on financial planning: couples can create a wedding, add budget categories, collect vendor quotations and select the quotation they want to use.

## Current MVP

- Account registration and login
- International phone-number registration with country selection and E.164 storage
- Basic wedding setup
- Budget target and live financial summary
- Budget categories
- Multiple vendor quotations per category
- Selected quotation tracking
- Free plan with a configurable four-budget-item limit
- E60 Standard project upgrade through MojaPOS / MTN MoMo
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
- Server-managed administrator roles with full feature access
- Two revocable, unrestricted test-account slots
- Private admin dashboard with session visits and registration totals
- Floating WhatsApp support link on every page
- Privacy Notice and Terms acceptance recorded at registration
- Authenticated couple-photo delivery, account export and privacy-preserving deletion
- Explicit confirmation before every MoMo request
- AI Planning Assistant for platform help, project summaries, budgets and quotations
- Separate, expiring confirmation before every assistant-created project change

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

For local HTTP only, set `SESSION_COOKIE_SECURE=false` in `.env`. Keep it `true`
on the HTTPS production site.

## Production privacy maintenance

Apply migrations after each deployment and run the retention cleanup once a
day (for example from cron or a systemd timer):

```bash
flask --app run db upgrade
flask --app run data-retention-cleanup
```

The cleanup removes old operational visits, analytics entries, payment log
entries and expired unpaid invitations according to the retention-day values
in `.env`. Couple photos are stored under `instance/uploads` and are delivered
only through an authenticated route. On first startup after this update, the
app moves existing couple photos out of the public static directory.

## First database migration

The initial Alembic migration is included. For later model changes:

```bash
flask --app run db migrate -m "Describe the change"
flask --app run db upgrade
```

## Super admin and test accounts

Administrator privileges are managed only from the server CLI. After applying
the migration, create the first super admin:

```bash
python super_admin_cli.py bootstrap --name "UMSHADO Admin" --email admin@example.com --phone 26876123456
```

Create the two unrestricted test accounts by running the following command
twice with the actual tester details:

```bash
python super_admin_cli.py create-test-user --name "Test Couple 1" --email test1@example.com --phone 26876000001
python super_admin_cli.py create-test-user --name "Test Couple 2" --email test2@example.com --phone 26876000002
```

The CLI prompts for passwords and re-verifies the super admin before privileged
changes. Use `python super_admin_cli.py --help` for role, test-access, password
reset and account-listing commands. Super admins, administrators and the two
test accounts can use all package-controlled features without payment records.

## Next small milestones

1. Wedding programme planning
2. Invitation and guest list
3. Selected information sharing through openWA

## Pricing configuration

Pricing and free-tier limits are controlled from `.env`:

```ini
FREE_BUDGET_ITEM_LIMIT=4
OWNER_PLAN_PRICE=60.00
STAKEHOLDER_PRICE=30.00
```

Local proofing uses MojaPOS mock mode. Before production, set both mock options to
`false`, add the real API key and configure `/api/payment/callback` in MojaPOS.
International phone numbers can register, but MoJaPOS self-payment is restricted
to the comma-separated ISO country codes in `MOJAPOS_SUPPORTED_COUNTRIES` (the
safe default is `SZ`). Owners with a supported number may still pay for an
international stakeholder's invitation.

## UMSHADO Planning Assistant

The assistant uses the OpenAI Responses API with function calling. The API key
must remain in the VPS environment and must never be included in browser code:

```ini
ASSISTANT_ENABLED=true
OPENAI_API_KEY=your-server-side-project-key
OPENAI_MODEL=gpt-5.4-mini
ASSISTANT_MAX_MESSAGE_LENGTH=1200
ASSISTANT_REQUEST_LIMIT=20
```

Assistant conversations are not stored by UMSHADO. Requests use `store=false`.
Only authorised project data needed for the current request is sent. Write tools
create a 15-minute server-side confirmation and do not change a project until the
logged-in user confirms it. Payments, account deletion, permissions and photo
access are excluded from the assistant. Run `flask --app run db upgrade` after
deploying to create the pending-confirmation table.

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
