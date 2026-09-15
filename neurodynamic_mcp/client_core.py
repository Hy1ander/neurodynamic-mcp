"""Local buyer adapter. No listening socket; fixed merchant, bounded explicit purchases."""
import asyncio
import base64
import fcntl
import hashlib
import inspect
import json
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

import httpx

ORIGIN = 'https://api.neurodynamic.tech'
NETWORK = 'eip155:8453'
ASSET = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
PAYEE = '0xa369ac3412360206db63507b190e691c0c5b9f3e'
SERVICES = {
    'narration': ('/v1/audio/speech', 5000, 'audio/mpeg', '.mp3'),
    'transcription': ('/v1/audio/transcriptions', 10000, 'application/json', '.json'),
    'abliterated': ('/v1/llm/abliterated/completions', 20000, 'application/json', '.json'),
    'abliterated-large': ('/v1/llm/abliterated-large/completions', 35000, 'application/json', '.json'),
}
DOCS = {'services': '/.well-known/ai-services.json', 'voices': '/v1/audio/voices',
        'schema': '/openapi.json', 'cloning': '/v1/audio/cloning/capabilities'}
VOICES = ['af_heart', 'af_bella', 'bf_emma', 'bf_alice', 'bm_george', 'am_michael', 'am_fenrir']


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def private_read(path, maximum=4096):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
            raise ValueError('Private file must be regular, owned by this user and mode 0600')
        content = f.read(maximum + 1)
        if len(content) > maximum:
            raise ValueError('Private file exceeds size limit')
        return content


def validate_body(service, body):
    if not isinstance(body, dict):
        raise ValueError('Request must be a JSON object')
    text = body.get('input')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Nonempty input text required')
    if service == 'narration':
        if set(body) - {'input', 'voice'} or len(text) > 1000 or body.get('voice', 'af_heart') not in VOICES:
            raise ValueError('Narration accepts input up to 1000 characters and a catalogue voice ID')
    elif service in ('abliterated', 'abliterated-large'):
        if (set(body) - {'input', 'max_tokens', 'adult', 'third_party_processing', 'terms_version'}
            or len(text.encode()) > 2000 or type(body.get('max_tokens', 512)) is not int
            or not 16 <= body.get('max_tokens', 512) <= 512
            or body.get('adult') is not True or body.get('third_party_processing') is not True
            or body.get('terms_version') != '2026-09-11-llm-v1'):
            raise ValueError('LLM requires 2000-byte input limit, 16–512 tokens and explicit current terms/adult/third-party acceptance')
    else:
        raise ValueError('Use transcribe_file for audio; private cloning uses the documented approved-account workflow')


