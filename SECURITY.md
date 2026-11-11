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

This repository contains a static UI prototype and a small local preview
server (`scripts/serve.py`). The preview server is intended for local
development only and binds to `127.0.0.1` by default; do not expose it to
the internet.

ComfyUI is a separate upstream project and is not part of this repository.
Report ComfyUI issues to that project.
