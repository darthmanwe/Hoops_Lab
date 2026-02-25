# Hoops_Lab
HoopsLab: NBA + EuroLeague Intelligence Platform

## Current Status

Implemented backbone:
- `apps/api`: Cloudflare Worker API with routes:
  - `/health`
  - `/players/search`
  - `/players/:id`
  - `/teams/:id`
  - `/games`
  - `/games/:id`
  - `/leaderboards/gravity`
  - `/leaderboards/clutch`
  - `/compare`
- `apps/web`: Next.js app pages:
  - `/`
  - `/games`
  - `/games/[id]`
  - `/leaderboards`
  - `/compare`
- `data/schema/schema.sql`: canonical database schema + indexes
- `data/etl`: ETL job that generates a D1 upload SQL artifact with bootstrap data
- `.github/workflows`: CI + nightly ETL pipelines

## Quickstart (Local)

1. Copy env template:
   - `.env.example` -> `.env`
2. Install dependencies:
   - `apps/api`: `npm install`
   - `apps/web`: `npm install`
   - `data/etl`: `poetry install`
3. Generate ETL artifact:
   - `poetry run nightly --out ../../data/etl_out`
4. Apply schema + load data (local D1):
   - `npx wrangler d1 execute hoopslab-db --file ../../data/schema/schema.sql`
   - `npx wrangler d1 execute hoopslab-db --file ../../data/etl_out/d1_upload.sql`
5. Run API:
   - `npm run dev` in `apps/api`
6. Run Web:
   - `npm run dev` in `apps/web`

## Deployment Notes

- Pages build command: `npm install && npm run build`
- Pages env var to set after Worker deploy:
  - `NEXT_PUBLIC_API_BASE=https://<worker-subdomain>.workers.dev`
