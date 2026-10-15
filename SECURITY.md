# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability** (or go straight to
   <https://github.com/Dawn-Of-Justice/bharat-sourcer/security/advisories/new>).
3. Describe the issue, the affected component and how to reproduce it.

Do not open a public issue, pull request or discussion for a suspected vulnerability, and do
not share details publicly until a fix is available and the maintainers agree to disclosure.

Helpful details to include:

- The affected component (`backend/` API, `frontend/` app or `server.mjs` proxy, deployment
  configuration) and the commit or deployed URL you tested.
- Steps to reproduce, the expected result and the actual result.
- The impact you believe it has (for example, reading another user's project or share link,
  bypassing sign-in or quotas, or exposing a credential).

Reports are handled on a best-effort basis by the project maintainers. We will acknowledge the
report in the advisory thread, keep you updated there, and credit you in the advisory if you
would like.

## Supported versions

Only the latest commit on `main` and the currently deployed site are supported. Older
commits and branches do not receive fixes.

## Testing guidelines

When investigating an issue, please:

- Use your own account, guest session or project. Do not access, modify or delete data that
  belongs to other people.
- Avoid denial-of-service, load testing, automated scanning at volume, and anything that
  drives up AI (Gemini) or cloud costs.
- Do not test against the third-party seller websites the app links to; they are out of scope.
- Stop and report as soon as you find an issue that exposes data or credentials.

## Secrets

This repository should never contain credentials. Local configuration belongs in ignored
files such as `backend/.env` and `frontend/.env.local`; see the `.env.example` files for the
variable names. The Firebase web configuration (`apiKey`, `authDomain`, `projectId`,
`appId`) is public by design and is served to the browser at runtime; it is not a secret.
If you find a real credential in the repository or its history, report it privately as
described above.
