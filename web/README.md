# Standing landing site

Published at **https://standing.joelhanson.com** via GitHub Pages
(`.github/workflows/pages.yml`).

## DNS (one-time)

At your DNS host for `joelhanson.com`:

| Type | Name | Target |
| --- | --- | --- |
| `CNAME` | `standing` | `Joel-hanson.github.io` |

Then in the Standing repo: **Settings → Pages → Custom domain** →
`standing.joelhanson.com`, enable **Enforce HTTPS**.

Repo must be **public** (or GitHub Pro) for Pages on the free plan.
