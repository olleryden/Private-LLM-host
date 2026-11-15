# personal/

Local-only context for this project. Git ignores everything in this folder
except this README, so the folder exists in the remote repository, but its
contents never leave this PC through Git.

Use it for information that helps working sessions but should not be pushed:

- personal notes and preferences;
- account identifiers (Konnect, Tailscale, device names);
- network details (IP addresses, exposed services);
- detailed security findings.

Assistants working on this project should read these files for context
when they exist. When a fact is too sensitive for the pushed docs, write it
here and leave a general pointer in the pushed docs.

| File | Purpose |
|---|---|
| `CONTEXT.md` | Free-form owner context and preferences |
| `ENVIRONMENT.md` | Account IDs, hostnames, addresses, versions, and certificate details |
| `SECURITY_REVIEW.md` | Detailed exposure findings, exposed-credential log, hardening status |

Rules:

- **No credentials.** Passwords, API keys, and private keys belong in
  `.secrets/` or a password manager. This folder is for context, not
  secrets.
- **No Git backup.** These files are not backed up by Git. Include this
  folder in local backups if its notes matter.
- **Check before committing.** `git check-ignore -v personal/<file>` should
  report every file here except `README.md`.
