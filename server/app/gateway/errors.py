import math


class GatewayError(Exception):
    """Public error codes only; never expose provider bodies or credentials."""

    def __init__(self, code: str, status: int = 503, retry_after: float = 0):
        super().__init__(code)
        self.code = code
        self.status = status
        self.retry_after = max(0, math.ceil(retry_after))

    def payload(self):
        return {'code': self.code, 'retry_after': self.retry_after,
                'message': 'AI 요청을 처리할 수 없습니다. 잠시 후 다시 시도해 주세요.'}
