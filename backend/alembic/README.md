# Alembic Database Migration

This directory contains database migration scripts.

## Install Dependencies

Make sure Alembic is installed:

```bash
pip install alembic
# or
uv add alembic
```

## Usage

### Create New Migration

```bash
# Auto-generate migration (recommended)
alembic revision --autogenerate -m "describe your changes"

# Manually create empty migration
alembic revision -m "describe your changes"
```

### Apply Migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade one version
alembic upgrade +1

# Upgrade to specific version
alembic upgrade <revision_id>
```

### Rollback Migrations

```bash
# Rollback one version
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>

# Rollback all
alembic downgrade base
```

### View Migration History

```bash
# View current version
alembic current

# View migration history
alembic history

# View detailed history
alembic history --verbose
```

## Configuration

Database connection URL is read from the `DATABASE_URL` environment variable.

Please set it in your `.env` file:

```
DATABASE_URL=postgresql://user:password@localhost/dbname
```

## Notes

1. Before creating migrations, ensure all models are imported in `alembic/env.py`
2. When using `--autogenerate`, Alembic will automatically detect model changes
3. Always review generated migration scripts to ensure they meet expectations
4. Test migrations in development environment before applying to production

