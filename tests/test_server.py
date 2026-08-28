import json
import threading
import unittest
from http.client import HTTPConnection
from lxml import etree

import server


class ServerUnitTests(unittest.TestCase):
    def test_cnc_defaults_to_v100(self):
        root = etree.fromstring(b'<CNC xmlns="http://www.sped.fazenda.gov.br/nfse"/>')
        detected = server.detectar(root)
        self.assertEqual(detected["tipo"], "CNC")
        self.assertEqual(detected["ver"], "1.00")

    def test_consolidated_tables_are_used_as_fallback(self):
        self.assertGreater(len(server.TAB_SERV), 0)
        self.assertGreater(len(server.TAB_INDOP), 0)
        self.assertGreater(len(server.TAB_REJ), 0)

    def test_version_is_canonical(self):
        self.assertEqual(server._app_version(), "3.19.0")

    def test_xsd_state_counts_files_on_disk(self):
        state = server._xsd_state_real()
        self.assertGreater(len(state["schemas_instalados"]["v100"]), 0)
        self.assertGreater(len(state["schemas_instalados"]["v101"]), 0)
        self.assertTrue(state.get("data_xsd"))

    def test_safe_parser_does_not_expand_external_entity(self):
        body = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01"><x>&xxe;</x></DPS>'
        root = server._safe_parse(body)
        self.assertNotIn("root:", etree.tostring(root, encoding="unicode"))


class ServerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, method, path, body=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/xml"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, json.loads(data.decode("utf-8"))

    def test_health_reports_version_and_services(self):
        status, payload = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["versao"], "3.19.0")
        self.assertGreater(payload["tabelas"]["servicos"], 0)

    def test_cases_endpoint_returns_collection(self):
        status, payload = self.request("GET", "/api/casos")
        self.assertEqual(status, 200)
        self.assertIn("casos", payload)
        self.assertIsInstance(payload["casos"], list)

    def test_invalid_numeric_xml_returns_document_error(self):
        xml = b'<?xml version="1.0"?><DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01"><infDPS><tpAmb>2</tpAmb><vBCPisCofins>abc</vBCPisCofins></infDPS></DPS>'
        status, payload = self.request("POST", "/api/validar", xml)
        self.assertEqual(status, 422)
        self.assertFalse(payload["valido"])
        self.assertIn("erro", payload)


if __name__ == "__main__":
    unittest.main()
