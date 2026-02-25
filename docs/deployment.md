# Deployment (Cloudflare Free)

## 1) Deploy API Worker

From `apps/api`:

```powershell
npm install
npx wrangler deploy
```

Save output URL:
- `https://hoopslab-api.<subdomain>.workers.dev`

## 2) Create or Update D1 schema

From `apps/api`:

```powershell
npx wrangler d1 execute hoopslab-db --file ../../data/schema/schema.sql
```

## 3) Run ETL artifact and upload data

From `data/etl`:

```powershell
poetry install
poetry run nightly --out ../../data/etl_out
```

From `apps/api`:

```powershell
npx wrangler d1 execute hoopslab-db --file ../../data/etl_out/d1_upload.sql
```

## 4) Deploy Web (Cloudflare Pages)

Cloudflare Pages settings:
- Root directory: `apps/web`
- Build command: `npm install && npm run build`
- Framework preset: Next.js
- Deploy command: `true` (or `npm run deploy`, which is a no-op in this repo)

Environment variable:
- `NEXT_PUBLIC_API_BASE=https://hoopslab-api.<subdomain>.workers.dev`

## 5) GitHub Actions secrets needed

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `BALLDONTLIE_API_KEY` (optional)
