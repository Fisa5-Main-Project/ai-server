"""Compatible with Spring JwtUtil HS512 access tokens, never a body/header user ID."""
import base64
import binascii
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from redis.exceptions import RedisError

from .errors import GatewayError


@dataclass(frozen=True)
class Principal:
    user_id: int
    roles: frozenset[str]


def signing_key(secret):
    try:
        key = base64.b64decode(secret, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('AI_JWT_SECRET_BASE64 must be valid base64') from exc
    if len(key) < 64:
        raise ValueError('HS512 access key must be at least 64 bytes')
    return key


def verify_token(authorization, secret):
    if not authorization or not authorization.startswith('Bearer '):
        raise GatewayError('authentication_required', 401)
    try:
        claims = jwt.decode(authorization[7:], signing_key(secret), algorithms=['HS512'],
                            options={'require':['exp','sub','authorities']})
        subject, roles = claims['sub'], claims['authorities']
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdigit() or int(subject) <= 0:
            raise ValueError('invalid subject')
        if not isinstance(roles, str):
            raise ValueError('invalid authorities')
        return Principal(int(subject), frozenset(r.strip() for r in roles.split(',') if r.strip()))
    except (jwt.PyJWTError, ValueError) as exc:
        raise GatewayError('invalid_access_token', 401) from exc


async def authenticated_user(request: Request):
    config = request.app.state.gateway_config
    authorization = request.headers.get('Authorization')
    principal = verify_token(authorization, config.jwt_secret_base64)
    try:
        # Same Redis DB and raw string key serializer as Spring JwtAuthFilter.
        revoked = await request.app.state.auth_redis.exists(authorization[7:])
    except RedisError as exc:
        raise GatewayError('authentication_unavailable') from exc
    if revoked:
        raise GatewayError('access_token_revoked', 401)
    return principal


def authorize_owner(principal, user_id):
    if principal.user_id != user_id:
        raise GatewayError('user_mismatch', 403)


async def administrator(principal: Principal = Depends(authenticated_user)):
    if 'ROLE_ADMIN' not in principal.roles:
        raise GatewayError('admin_required', 403)
    return principal
