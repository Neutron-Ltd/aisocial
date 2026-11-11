# Security Policy

## Reporting a vulnerability

Please report security issues privately by email to **info@neutron.com.bd**.
Do not open a public GitHub issue for security problems.

Include:

- a description of the issue and its impact
- steps to reproduce, or a proof of concept
- the commit or version you tested

We aim to acknowledge reports within 5 business days and will keep you
informed while we work on a fix. Please give us reasonable time to address
the issue before disclosing it publicly.

## Scope

In scope: the NEUTX server (`neutx/`), the web UI (`WebUI/`) and the bundled
workflows. Areas of particular interest are authentication and sessions,
OAuth handling, token storage, file uploads and access to media, and
anything that lets one user read or change another user's data.

ComfyUI is a separate upstream project and is not part of this repository.
Report ComfyUI issues to that project. ComfyUI has no authentication of its
own; do not expose it to the internet.
