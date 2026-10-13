"""Tests HyperFrames — sans dépendance réseau (mock IA, faux TTS).

Lancement :  python -m pytest tests/test_server.py -v
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from server import app as app_module
from server import projects as P

client = TestClient(app_module)


def make_scene(i=1, **over):
    s = {"text": f"Scène {i} : du texte parlé", "visual_prompt": "visuel simple",
         "duration": 4.0, "locked": False}
    s.update(over)
    return s


class TempProject(unittest.TestCase):
    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(P, "ROOT", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        r = client.post("/api/projects", json={"name": "test"})
        self.pid = r.json()["id"]
        # injecte 2 scènes
        sf = self.tmp / self.pid / "script.json"
        script = json.loads(sf.read_text(encoding="utf-8"))
        script["scenes"] = [make_scene(1), make_scene(2)]
        sf.write_text(json.dumps(script), encoding="utf-8")


class TestProjects(TempProject):
    def test_create_and_get(self):
        r = client.get(f"/api/projects/{self.pid}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("scenes", r.json()["script"])

    def test_invalid_pid_rejected(self):
        self.assertIn(client.get("/api/projects/..%2Fetc").status_code, (400, 404))

    def test_update_script(self):
        s = client.get(f"/api/projects/{self.pid}").json()["script"]
        s["title"] = "modifié"
        r = client.put(f"/api/projects/{self.pid}/script", json=s)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(client.get(f"/api/projects/{self.pid}").json()["script"]["title"], "modifié")

    def test_export_zip(self):
        r = client.get(f"/api/projects/{self.pid}/export")
        self.assertEqual(r.status_code, 200)


class TestScenes(TempProject):
    def test_get_code_empty(self):
        r = client.get(f"/api/projects/{self.pid}/scenes/0/code")
        self.assertEqual(r.status_code, 200)
        self.assertIn("html", r.json())

    def test_put_code_validates(self):
        r = client.put(f"/api/projects/{self.pid}/scenes/0/code",
                       json={"html": "<html><body>x</body></html>",
                             "css": "body{color:red}", "js": "console.log(1)"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["warnings"], [])
        code = client.get(f"/api/projects/{self.pid}/scenes/0/code").json()
        self.assertIn("body{color:red}", code["css"])

    def test_put_code_warns_on_unbalanced(self):
        r = client.put(f"/api/projects/{self.pid}/scenes/0/code",
                       json={"html": "<html>", "css": "a{", "js": "f("})
        self.assertTrue(r.json()["warnings"])

    def test_add_delete_scene(self):
        r = client.post(f"/api/projects/{self.pid}/scenes", json={"after": -1})
        self.assertEqual(r.json()["index"], 2)
        s = client.get(f"/api/projects/{self.pid}").json()["script"]
        self.assertEqual(len(s["scenes"]), 3)
        r = client.delete(f"/api/projects/{self.pid}/scenes/1")
        self.assertEqual(r.status_code, 200)
        s = client.get(f"/api/projects/{self.pid}").json()["script"]
        self.assertEqual(len(s["scenes"]), 2)

    def test_reorder(self):
        r = client.post(f"/api/projects/{self.pid}/scenes/reorder",
                        json={"order": [1, 0]})
        self.assertEqual(r.status_code, 200)
        s = client.get(f"/api/projects/{self.pid}").json()["script"]
        self.assertEqual(s["scenes"][0]["text"], make_scene(2)["text"])

    def test_reorder_invalid(self):
        r = client.post(f"/api/projects/{self.pid}/scenes/reorder",
                        json={"order": [0, 0]})
        self.assertEqual(r.status_code, 400)

    def test_locked_scene_rejects_regen(self):
        sf = self.tmp / self.pid / "script.json"
        script = json.loads(sf.read_text(encoding="utf-8"))
        script["scenes"][0]["locked"] = True
        sf.write_text(json.dumps(script), encoding="utf-8")
        r = client.post(f"/api/projects/{self.pid}/scenes/0/regenerate",
                        json={"what": "text"})
        self.assertEqual(r.status_code, 409)


class TestVersions(TempProject):
    def test_snapshot_and_restore(self):
        s = client.get(f"/api/projects/{self.pid}").json()["script"]
        s["title"] = "v2"
        client.put(f"/api/projects/{self.pid}/script", json=s)
        r = client.post(f"/api/projects/{self.pid}/versions", json={"label": "test"})
        self.assertEqual(r.status_code, 200)
        # modifie puis restaure
        s["title"] = "v3"
        client.put(f"/api/projects/{self.pid}/script", json=s)
        r = client.get(f"/api/projects/{self.pid}/versions")
        versions = r.json()
        self.assertTrue(versions)
        n = versions[0]["n"]
        r = client.post(f"/api/projects/{self.pid}/versions/{n}/restore")
        self.assertEqual(r.status_code, 200)
        # restore ramène au snapshot n qui contenait "v2"
        self.assertEqual(client.get(f"/api/projects/{self.pid}").json()["script"]["title"], "v2")

    def test_diff(self):
        client.post(f"/api/projects/{self.pid}/versions", json={"label": "a"})
        s = client.get(f"/api/projects/{self.pid}").json()["script"]
        s["title"] = "autre"
        client.put(f"/api/projects/{self.pid}/script", json=s)
        client.post(f"/api/projects/{self.pid}/versions", json={"label": "b"})
        versions = client.get(f"/api/projects/{self.pid}/versions").json()
        n1, n2 = versions[-1]["n"], versions[0]["n"]
        r = client.get(f"/api/projects/{self.pid}/versions/diff", params={"a": n1, "b": n2})
        self.assertEqual(r.status_code, 200)
        self.assertIn("diff", r.json())


class TestAssets(TempProject):
    def test_upload_list_delete(self):
        import base64
        png = base64.b64encode(b"\x89PNG fake").decode()
        r = client.post(f"/api/projects/{self.pid}/assets",
                        json={"name": "logo.png", "data_b64": png})
        self.assertEqual(r.status_code, 200)
        self.assertIn("logo.png", client.get(f"/api/projects/{self.pid}/assets").json())
        r = client.post(f"/api/projects/{self.pid}/assets",
                        json={"name": "evil.exe", "data_b64": png})
        self.assertEqual(r.status_code, 400)
        r = client.delete(f"/api/projects/{self.pid}/assets/logo.png")
        self.assertEqual(r.status_code, 200)


class TestSceneReconstruction(TempProject):
    """Reconstruction correcte : split → combine d'un document autonome."""

    FULL_DOC = """<!DOCTYPE html>
<html><head><style>body{color:red}</style></head>
<body>
<h1>TITRE</h1>
<script>console.log('A');</script>
<p>PARAGRAPHE</p>
<script src="https://cdn.example.com/lib.js"></script>
<script>console.log('B');</script>
</body></html>"""

    def test_split_multi_script_roundtrip(self):
        from server.scenes import split_scene_html
        h, c, j = split_scene_html(self.FULL_DOC)
        # html : contenu intact (le bug historique tronquait après le 1er script)
        self.assertIn("TITRE", h)
        self.assertIn("PARAGRAPHE", h)
        self.assertIn("</body></html>", h.replace("\n", ""))
        # les scripts inline sont extraits, pas de résidu
        self.assertEqual(h.lower().count("<script"), 1)      # seul le src reste
        self.assertIn('src="https://cdn.example.com/lib.js"', h)
        self.assertNotIn("console.log", h)
        # css / js complets
        self.assertEqual(c, "body{color:red}")
        self.assertIn("console.log('A');", j)
        self.assertIn("console.log('B');", j)

    def test_write_then_combine_preserves_everything(self):
        from server.scenes import combine_scene_html, write_scene_code
        write_scene_code(self.pid, 0, self.FULL_DOC)
        doc = combine_scene_html(self.pid, 0).lower()
        self.assertIn("titre", doc)
        self.assertIn("paragraphe", doc)
        self.assertIn("console.log('a')", doc)
        self.assertIn("console.log('b')", doc)
        self.assertIn("cdn.example.com", doc)
        self.assertIn("</body></html>", doc.replace("\n", ""))

    def test_get_code_does_not_create_dirs(self):
        client.get(f"/api/projects/{self.pid}/scenes/0/code")
        # lecture sans effet de bord : aucun dossier scenes/ ne doit apparaître
        scenes_root = self.tmp / self.pid / "scenes"
        existing = [p.name for p in scenes_root.iterdir()] if scenes_root.is_dir() else []
        self.assertEqual(existing, [])

    def test_preview_header_injection(self):
        client.put(f"/api/projects/{self.pid}/scenes/0/code",
                   json={"html": "<html><head></head><body><header>x</header></body></html>",
                         "css": "p{}", "js": ""})
        r = client.get(f"/api/projects/{self.pid}/scenes/0/preview")
        self.assertEqual(r.status_code, 200)
        body = r.text
        # les variables sont injectées dans <head>, pas après <header>
        self.assertLess(body.index("--hf-primary"), body.index("<header"))
        self.assertIn("<header>x</header>", body)


