# CertifyMe Open edX Plugin

Open edX plugin that automatically issues [CertifyMe](https://certifyme.online)
credentials when a learner passes a course. The plugin is a thin bridge —
all certificate design, templating, and delivery logic lives in CertifyMe;
this package only talks to its REST API and keeps a local record of what
was requested.

## Features

- Admin-editable configuration (regional server, API token, template ID,
  credential fields, auto-issue toggle) with full change history.
- Automatic issuance on course completion, via the Open edX Hooks
  Extension Framework — never blocks an LMS request; all API calls happen
  in a Celery task.
- Automatic retries with exponential backoff for transient CertifyMe
  failures; permanent failures are recorded with a reason and can be
  retried manually from Django admin or the instructor tools page.
- Learner-facing "My Certificates" page (with a link to the CertifyMe-hosted
  certificate) and a public certificate verification page.
- Course-staff "instructor tools" page: search/filter, manual issue, bulk
  issue for a whole cohort, retry.

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
- **CertifyMe API contract**: confirmed via a real, successful live call
  (not a guess) — see `api.py`'s module docstring for the full detail.
  In particular:
  - The working endpoint is the regional one, e.g.
    `POST https://apac.platform.certifyme.dev/api/v2/credential` — see
    `servers.py`. CertifyMe's public API reference documents a generic
    `https://my.certifyme.online/api/v2/credential` which consistently
    returned `500` in testing against a real account; the regional URL
    (matching CertifyMe's own Moodle plugin, `local_certifyme`) worked.
  - Auth is the raw API token in the `Authorization` header (no `Bearer`
    prefix).
  - `template_ID` must be sent as a JSON number, not a string.
  - No organization-id concept — an account is scoped entirely by its API
    token + regional server.
  - No dedicated course/completion-date field — course data can only reach
    the credential via `custom_fields` (see Configuration below).
  - The response **does** carry a stable id (`credential_UID`) and a
    verification URL (`credential_url`) — captured as `certificate_id`/
    `verification_url` on `CertifyMeCertificate`.
  - No badge, revoke, or resend endpoint is confirmed to exist. CertifyMe's
    public API reference does document `GET`/`PUT`/`DELETE` by credential
    id (retrieve/edit/delete) — not yet implemented here, only issuance.

## Installation (Tutor)

1. For local development, bind-mount the plugin so Tutor builds it as an
   editable install and keeps it live-editable in the container:

   ```bash
   tutor mounts add /path/to/openedx-certifyme
   ```

   For a published release instead, add it to `OPENEDX_EXTRA_PIP_REQUIREMENTS`:

   ```bash
   tutor config save --append OPENEDX_EXTRA_PIP_REQUIREMENTS=openedx-certifyme==<version>
   ```

2. Rebuild and restart the images (`openedx` for `tutor local`, `openedx-dev`
   for `tutor dev`):

   ```bash
   tutor images build openedx-dev   # or `openedx` for a local/production deploy
   tutor dev launch                 # or `tutor local launch`
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
| Server | Which CertifyMe regional server this account is on (APAC/EU2/US1/Butterfly) |
| API Token | CertifyMe API token (masked in the admin list view) |
| Template ID | CertifyMe credential template ID |
| Text | Free-text label shown on the credential (e.g. job title, organization) |
| Verify mode | Identity-verification mode: None / SSN / Code / Passport Number |
| Verify code | Required by CertifyMe when Verify mode isn't "None" |
| License number | Optional license number to display on the credential |
| Custom fields | One `FieldName=value` per line, sent as `Custom.FieldName`. Supports `{course_name}`, `{student_name}`, `{student_email}`, `{date}` tokens — this is the only way to get the course name onto the credential, e.g. `Course={course_name}` |
| Auto issue certificates | Issue automatically when a learner passes |
| API timeout / max retries | Tuning for the HTTP client |

There is no "Test connection" action: CertifyMe has no confirmed
non-mutating endpoint to check against. Use the instructor tools page's
manual **Issue Certificate** to confirm a token/template pair actually
works.

## Usage

- **Learners**: `/certifyme/certificates/` lists their certificates, each
  linking to the CertifyMe-hosted certificate and a local verify page.
- **Course staff**: `/certifyme/instructor/<course_id>/` for manual issue,
  bulk issue, retry, search, and filtering. Requires course staff/instructor
  role or platform staff.
- **Support/ops**: Django admin → **CertifyMe Certificates** for a
  read-only audit log (status, retry count, failure reason, raw API
  response) across all courses, with a bulk **Retry** action.

## Troubleshooting

- **Certificates never get issued**: check `Enabled` and
  `Auto issue certificates` are both on in the current configuration, and
  that a Celery worker is consuming the LMS default queue.
- **"CertifyMe is not configured yet" errors**: an API token is required
  before any API call will be attempted.
- **A specific certificate is stuck FAILED**: check `failure_reason` on
  the row (Django admin or instructor tools). A `401`/`403` means the API
  token is wrong; a `404` means the template ID doesn't exist on the
  selected server (per CertifyMe's own troubleshooting docs). Permanent
  failures are not auto-retried — fix the underlying issue, then use the
  **Retry** action.
- **Health check flooding logs**: it logs at `DEBUG`, not `INFO`, precisely
  because liveness probes hit it constantly — raise your log level if you
  need to see it.
- **Certificates stuck retrying with a connection/timeout error**: a real
  successful issuance call was observed taking ~20 seconds (CertifyMe
  appears to generate and upload the credential image before responding),
  which is why `API timeout / max retries` defaults to a 30s timeout — if
  you've lowered it, raise it back up rather than assuming the API is down.
