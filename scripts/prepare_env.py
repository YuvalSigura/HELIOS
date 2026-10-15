"""Generate local-only credentials; never commit .env."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
path = root / '.env'
if path.exists():
    raise SystemExit('.env already exists; not overwriting')
lines = [
    'HELIOS_DB_PASSWORD=' + secrets.token_urlsafe(24),
    'HELIOS_S3_ACCESS=helioslab',
    'HELIOS_S3_SECRET=' + secrets.token_urlsafe(24),
    'HELIOS_SESSION_SECRET=' + secrets.token_urlsafe(48),
    'HELIOS_ANALYST_PASSWORD=' + secrets.token_urlsafe(12),
]
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
try:
    path.chmod(0o600)
except OSError:
    pass
print('Wrote .env. Give only the analyst password to HOMELAB.')
