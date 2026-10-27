import click
from app import create_app
from app.extensions import db
from app.models import *  

from app.utils.seed_safety import validate_seed_database_safety

app = create_app()


@app.cli.command('init-db')
def init_db():
    """Create all database tables."""
    validate_seed_database_safety(app, operation='init-db', is_destructive=False)
    db.create_all()
    click.echo('Database tables created.')


@app.cli.command('drop-db')
def drop_db():
    """Drop all database tables (USE WITH CAUTION)."""
    validate_seed_database_safety(app, operation='drop-db', is_destructive=True)
    db.drop_all()
    click.echo('All database tables dropped.')


@app.cli.command('reset-db')
def reset_db():
    """Drop and recreate all tables, then seed."""
    validate_seed_database_safety(app, operation='reset-db', is_destructive=True)
    db.drop_all()
    db.create_all()
    click.echo('Database reset complete. Run `python seed.py` to seed data.')


@app.cli.command('verify-audit-chain')
def verify_audit_chain():
    """Verify the cryptographic hash-linked audit trail integrity."""
    from app.models import AuditLog
    is_valid = AuditLog.verify_chain_integrity()
    if is_valid:
        click.echo('Audit chain integrity: VALID')
    else:
        click.echo('Audit chain integrity: TAMPERED - CHAIN BROKEN!')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)