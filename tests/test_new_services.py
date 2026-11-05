import asyncio, base64, json, os, stat, tempfile, unittest
from pathlib import Path
import httpx

from neurodynamic_mcp.client_core import Buyer, _image_dimensions, _pdf_page_count

PAYMENT = base64.b64encode(json.dumps({'success': True, 'network': 'eip155:8453', 'transaction': '0xabc'}).encode()).decode()

class NewServiceTests(unittest.TestCase):
    def test_raw_limits_and_signatures(self):
        self.assertEqual(_pdf_page_count(b'%PDF-1.7\n/Type /Page\n'), 1)
        with self.assertRaises(ValueError): _pdf_page_count(b'not a pdf')
        png = b'\x89PNG\r\n\x1a\n' + b'\x00'*8 + (4000).to_bytes(4,'big') + (3000).to_bytes(4,'big')
        self.assertEqual(_image_dimensions(png, 'image/png'), (4000, 3000))

    def test_multipart_and_raw_payment_are_pinned_and_replayed(self):
        async def run():
            with tempfile.TemporaryDirectory() as td:
                calls=[]
                def handler(request):
                    calls.append(request)
                    if 'PAYMENT-SIGNATURE' not in request.headers:
                        body={'x402Version':2,'resource':{'url':'https://api.neurodynamic.tech'+request.url.path},'accepts':[{'scheme':'exact','network':'eip155:8453','asset':'0x833589fcd6edb6e08f4c7c32d4f71b54bda02913','payTo':'0xc9ec9b779e5e94a8c580bb7f9f79c3d7dc113cd0','amount':'10000','maxTimeoutSeconds':300,'extra':{'name':'USD Coin','version':'2'}}]}
                        return httpx.Response(402, json=body)
                    return httpx.Response(200, content=b'{"text":"ok"}', headers={'content-type':'application/json','payment-response':PAYMENT})
                buyer=Buyer(Path(td)/'state', Path(td)/'key', 10000, httpx.MockTransport(handler))
                buyer.sign=lambda q: asyncio.sleep(0, result='proof')
                audio=b'RIFF' + b'audio'
                result=await buyer.purchase('transcript-package', {'language':'en'}, 'pkg1', True, raw_upload=audio)
                self.assertEqual(result['state'],'complete')
                self.assertIn(b'filename=', calls[1].content)
                self.assertIn(b'RIFF', calls[1].content)
                again=await buyer.purchase('transcript-package', {'language':'en'}, 'pkg1', True, raw_upload=audio)
                self.assertTrue(again['reused']); self.assertEqual(len(calls),2)
        asyncio.run(run())

    def test_pdf_page_limit_fails_before_payment(self):
        async def run():
            with tempfile.TemporaryDirectory() as td:
                buyer=Buyer(Path(td)/'state', Path(td)/'key', 10000, httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('network'))))
                buyer.sign=lambda q: asyncio.sleep(0, result='proof')
                with self.assertRaises(ValueError):
                    await buyer.purchase('document-extract', {}, 'pdf1', True, raw_upload=b'%PDF-1.7\n'+b'/Type /Page\n'*21)
        asyncio.run(run())

    def test_quote_binding_covers_all_new_services(self):
        async def run():
            with tempfile.TemporaryDirectory() as td:
                seen = []
                def handler(request):
                    seen.append(request.url.path)
                    endpoint = request.url.path
                    body = {'x402Version': 2, 'resource': {'url': 'https://api.neurodynamic.tech' + endpoint},
                            'accepts': [{'scheme': 'exact', 'network': 'eip155:8453',
                                         'asset': '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
                                         'payTo': '0xc9ec9b779e5e94a8c580bb7f9f79c3d7dc113cd0',
                                         'amount': '10000', 'maxTimeoutSeconds': 300,
                                         'extra': {'name': 'USD Coin', 'version': '2'}}]}
                    return httpx.Response(402, json=body)
                buyer = Buyer(Path(td) / 'state', Path(td) / 'key', 30000, httpx.MockTransport(handler))
                for service in ('transcript-package', 'document-extract', 'document-ocr'):
                    await buyer.quote(service)
                self.assertEqual(seen, ['/v1/audio/transcript-packages', '/v1/documents/extract', '/v1/documents/ocr'])
        asyncio.run(run())

    def test_pdf_and_ocr_success_contracts_and_negative_results(self):
        async def run():
            for service, upload, mime, result in (
                ('document-extract', b'%PDF-1.7\n', 'application/pdf', {'markdown': '# extracted', 'pages': [{'page': 1}]}),
                ('document-ocr', b'\x89PNG\r\n\x1a\n' + b'\x00' * 8 + (10).to_bytes(4, 'big') + (10).to_bytes(4, 'big'), 'image/png', {'markdown': 'printed text', 'pages': [{'page': 1}]}),
            ):
                with tempfile.TemporaryDirectory() as td:
                    def handler(request):
                        if 'PAYMENT-SIGNATURE' not in request.headers:
                            endpoint = request.url.path
                            return httpx.Response(402, json={'x402Version': 2, 'resource': {'url': 'https://api.neurodynamic.tech' + endpoint}, 'accepts': [{'scheme': 'exact', 'network': 'eip155:8453', 'asset': '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', 'payTo': '0xc9ec9b779e5e94a8c580bb7f9f79c3d7dc113cd0', 'amount': '10000', 'maxTimeoutSeconds': 300, 'extra': {'name': 'USD Coin', 'version': '2'}}]})
                        return httpx.Response(200, json=result, headers={'payment-response': PAYMENT})
                    buyer = Buyer(Path(td) / 'state', Path(td) / 'key', 10000, httpx.MockTransport(handler))
                    buyer.sign = lambda q: asyncio.sleep(0, result='proof')
                    got = await buyer.purchase(service, {}, service + '-ok', True, raw_upload=upload, upload_mime=mime)
                    self.assertEqual(got['state'], 'complete')
                    self.assertEqual(json.loads(Path(got['output_file']).read_text()), result)

                    bad = {'text': 'legacy OCR shape'} if service == 'document-ocr' else {'markdown': '# missing pages'}
                    def bad_handler(request):
                        if 'PAYMENT-SIGNATURE' not in request.headers:
                            endpoint = request.url.path
                            return httpx.Response(402, json={'x402Version': 2, 'resource': {'url': 'https://api.neurodynamic.tech' + endpoint}, 'accepts': [{'scheme': 'exact', 'network': 'eip155:8453', 'asset': '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', 'payTo': '0xc9ec9b779e5e94a8c580bb7f9f79c3d7dc113cd0', 'amount': '10000', 'maxTimeoutSeconds': 300, 'extra': {'name': 'USD Coin', 'version': '2'}}]})
                        return httpx.Response(200, json=bad, headers={'payment-response': PAYMENT})
                    failing = Buyer(Path(td) / 'bad-state', Path(td) / 'key', 10000, httpx.MockTransport(bad_handler))
                    failing.sign = lambda q: asyncio.sleep(0, result='proof')
                    with self.assertRaises(ValueError):
                        await failing.purchase(service, {}, service + '-bad', True, raw_upload=upload, upload_mime=mime)
        asyncio.run(run())

if __name__ == '__main__': unittest.main()
