# Database setup

Needs `psql` and `SUPABASE_DB_URL` in `.env` (Supabase dashboard → Connect → Session pooler).

Create the tables (safe to re-run):

```
set -a; source .env; set +a
psql "$SUPABASE_DB_URL" -f schema.sql
```

Check them:

```
psql "$SUPABASE_DB_URL" -c '\d channels' -c '\d videos'
```

`schema.sql` skips tables that already exist. To change one, use `alter table`, or drop it and re-run.
