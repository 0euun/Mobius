"""
데모 API Key 기반 RBAC와 테넌트 컨텍스트.
P2에서 OAuth/OIDC의 subject·tenant claim으로 동일한 Principal을 생성한다.
"""

from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException
from .auth import decode_token


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    tenant_slug: str


PRINCIPALS = {
    "mobius-victim-demo": Principal("victim-demo-user", "victim", "victim-demo"),
    "mobius-b2b-demo": Principal("b2b-demo-user", "b2b", "b2b-demo"),
    "mobius-admin-demo": Principal("admin-demo-user", "admin", "admin-demo"),
}
ROLES = {key: value.role for key, value in PRINCIPALS.items()}


def require_principal(*allowed: str):
    def dependency(x_api_key: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> Principal:
        principal = None
        if authorization and authorization.lower().startswith("bearer "):
            claims = decode_token(authorization.split(" ", 1)[1])
            principal = Principal(str(claims["sub"]), str(claims["role"]), str(claims["tenant_id"]))
        if principal is None:
            principal = PRINCIPALS.get(x_api_key or "")
        if principal is None:
            raise HTTPException(status_code=401, detail="유효한 API Key가 필요합니다.")
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="이 역할에는 접근 권한이 없습니다.")
        return principal
    return dependency


def require_role(*allowed: str):
    def dependency(principal: Principal = Depends(require_principal(*allowed))) -> str:
        return principal.role
    return dependency
