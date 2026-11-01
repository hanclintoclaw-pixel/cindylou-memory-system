import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from unification.canary_api import MAX_BODY, main, make_server, read_token


class CanaryApiTests(unittest.TestCase):
    def setUp(self):
        self.token = 'test-route-token-'+'x'*32
        self.executor = Mock(return_value={'version':1,'status':'ok','results':[],'coverage':'partial'})
        self.server = make_server('/fixed/registry','/fixed/partition',self.token,0,executor=self.executor)
        self.thread = threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.01})
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def request(self,path='/v1/search',body=None,*,auth=True,headers=None,method='POST',raw=None):
        options = {'Content-Type':'application/json'}
        if auth:
            options['Authorization']='Bearer '+self.token
        options.update(headers or {})
        connection = http.client.HTTPConnection(*self.server.server_address,timeout=3)
        try:
            payload = raw if raw is not None else json.dumps(body if body is not None else {'query':'Tom Erlichman'})
            connection.request(method,path,body=payload,headers=options)
            response = connection.getresponse()
            result = response.status,json.loads(response.read()),dict(response.getheaders())
            return result
        finally:
            connection.close()

    def test_unauthenticated_and_browser_requests_never_touch_executor(self):
        for headers,auth,expected in [({},False,401),({'Authorization':'Bearer wrong'},True,401),
                ({'Origin':'http://localhost'},True,403),({'Sec-Fetch-Site':'same-origin'},True,403)]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request(auth=auth,headers=headers)[0],expected)
        self.executor.assert_not_called()

    def test_public_fixed_mapping_and_no_cache(self):
        code,payload,headers = self.request(body={'query':'Curtis','limit':3})
        self.assertEqual(code,200)
        args = self.executor.call_args.args[0]
        self.assertEqual(args.registry,Path('/fixed/registry'))
        self.assertEqual(args.partition,Path('/fixed/partition'))
        self.assertTrue(args.enable_canary)
        self.assertEqual((args.q,args.limit,args.command),('Curtis',3,'search'))
        self.assertEqual(payload['caller']['audience'],'public')
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_authority_injection_and_invalid_types_are_rejected(self):
        for body in [{'query':'Tom','audience':'operator'},{'query':'Tom','registry':'/private'},
                     {'query':'Tom','limit':True},{'query':['Tom']},[],{'query':'Tom','domain':'captured'}]:
            with self.subTest(body=body):
                self.assertEqual(self.request(body=body)[0],400)
        self.executor.assert_not_called()

    def test_get_revision_and_bounds_are_required(self):
        code,_,_ = self.request('/v1/get',{'doc_id':'wiki/PCs/Curtis.md#balance','revision':'a'*64,'start_line':2,'lines':1})
        self.assertEqual(code,200)
        args = self.executor.call_args.args[0]
        self.assertEqual((args.command,args.start_line,args.lines),('get',2,1))
        for body in [{'doc_id':'x'},{'doc_id':'x','revision':'a'*64,'lines':True}]:
            self.assertEqual(self.request('/v1/get',body)[0],400)

    def test_private_write_admin_and_unknown_routes_absent(self):
        for route in ['/facts','/restart','/rebuild','/v1/capture','/v1/search?audience=operator']:
            self.assertEqual(self.request(route)[0],404)
        self.executor.assert_not_called()

    def test_statuses_and_unexpected_errors_do_not_leak(self):
        for status,code in [('denied',403),('stale',409),('unavailable',503),('empty',200)]:
            self.executor.return_value={'status':status,'results':[]}
            self.assertEqual(self.request()[0],code)
        self.executor.side_effect = RuntimeError('PRIVATE SOURCE SECRET')
        code,payload,_ = self.request()
        self.assertEqual((code,payload),(503,{'status':'unavailable'}))

    def test_body_budget_and_malformed_json_precede_backend(self):
        self.assertEqual(self.request(raw='x'*(MAX_BODY+1))[0],413)
        self.assertEqual(self.request(raw='{bad')[0],400)
        self.assertEqual(self.request(headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request(headers={'Transfer-Encoding':'chunked'})[0],400)
        self.executor.assert_not_called()

    def test_health_is_authenticated_too(self):
        self.assertEqual(self.request('/v1/health',method='GET',auth=False)[0],401)
        self.assertEqual(self.request('/v1/health',method='GET')[0],200)
        self.assertEqual(self.executor.call_args.args[0].command,'health')


class CanaryApiStartupTests(unittest.TestCase):
    def test_default_off_before_token_source_or_bind(self):
        with patch('unification.canary_api.read_token') as token, patch('unification.canary_api.make_server') as server:
            with self.assertRaises(SystemExit) as error:
                main(['--registry','/missing','--partition','/missing','--token-file','/missing','--port','18091'])
            self.assertEqual(error.exception.code,2)
            token.assert_not_called()
            server.assert_not_called()

    def test_token_file_permissions_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'token'
            path.write_text('a'*43+'\n')
            path.chmod(0o600)
            self.assertEqual(read_token(path),'a'*43)
            path.chmod(0o700)
            self.assertEqual(read_token(path),'a'*43)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_token(path)
            path.chmod(0o600)
            alias=path.with_name('alias')
            alias.symlink_to(path)
            with self.assertRaises(OSError):
                read_token(alias)


if __name__ == '__main__':
    unittest.main()
