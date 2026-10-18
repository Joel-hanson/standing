# Standing landing site

Published at **https://standing.joelhanson.com** via GitHub Pages
(`.github/workflows/pages.yml`).

## DNS (one-time)

At Cloudflare for `joelhanson.com`:

| Type | Name | Target | Proxy |
| --- | --- | --- | --- |
| `CNAME` | `standing` | `Joel-hanson.github.io` | DNS only (grey cloud) |

Then: **Settings → Pages → Source: GitHub Actions**, custom domain
`standing.joelhanson.com`, **Enforce HTTPS**.

Do **not** set Pages to “Deploy from a branch” — that enables GitHub’s
`pages-build-deployment` job alongside this workflow.

Repo must be **public** (or GitHub Pro) for Pages on the free plan.
