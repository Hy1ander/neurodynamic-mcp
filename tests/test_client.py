import asyncio
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from neurodynamic_mcp.client_core import Buyer, SERVICES, ORIGIN, NETWORK, ASSET, PAYEE, private_read, validate_body


def quote(service='narration'):
    path, amount, _, _ = SERVICES[service]
    return {'x402Version': 2, 'resource': {'url': ORIGIN+path}, 'accepts': [
        {'scheme': 'exact', 'network': NETWORK, 'asset': ASSET, 'amount': str(amount),
         'payTo': PAYEE, 'maxTimeoutSeconds': 300, 'extra': {'name': 'USD Coin', 'version': '2'}}]}

class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root/'state'
        self.key = self.root/'key'
        self.key.write_text('dummy'); self.key.chmod(0o600)
        self.signed = 0; self.paid = 0
        self.fail = False
        self.q = quote()
        self.buyer = Buyer(self.state, self.key, 10000, httpx.MockTransport(self.handler))
        async def sign(q):
            self.signed += 1
            return 'signed-proof'
        self.buyer.sign = sign
    def tearDown(self):
        self.tmp.cleanup()
    def handler(self, request):
        if 'payment-signature' not in request.headers:
            return httpx.Response(402, json=self.q)
        self.paid += 1
        if self.fail:
            raise httpx.ReadTimeout('simulated response lost')
        receipt = base64.b64encode(json.dumps({'success': True, 'network': NETWORK, 'transaction': '0xtest'}).encode()).decode()
        return httpx.Response(200, content=b'ID3synthetic', headers={'Content-Type':'audio/mpeg','PAYMENT-RESPONSE':receipt})
    async def buy(self, ident='one', text='Test', confirm=True):
        return await self.buyer.purchase('narration', {'input':text}, ident, confirm)
    async def test_quote_no_wallet_no_spending(self):
        b = Buyer(transport=httpx.MockTransport(self.handler))
        self.assertEqual((await b.quote('narration'))['accepts'][0]['amount'],'5000')
        self.assertFalse(b.budget()['purchases_enabled'])
        self.assertFalse(self.state.exists())
    async def test_default_requires_configuration_and_explicit_intent(self):
        with self.assertRaises(ValueError): await self.buy(confirm=False)
        self.buyer.cap=0
        with self.assertRaises(ValueError): await self.buy()
        self.assertEqual(self.signed,0)
    async def test_reject_quote_substitution(self):
        for field,value in [('payTo','0x'+'1'*40),('network','eip155:137'),('amount','99999'),('asset','0x'+'2'*40),('scheme','upto')]:
            self.q=quote(); self.q['accepts'][0][field]=value
            with self.assertRaises(ValueError): await self.buy()
        self.q=quote(); self.q['resource']['url']='https://evil.example/'
        with self.assertRaises(ValueError): await self.buy()
        self.assertEqual(self.signed,0)
    async def test_receipt_output_and_duplicate_never_repays(self):
        first=await self.buy(); second=await self.buy()
        self.assertEqual(first['state'],'complete'); self.assertTrue(second['reused'])
        self.assertEqual((self.paid,self.signed),(1,1))
        self.assertEqual(Path(first['output_file']).stat().st_mode&0o777,0o600)
    async def test_changed_input_same_id_rejected(self):
        await self.buy()
        with self.assertRaises(ValueError): await self.buy(text='Changed')
        self.assertEqual(self.signed,1)
    async def test_uncertain_persists_and_never_resigns(self):
        self.fail=True
        with self.assertRaises(ValueError): await self.buy()
        restarted=Buyer(self.state,self.key,5000,httpx.MockTransport(self.handler))
        r=await restarted.purchase('narration',{'input':'Test'},'one',True)
        self.assertEqual(r['state'],'uncertain');self.assertTrue(r['reused'])
        self.assertEqual(restarted.budget()['remaining_atomic_usdc'],0)
        with self.assertRaises(ValueError): await restarted.purchase('narration',{'input':'Other'},'two',True)
        self.assertEqual((self.paid,self.signed),(1,1))
    async def test_cap_applies_cumulatively(self):
        await self.buy('one');await self.buy('two')
        with self.assertRaises(ValueError):await self.buy('three')
        self.assertEqual(self.paid,2)
    async def test_parallel_purchases_fail_closed(self):
        async def delayed(q):
            await asyncio.sleep(0.03); return 'signed'
        self.buyer.sign=delayed
        results=await asyncio.gather(self.buy('one'),self.buy('two'),return_exceptions=True)
        self.assertEqual(sum(isinstance(x,dict) for x in results),1)
        self.assertEqual(self.paid,1)
    async def test_missing_receipt_keeps_reservation(self):
        self.buyer.transport=httpx.MockTransport(lambda r:httpx.Response(402,json=quote()) if 'payment-signature' not in r.headers else httpx.Response(200,content=b'ID3',headers={'content-type':'audio/mpeg'}))
        with self.assertRaises(ValueError):await self.buy()
        self.assertEqual(self.buyer.budget()['reserved_atomic_usdc'],5000)
    async def test_filename_injection(self):
        with self.assertRaises(ValueError): await self.buy('../evil')
        self.assertEqual(self.signed,0)
    async def test_state_symlink_rejected(self):
        real=self.root/'real'; real.mkdir(mode=0o700); self.state.symlink_to(real)
        with self.assertRaises(ValueError):await self.buy()
    async def test_oversized_quote_fails_before_signing(self):
        self.buyer.transport=httpx.MockTransport(lambda r:httpx.Response(402,content=b'a'*131073))
        with self.assertRaises(ValueError):await self.buy()
        self.assertEqual(self.signed,0)
    async def test_no_redirect_follow(self):
        self.buyer.transport=httpx.MockTransport(lambda r:httpx.Response(307,headers={'location':'https://evil.example'}))
        with self.assertRaises(ValueError):await self.buy()
        self.assertEqual(self.signed,0)
    def test_private_file_permissions_and_symlink(self):
        self.key.chmod(0o644)
        with self.assertRaises(ValueError): private_read(self.key)
        link=self.root/'link';link.symlink_to(self.key)
        with self.assertRaises(OSError):private_read(link)
    def test_llm_consent_and_byte_limit(self):
        valid={'input':'Test','adult':True,'third_party_processing':True,'terms_version':'2026-09-11-llm-v1','max_tokens':16}
        validate_body('abliterated',valid)
        for change in [{'adult':False},{'third_party_processing':False},{'input':'é'*1001},{'max_tokens':True},{'terms_version':'old'}]:
            with self.assertRaises(ValueError):validate_body('abliterated',{**valid,**change})
    async def test_real_sdk_signature_locally_no_rpc(self):
        from eth_account import Account
        self.key.write_text(Account.create().key.hex())
        real=Buyer(self.state,self.key,5000)
        proof=json.loads(base64.b64decode(await real.sign(quote())))
        self.assertEqual(proof['accepted']['network'],NETWORK)
        self.assertEqual(proof['payload']['authorization']['to'].lower(),PAYEE)
        self.assertEqual(str(proof['payload']['authorization']['value']),'5000')

if __name__=='__main__':unittest.main()
