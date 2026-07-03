# CertifyMe Open edX Plugin

Open edX plugin that automatically issues [CertifyMe](https://certifyme.online)
certificates (and optionally badges) when a learner passes a course. The
plugin is a thin bridge — all certificate design, templating, and delivery
logic lives in CertifyMe; this package only talks to its REST API and keeps
a local record of what was issued.

## Features

- Admin-editable configuration (API URL/key, org/template IDs, auto-issue
  toggles, enable/disable) with a one-click "Test connection" action.
- Automatic issuance on course completion, via the Open edX Hooks
  Extension Framework — never blocks an LMS request; all API calls happen
  in a Celery task.
- Automatic retries with exponential backoff for transient CertifyMe
  failures; permanent failures are recorded with a reason and can be
  retried manually from Django admin or the instructor tools page.
- Optional automatic badge issuance alongside certificates.
- Learner-facing "My Certificates" page and a public certificate
  verification page.
- Course-staff "instructor tools" page: search/filter, manual issue, bulk
  issue for a whole cohort, retry, revoke, resend email.

## Architecture notes

- **Registration**: uses edx-platform's native Django plugin architecture
  (`lms.djangoapp` / `cms.djangoapp` entry points + a `plugin_app` config in
  `apps.py`), not a bespoke Tutor plugin. No `INSTALLED_APPS` edits, no core
  changes.
- **Course-completion signal**: subscribes to
  `openedx_events.learning.signals.COURSE_PASSING_STATUS_UPDATED`, the Hooks
  Extension Framework event edx-platform's own grading app emits whenever a
  learner's passing status changes. Event payload field names have shifted
  across Open edX releases before; the handler logs the raw payload and
  fails closed (logs + returns) rather than crashing grade processing if a
  field is ever missing.
- **Student/instructor pages**: the real student dashboard and legacy
  instructor dashboard are edx-platform core templates with no supported
  third-party injection point (that only exists for the newer React MFEs, a
  separate frontend project). Rather than patch core templates, this
  plugin serves its own small, self-contained pages under `/certifyme/...`.
- **CertifyMe API contract**: CertifyMe's exact OpenAPI reference wasn't
  available while building this, so `api.py` follows conventional REST
  patterns (Bearer auth, `/api/v1/...` resource paths). Endpoint paths and
  payload shapes are centralized as class constants in
  `CertifyMeAPIClient` — check them against CertifyMe's real API docs and
  adjust if needed before going live.

## Installation (Tutor)

1. Add it as a private requirement so it gets `pip install`-ed into the
   `openedx` image:

   ```bash
   mkdir -p "$(tutor config printroot)/env/build/openedx/requirements"
   echo "-e /path/to/openedx-certifyme" >> "$(tutor config printroot)/env/build/openedx/requirements/private.txt"
   ```

   For a published release, use `openedx-certifyme==<version>` instead of
   the editable path (or add it to `OPENEDX_EXTRA_PIP_REQUIREMENTS`).

2. Rebuild and restart the `openedx` image:

   ```bash
   tutor images build openedx
   tutor dev launch   # or `tutor local launch`
   ```

3. Run migrations (Tutor does this automatically on `launch`/`init`; to run
   by hand):

   ```bash
   tutor dev run lms ./manage.py lms migrate openedx_certifyme
   ```

4. Make sure a Celery worker for the LMS queue is running (Tutor runs one
   by default) — automatic issuance depends on it.

5. Verify the plugin loaded: the LMS log should contain
   `CertifyMe plugin loaded (app=openedx_certifyme, ...)`, and:

   ```bash
   curl http://local.edly.io/certifyme/health
   # {"plugin": "openedx-certifyme", "status": "ok", "version": "0.1.0", "enabled": false}
   ```

## Configuration

Go to Django admin → **CertifyMe Configuration** → *Add*. Every save
creates a new versioned row (full change history, nothing is overwritten):

| Field | Purpose |
|---|---|
| Enabled | Master on/off switch for the whole integration |
| API URL | Base URL of the CertifyMe API |
| API Key | CertifyMe API key (masked in the admin list view) |
| Organization ID | CertifyMe org certificates are issued under |
| Template ID | Default certificate template |
| Auto issue certificates | Issue automatically when a learner passes |
| Auto issue badges | Also issue a badge on the same trigger |
| API timeout / max retries | Tuning for the HTTP client |

Select the row and use **Actions → Test connection to CertifyMe** to
confirm the URL/key work before enabling auto-issue.

## Usage

- **Learners**: `/certifyme/certificates/` lists their certificates, each
  linking to the CertifyMe-hosted certificate and a local verify page.
- **Course staff**: `/certifyme/instructor/<course_id>/` for manual issue,
  bulk issue, retry, revoke, resend, search, and filtering. Requires course
  staff/instructor role or platform staff.
- **Support/ops**: Django admin → **CertifyMe Certificates** for a
  read-only audit log (status, retry count, failure reason, raw API
  response) across all courses, with a bulk **Retry** action.

## Troubleshooting

- **Certificates never get issued**: check `Enabled` and
  `Auto issue certificates` are both on in the current configuration, and
  that a Celery worker is consuming the LMS default queue.
- **"CertifyMe is not configured yet" errors**: API URL and API key are
  both required before any API call (including the public verify page's
  live status check) will be attempted.
- **A specific certificate is stuck FAILED**: check `failure_reason` on
  the row (Django admin or instructor tools) — permanent failures (bad
  key, rejected payload) are not auto-retried. Fix the underlying issue,
  then use the **Retry** action.
- **Health check flooding logs**: it logs at `DEBUG`, not `INFO`, precisely
  because liveness probes hit it constantly — raise your log level if you
  need to see it.
