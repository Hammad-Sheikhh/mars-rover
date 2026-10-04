# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through [GitHub Security Advisories](https://github.com/Hammad-Sheikhh/mars-rover/security/advisories/new). Include:

* what you found and where (file and line, or endpoint)
* steps to reproduce
* the impact you expect

You should get a response within 7 days.

## Scope

* Firmware in `rover1/` and `cam1/`
* The Supabase schema and policies in `docs/supabase/`
* Leaked credentials anywhere in the repository or its history

## How secrets are handled

| Secret | Where it lives |
|---|---|
| WiFi / AP passwords, Supabase URL + anon key | `rover1/secrets.h`, `cam1/secrets.h` (git-ignored) |
| Reference copy for the team | `.env` (git-ignored) |
| Supabase `service_role` key | Never in this repo, never on a device |

* CI runs [gitleaks](https://github.com/gitleaks/gitleaks) on every push and pull request.
* The Supabase anon key is compiled into firmware, so treat it as public. Data is protected by row-level security (see `docs/supabase/schema.sql`), not by keeping that key hidden.

## If a secret leaks

1. **Rotate it first.**
   * WiFi password: change it on the router.
   * Supabase key: regenerate it in Project Settings → API.
2. Update your local `secrets.h` and reflash both boards.
3. Purge the secret from git history with `git filter-repo --replace-text`, force-push, and have every collaborator re-clone.
4. Review Supabase logs for unexpected activity.

## Known limitations

See "Known gaps" in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#known-gaps-tracked-for-future-work). The most important are that TLS certificates are not validated and the local AP endpoints have no authentication.
