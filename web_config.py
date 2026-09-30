"""Private configuration independent of Streamlit. Environment wins over TOML."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True)
class WebConfig:
    admin_password: str = field(default='', repr=False)
    sheet_id: str = field(default='', repr=False)
    gcp_json: str | dict = field(default='', repr=False)
    backup_url: str = field(default='', repr=False)
    session_seconds: int = 28800
    attempt_seconds: int = 86400
    secure_cookie: bool = False
    error: str = ''


def load_config(root=None, environ=None):
    root = Path(root) if root is not None else Path(__file__).parent
    env = os.environ if environ is None else environ
    path = root / 'secrets.toml'
    if not path.exists():
        path = root / '.streamlit' / 'secrets.toml'
    values = {}
    try:
        if path.exists():
            with path.open('rb') as source:
                values = tomllib.load(source)
        def get(name, default=''):
            return env.get(name, values.get(name, default))
        return WebConfig(
            admin_password=str(get('ADMIN_PASSWORD')),
            sheet_id=str(get('SHEET_ID')),
            gcp_json=get('GCP_JSON'),
            backup_url=str(get('GS_BACKUP_URL')),
            session_seconds=max(60, int(get('SESSION_SECONDS', 28800))),
            attempt_seconds=max(300, int(get('ATTEMPT_SECONDS', 86400))),
            secure_cookie=str(get('SECURE_COOKIE', 'false')).lower() in ('true', '1', 'yes'),
        )
    except (OSError, ValueError, TypeError):
        return WebConfig(error='연결 설정 파일을 읽지 못했습니다. secrets.toml 형식을 확인해 주세요.')
