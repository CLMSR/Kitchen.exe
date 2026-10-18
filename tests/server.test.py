import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class SearchParserTests(unittest.TestCase):
    def test_parses_duckduckgo_title_and_snippet(self):
        html = '''
        <div class="result results_links">
          <div class="result__title"><a class="result__a" href="https://example.com/healthy-tiramisu">Healthy Tiramisu</a></div>
          <a class="result__snippet">A lighter dessert with Greek yogurt.</a>
        </div>
        '''
        parser = server.KitchenHandler._SearchParser()
        parser.feed(html)
        self.assertEqual(len(parser.results), 1)
        self.assertEqual(parser.results[0]["title"], "Healthy Tiramisu")
        self.assertEqual(parser.results[0]["url"], "https://example.com/healthy-tiramisu")
        self.assertEqual(parser.results[0]["excerpt"], "A lighter dessert with Greek yogurt.")

    def test_parses_google_style_result(self):
        html = '''<div class="MjjYud"><a href="https://example.org/recipe"><h3>Receta saludable</h3></a><div class="VwiC3b">Postre de yogur y café</div></div>'''
        parser = server.KitchenHandler._SearchParser()
        parser.feed(html)
        self.assertEqual(len(parser.results), 1)
        self.assertEqual(parser.results[0]["title"], "Receta saludable")
        self.assertEqual(parser.results[0]["excerpt"], "Postre de yogur y café")


    def test_parses_duckduckgo_lite_result_link(self):
        html = '''<table><tr><td><a class="result-link" href="https://example.net/tiramisu">Tiramisú saludable</a></td></tr></table>'''
        parser = server.KitchenHandler._SearchParser()
        parser.feed(html)
        self.assertEqual(len(parser.results), 1)
        self.assertEqual(parser.results[0]["title"], "Tiramisú saludable")
        self.assertEqual(parser.results[0]["url"], "https://example.net/tiramisu")

    def test_rejects_localhost_recipe_urls(self):
        handler = object.__new__(server.KitchenHandler)
        self.assertIsNone(handler._safe_public_url("http://127.0.0.1:8765/index.html"))
        self.assertIsNone(handler._safe_public_url("file:///Users/me/index.html"))


if __name__ == "__main__":
    unittest.main()