class TestSrtEndpoint(TempProject):
    def test_srt_download(self):
        r = client.get(f"/api/projects/{self.pid}/subtitles/srt")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Scène 1", r.text)


class TestSrt(unittest.TestCase):
    def test_build_srt_format(self):
        from server.tts import _fmt_srt, build_srt
        self.assertEqual(_fmt_srt(0), "00:00:00,000")
        self.assertEqual(_fmt_srt(61.25), "00:01:01,250")
        script = {"scenes": [
            {"text": "bonjour toi", "duration": 2.0,
             "audio": {"duration": 1.5, "words": [
                 {"t": 0.0, "d": 0.4, "w": "bonjour"},
                 {"t": 0.5, "d": 0.4, "w": "toi"}]}},
            {"text": "   ", "duration": 2.0},
        ]}
        srt = build_srt(script)
        self.assertIn("00:00:00,000 -->", srt)
        self.assertIn("bonjour toi", srt)


class TestAIHelpers(unittest.TestCase):
    def test_extract_json_nested(self):
        from server.ai import _extract_json
        self.assertEqual(_extract_json('avant {"a":{"b":"}{"}} après'),
                         {"a": {"b": "}{"}})
        self.assertIsNone(_extract_json("aucun json"))
        self.assertIsNone(_extract_json('{"tronqué'))

    def test_config_endpoints(self):
        r = client.get("/api/ai/config")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("api_key", r.json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