class Buyer:
    def __init__(self, state=None, key_file=None, cap=0, transport=None):
        self.state = Path(state) if state else None
        self.key_file = Path(key_file) if key_file else None
        self.cap = int(cap)
        if not 0 <= self.cap <= 1000000:
            raise ValueError('Session configuration cap must be 0–1000000 atomic USDC (maximum $1)')
        self.transport = transport

    def client(self):
        return httpx.AsyncClient(timeout=httpx.Timeout(100, connect=10), follow_redirects=False,
                                 trust_env=False, transport=self.transport,
                                 headers={'User-Agent': 'NeuroDynamic-MCP/1.0', 'X-Client-Name': 'NeuroDynamic MCP', 'X-Discovery-Source': 'direct'})

    async def request(self, method, path, limit=2*1024*1024, **kwargs):
        async with self.client() as c:
            async with c.stream(method, ORIGIN + path, **kwargs) as r:
                data = bytearray()
                async for chunk in r.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError('Response size limit exceeded; preserve any existing purchase record')
                return r.status_code, dict(r.headers), bytes(data)

    async def catalogue(self, kind):
        if kind not in DOCS:
            raise ValueError('Choose services, voices, schema or cloning')
        status, _, data = await self.request('GET', DOCS[kind])
        if status != 200:
            raise ValueError('Catalogue unavailable; HTTP ' + str(status))
        return json.loads(data)

    async def quote(self, service):
        if service not in SERVICES:
            raise ValueError('Unknown service; cloning quotes require an authenticated ready job')
        path, amount, _, _ = SERVICES[service]
        status, _, data = await self.request('POST', path, limit=131072)
        if status != 402:
            raise ValueError('No payable quote; HTTP ' + str(status))
        q = json.loads(data)
        accepted = q.get('accepts', [])
        matches = [r for r in accepted if r.get('network') == NETWORK]
        if q.get('x402Version') != 2 or q.get('resource', {}).get('url') != ORIGIN + path or len(matches) != 1:
            raise ValueError('Unexpected payment contract')
        req = matches[0]
        if (req.get('scheme') != 'exact' or req.get('amount') != str(amount)
            or req.get('asset', '').lower() != ASSET or req.get('payTo', '').lower() != PAYEE
            or not 1 <= req.get('maxTimeoutSeconds', 0) <= 300
            or req.get('extra', {}).get('name') != 'USD Coin'
            or req.get('extra', {}).get('version') != '2'):
            raise ValueError('Unapproved price, token, receiver or signature domain; no signature created')
        # The initial release signs only the reviewed Base option, even if the merchant adds chains.
        return {**q, 'accepts': [req]}

    @contextmanager
    def ledger(self):
        if not self.state or not self.state.is_absolute():
            raise ValueError('Configure an absolute NEURODYNAMIC_STATE directory for purchases')
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = self.state.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
            raise ValueError('State directory must be owner-only, real directory, not a symlink')
        lockfd = os.open(self.state / 'purchase.lock', os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            dbpath = self.state / 'purchases.sqlite3'
            if dbpath.is_symlink():
                raise ValueError('Ledger may not be a symlink')
            fd = os.open(dbpath, os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
            os.close(fd)
            db = sqlite3.connect(dbpath)
            db.row_factory = sqlite3.Row
            try:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('CREATE TABLE IF NOT EXISTS purchases (id TEXT PRIMARY KEY, service TEXT NOT NULL, digest TEXT NOT NULL, amount INTEGER NOT NULL, state TEXT NOT NULL, proof TEXT, receipt TEXT, output TEXT)')
                db.commit()
                yield db
            finally:
                db.close()
        finally:
            os.close(lockfd)

    async def sign(self, quote):
        if not self.key_file:
            raise ValueError('No buyer key configured; discovery remains available without one')
        from eth_account import Account
        from x402.client import x402Client
        from x402.mechanisms.evm.exact.client import ExactEvmScheme
        from x402.mechanisms.evm.signers import EthAccountSigner
        from x402.schemas import PaymentRequired
        key = private_read(self.key_file).decode().strip()
        buyer = x402Client().register(NETWORK, ExactEvmScheme(EthAccountSigner(Account.from_key(key))))
        payload = buyer.create_payment_payload(PaymentRequired.model_validate(quote))
        if inspect.isawaitable(payload):
            payload = await payload
        return base64.b64encode(canonical(payload.model_dump(mode='json', by_alias=True, exclude_none=True)).encode()).decode()

    async def purchase(self, service, body, purchase_id, confirm_purchase, raw_audio=None):
        if confirm_purchase is not True:
            raise ValueError('Explicit confirm_purchase=true is required')
        if not self.cap or not self.key_file:
            raise ValueError('Purchases disabled; owner must configure a buyer key and cumulative cap')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', purchase_id):
            raise ValueError('Purchase ID must contain 1–64 letters, digits, hyphens or underscores')
        if service not in SERVICES:
            raise ValueError('Unsupported purchase service')
        if service == 'transcription':
            if not raw_audio or len(raw_audio) > 12*1024*1024 or not re.fullmatch('[a-z]{2}', body.get('language', '')):
                raise ValueError('Audio up to 12 MiB and a two-letter language are required')
            identity = {'language': body['language'], 'audio_sha256': hashlib.sha256(raw_audio).hexdigest()}
        else:
            validate_body(service, body)
            identity = body
        path, amount, mime, suffix = SERVICES[service]
        digest = hashlib.sha256(canonical({'service': service, 'request': identity}).encode()).hexdigest()
        with self.ledger() as db:
            old = db.execute('SELECT * FROM purchases WHERE id=?', (purchase_id,)).fetchone()
            if old:
                if old['digest'] != digest:
                    raise ValueError('Purchase ID belongs to a different request; no replacement signature created')
                return {'purchase_id': purchase_id, 'state': old['state'], 'output_file': old['output'],
                        'reused': True, 'next_action': 'Read saved output or use payment_status. No request or new payment was sent.'}
            spent = db.execute('SELECT COALESCE(SUM(amount),0) FROM purchases').fetchone()[0]
            if spent + amount > self.cap:
                raise ValueError('Cumulative budget exhausted, including uncertain/reserved purchases')
            quote = await self.quote(service)
            # Reserve durably before signing; a crash never resets the budget or signs this ID again.
            db.execute('INSERT INTO purchases(id,service,digest,amount,state) VALUES(?,?,?,?,?)',
                       (purchase_id, service, digest, amount, 'reserved'))
            db.commit()
            try:
                proof = await self.sign(quote)
                db.execute('UPDATE purchases SET proof=?,state=? WHERE id=?', (proof, 'submitted', purchase_id))
                db.commit()
                args = {'headers': {'PAYMENT-SIGNATURE': proof}}
                if service == 'transcription':
                    args.update(data={'model': 'whisper-1', 'response_format': 'json', 'language': body['language']},
                                files={'file': ('audio', raw_audio, 'application/octet-stream')})
                else:
                    args['json'] = body
                status, headers, data = await self.request('POST', path, limit=8*1024*1024 if service == 'narration' else 131072, **args)
                if status != 200 or headers.get('content-type', '').split(';')[0] != mime:
                    raise ValueError('Purchase HTTP ' + str(status) + '; check payment_status, do not pay again')
                receipt_header = headers.get('payment-response', '')
                if len(receipt_header) > 16384:
                    raise ValueError('Oversized receipt')
                receipt = json.loads(base64.b64decode(receipt_header, validate=True))
                if receipt.get('success') is not True or receipt.get('network') != NETWORK or not receipt.get('transaction'):
                    raise ValueError('Unconfirmed settlement receipt')
                if service != 'narration':
                    result = json.loads(data)
                    if not isinstance(result.get('text'), str):
                        raise ValueError('Unexpected result')
                    if service != 'transcription' and (result.get('model') != service or result.get('ai_generated') is not True):
                        raise ValueError('Unexpected LLM result')
                output = self.state / (purchase_id + suffix)
                fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as f:
                    f.write(data); f.flush(); os.fsync(f.fileno())
                db.execute('UPDATE purchases SET state=?,receipt=?,output=? WHERE id=?',
                           ('complete', canonical(receipt), str(output), purchase_id))
                db.commit()
                return {'purchase_id': purchase_id, 'state': 'complete', 'output_file': str(output),
                        'receipt': receipt, 'amount_usdc': amount/1000000, 'sha256': hashlib.sha256(data).hexdigest()}
            except Exception:
                db.execute('UPDATE purchases SET state=? WHERE id=?', ('uncertain', purchase_id))
                db.commit()
                raise ValueError('Purchase incomplete or uncertain. Keep this purchase ID and state directory; use payment_status. No automatic replacement payment.') from None

    async def status(self, purchase_id):
        with self.ledger() as db:
            row = db.execute('SELECT * FROM purchases WHERE id=?', (purchase_id,)).fetchone()
            if not row:
                raise ValueError('Unknown purchase ID')
            result = {k: row[k] for k in ('id', 'service', 'amount', 'state', 'output')}
            if row['receipt']:
                result['receipt'] = json.loads(row['receipt'])
            if row['service'].startswith('abliterated') and row['proof']:
                code, _, data = await self.request('POST', '/v1/llm/' + row['service'] + '/status',
                                                   limit=65536, headers={'PAYMENT-SIGNATURE': row['proof']})
                result['remote_http_status'] = code
                if code == 200:
                    result['remote_status'] = json.loads(data)
            result['next_action'] = 'Read saved output if complete. For uncertainty contact support with the transaction or request ID; do not create a replacement purchase. LLM output is not retained by the merchant.'
            return result

    def budget(self):
        if not self.state:
            return {'purchases_enabled': False, 'cap_atomic_usdc': self.cap, 'reserved_atomic_usdc': 0}
        with self.ledger() as db:
            spent = db.execute('SELECT COALESCE(SUM(amount),0) FROM purchases').fetchone()[0]
        return {'purchases_enabled': bool(self.key_file and self.cap), 'cap_atomic_usdc': self.cap,
                'reserved_atomic_usdc': spent, 'remaining_atomic_usdc': max(0, self.cap-spent),
                'note': 'Cumulative across restarts. Uncertain and reserved purchases count. No automatic reset.'}
