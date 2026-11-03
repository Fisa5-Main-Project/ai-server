"""One HTTP request per invoke; SDK retry policies cannot bypass admission."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re

import httpx

from .errors import GatewayError


def retry_after_seconds(value, now=None):
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            seconds = max(0, (target - (now or datetime.now(timezone.utc))).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


class ProviderLimited(GatewayError):
    def __init__(self, retry_after=None):
        super().__init__('provider_rate_limit', 429, retry_after or 0)
        self.delay = retry_after


class InvalidProviderResponse(GatewayError):
    def __init__(self, usage):
        super().__init__('provider_invalid_response', 502)
        self.usage = usage


@dataclass
class ProviderResult:
    content: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None = None


def _count(value):
    return value if type(value) is int and value >= 0 else None


class HTTPProvider:
    def __init__(self, http, provider, model, api_key, max_output_tokens):
        if provider not in ('groq', 'gemini') or not re.fullmatch(r'[A-Za-z0-9_./-]+', model):
            raise ValueError('Unsupported provider/model')
        self.http, self.provider, self.model = http, provider, model
        self.api_key, self.max_output_tokens = api_key, max_output_tokens

    async def invoke(self, messages, temperature):
        if self.provider == 'groq':
            url = 'https://api.groq.com/openai/v1/chat/completions'
            headers = {'Authorization': 'Bearer ' + self.api_key}
            body = {'model':self.model, 'messages':messages, 'temperature':temperature,
                    'max_completion_tokens':self.max_output_tokens, 'stream':False}
        else:
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent'
            headers = {'x-goog-api-key':self.api_key}
            body = {'contents':[{'role':'model' if m['role']=='assistant' else 'user',
                                 'parts':[{'text':m['content']}]} for m in messages if m['role']!='system'],
                    'generationConfig':{'temperature':temperature, 'maxOutputTokens':self.max_output_tokens}}
            system = '\n'.join(m['content'] for m in messages if m['role']=='system')
            if system:
                body['systemInstruction'] = {'parts':[{'text':system}]}
        try:
            response = await self.http.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise GatewayError('provider_timeout', 504) from exc
        except httpx.HTTPError as exc:
            raise GatewayError('provider_unavailable', 502) from exc
        if response.status_code == 429:
            raise ProviderLimited(retry_after_seconds(response.headers.get('Retry-After')))
        if response.status_code >= 400:
            raise GatewayError('provider_error', 502)
        counts = {}
        try:
            data = response.json()
            # Meter independently from content: blocked/empty candidates may still consume tokens.
            if self.provider == 'groq':
                usage = data.get('usage') or {}
                counts = {'input_tokens':_count(usage.get('prompt_tokens')),
                          'output_tokens':_count(usage.get('completion_tokens')),
                          'total_tokens':_count(usage.get('total_tokens')),
                          'cached_input_tokens':_count((usage.get('prompt_tokens_details') or {}).get('cached_tokens'))}
                content = data['choices'][0]['message']['content']
            else:
                usage = data.get('usageMetadata') or {}
                output = _count(usage.get('candidatesTokenCount'))
                thoughts = _count(usage.get('thoughtsTokenCount'))
                if output is not None:
                    output += thoughts or 0
                counts = {'input_tokens':_count(usage.get('promptTokenCount')), 'output_tokens':output,
                          'total_tokens':_count(usage.get('totalTokenCount')),
                          'cached_input_tokens':_count(usage.get('cachedContentTokenCount'))}
                parts = data['candidates'][0]['content']['parts']
                content = ''.join(p.get('text','') for p in parts if not p.get('thought'))
            if not isinstance(content, str):
                raise ValueError('Content must be text')
            return ProviderResult(content, **counts)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise InvalidProviderResponse(counts) from exc
