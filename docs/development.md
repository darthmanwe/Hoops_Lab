# Development

## API (Worker)

```powershell
cd apps/api
npm install
npm run dev
```

Smoke test:

```powershell
curl http://127.0.0.1:8787/health
```

## Web (Next.js)

```powershell
cd apps/web
npm install
npm run dev
```

Optional local env file:
- Copy `apps/web/.env.local.example` to `.env.local`.

## ETL (Poetry)

```powershell
cd data/etl
poetry install
poetry run nightly --out ../../data/etl_out
```

## Typical local order

1. Run API (`npm run dev`)
2. Run ETL artifact (`poetry run nightly`)
3. Execute SQL artifact to D1 for data bootstrap
4. Run Web (`npm run dev`)
