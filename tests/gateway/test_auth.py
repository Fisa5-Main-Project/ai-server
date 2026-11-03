import base64
import time

import jwt
import pytest

from app.gateway.auth import verify_token, authorize_owner, Principal
from app.gateway.errors import GatewayError

KEY = b'x' * 64
SECRET = base64.b64encode(KEY).decode()


def token(**claims):
    return jwt.encode({'sub':'7','exp':time.time()+300,'authorities':'ROLE_USER',**claims},KEY,algorithm='HS512')


def test_verified_subject_and_roles():
    p = verify_token('Bearer '+token(),SECRET)
    assert p.user_id == 7
    authorize_owner(p,7)
    with pytest.raises(GatewayError) as caught:
        authorize_owner(p,8)
    assert caught.value.status == 403


@pytest.mark.parametrize('value',[None,'Bearer invalid','Bearer '+token(exp=0),
    'Bearer '+jwt.encode({'sub':'7','exp':time.time()+30},KEY,algorithm='HS256'),
    'Bearer '+token(sub='not-a-user'),'Bearer '+token(authorities=None)])
def test_reject_invalid_token(value):
    with pytest.raises(GatewayError) as caught:
        verify_token(value,SECRET)
    assert caught.value.status == 401


def test_admin_cannot_charge_another_user_via_owned_endpoint():
    with pytest.raises(GatewayError):
        authorize_owner(Principal(1, frozenset({'ROLE_ADMIN'})),2)
