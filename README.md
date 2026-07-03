# CertifyMe Open edX Plugin

Open edX plugin that integrates CertifyMe with Open edX.

## Features

- Automatic certificate issuance
- Badge issuance
- Instructor dashboard
- Student certificates
- CertifyMe REST API integration

Status: Under Development

## Installation (Tutor, editable / dev mode)

This plugin registers itself with edx-platform through the standard
Open edX Django **plugin architecture** (`lms.djangoapp` / `cms.djangoapp`
entry points) — no separate Tutor plugin or manual `INSTALLED_APPS`
edit is required.

1. Add it as a private requirement so it gets `pip install`-ed into the
   `openedx` image:

   ```bash
   mkdir -p "$(tutor config printroot)/env/build/openedx/requirements"
   echo "-e /path/to/openedx-certifyme" >> "$(tutor config printroot)/env/build/openedx/requirements/private.txt"
   ```

   (For a published release, use `pip install openedx-certifyme` /
   add `openedx-certifyme==<version>` to `OPENEDX_EXTRA_PIP_REQUIREMENTS`
   instead of the editable path.)

2. Rebuild and restart the `openedx` image:

   ```bash
   tutor images build openedx
   tutor dev launch   # or `tutor local launch`
   ```

3. Verify the plugin loaded — the LMS logs should contain:

   ```
   CertifyMe plugin loaded (app=openedx_certifyme, verbose_name=CertifyMe Certificate Integration).
   ```

4. Verify the health endpoint:

   ```bash
   curl http://local.edly.io/certifyme/health
   # {"plugin": "openedx-certifyme", "status": "ok", "version": "0.1.0", "enabled": false}
   ```
