"""OAuth 설정, 초대 승인, 짧은 수명의 Mobius JWT 발급."""
import json
import os
import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException


JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv("MOBIUS_JWT_SECRET", "mobius-development-secret-change-in-production")
JWT_TTL_MINUTES = int(os.getenv("MOBIUS_JWT_TTL_MINUTES", "60"))
OAUTH = {
    "google": {"client_id": os.getenv("GOOGLE_CLIENT_ID", ""), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""), "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/v1/auth/callback/google"), "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth"},
}


def provider_status() -> dict:
    return {name: {"configured": bool(item["client_id"] and item["client_secret"]), "redirect_uri": item["redirect_uri"]} for name, item in OAUTH.items()}


def authorization_url(provider: str) -> str:
    config = OAUTH.get(provider)
    if config is None:
        raise HTTPException(status_code=404, detail="지원하지 않는 로그인 공급자입니다.")
    if not config["client_id"]:
        raise HTTPException(status_code=503, detail=f"{provider} OAuth 설정이 필요합니다.")
    query = {"client_id": config["client_id"], "redirect_uri": config["redirect_uri"], "response_type": "code"}
    if provider == "google": query.update({"scope": "openid email profile", "access_type": "offline", "prompt": "select_account"})
    return f"{config['authorize_url']}?{urlencode(query)}"


def issue_token(subject: str, role: str, tenant_slug: str) -> str:
    now = datetime.now(UTC)
    header = _b64({"alg": JWT_ALGORITHM, "typ": "JWT"})
    payload = _b64({"sub": subject, "role": role, "tenant_id": tenant_slug, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=JWT_TTL_MINUTES)).timestamp())})
    signature = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{signature}"


def decode_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(f"{header}.{payload}")):
            raise ValueError("invalid signature")
        claims = json.loads(_unb64(payload))
        if claims.get("exp", 0) < int(datetime.now(UTC).timestamp()):
            raise ValueError("expired")
        if {"sub", "role", "tenant_id"} - claims.keys():
            raise ValueError("missing claims")
        return claims
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=401, detail="로그인 세션이 유효하지 않습니다.") from error


def _b64(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(value: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), value.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()


def oauth_profile(provider: str, code: str) -> tuple[str, str]:
    """공급자 code를 검증해 고유 subject와 이메일을 얻는다."""
    config = OAUTH[provider]
    if provider != "google":
        raise HTTPException(status_code=404, detail="지원하지 않는 로그인 공급자입니다.")
    token_url, profile_url = "https://oauth2.googleapis.com/token", "https://openidconnect.googleapis.com/v1/userinfo"
    body = urlencode({"grant_type": "authorization_code", "code": code, "client_id": config["client_id"], "client_secret": config["client_secret"], "redirect_uri": config["redirect_uri"]}).encode()
    try:
        with urlopen(Request(token_url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10) as response:
            access_token = json.loads(response.read())["access_token"]
        with urlopen(Request(profile_url, headers={"Authorization": f"Bearer {access_token}"}), timeout=10) as response:
            profile = json.loads(response.read())
    except Exception as error:
        raise HTTPException(status_code=401, detail="OAuth 인증 정보를 확인할 수 없습니다.") from error
    subject, email = profile.get("sub"), profile.get("email")
    if not subject or not email:
        raise HTTPException(status_code=400, detail="로그인 공급자가 이메일 동의를 제공하지 않았습니다.")
    return str(subject), str(email)
