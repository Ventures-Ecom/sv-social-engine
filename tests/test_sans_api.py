#!/usr/bin/env python3
"""Tests SANS aucun appel payant (07/09/2026, audit) :  python3 -m unittest tests/test_sans_api.py
Couvre les correctifs de l'audit : fenêtre du lot hebdo, briefs ignorés visibles, règle d'alternance,
garde-fou d'apprentissage, mode SV_FAKE_GEMINI, purge en simulation, résolution des noms avec accents."""
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
os.environ["SV_FAKE_GEMINI"] = "1"
os.environ.setdefault("GEMINI_API_KEY", "fake")

import inspectrice  # noqa: E402
import apprendre  # noqa: E402
import generate as core  # noqa: E402
import generate_ai as g  # noqa: E402
import purge  # noqa: E402

PRODUITS = [
    {"title": "Vespera — The Velvet Gown", "handle": "vespera-the-velvet-gown"},
    {"title": "Bourgeoise Dress", "handle": "bourgeoise-dress"},
    {"title": "Ruby — The Midnight Muse Gown", "handle": "ruby-the-midnight-muse-gown"},
    {"title": "Zoé — Sweater", "handle": "sweater-zoe"},
]


class LotHebdo(unittest.TestCase):
    def setUp(self):
        self.lundi = datetime(2026, 9, 7, 6, 40, tzinfo=timezone.utc)

    def run_(self, delta_h, conclusion="success", status="completed"):
        return {"created_at": (self.lundi - timedelta(hours=delta_h)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "conclusion": conclusion, "status": status}

    def test_lot_du_dimanche_compte(self):
        self.assertTrue(inspectrice.lot_deja_parti([self.run_(14)], self.lundi))

    def test_lot_vieux_d_une_semaine_ne_compte_pas(self):
        self.assertFalse(inspectrice.lot_deja_parti([self.run_(7 * 24 + 14)], self.lundi))

    def test_run_echoue_ne_compte_pas_mais_run_en_cours_oui(self):
        self.assertFalse(inspectrice.lot_deja_parti([self.run_(2, "failure")], self.lundi))
        self.assertTrue(inspectrice.lot_deja_parti([self.run_(1, None, "in_progress")], self.lundi))

    def test_fenetre_courte_anti_empilement(self):
        self.assertTrue(inspectrice.lot_deja_parti([self.run_(3)], self.lundi, fenetre_h=6))
        self.assertFalse(inspectrice.lot_deja_parti([self.run_(9)], self.lundi, fenetre_h=6))


class Apprentissage(unittest.TestCase):
    def test_raison_qui_parle_d_une_autre_robe(self):
        self.assertEqual(apprendre.autre_robe_citee("J'ai demandé la vespéra dress.", "bourgeoise-dress", PRODUITS), "Vespera")

    def test_raison_sur_la_bonne_robe(self):
        self.assertIsNone(apprendre.autre_robe_citee("La Bourgeoise est trop courte ici", "bourgeoise-dress", PRODUITS))

    def test_raison_generique(self):
        self.assertIsNone(apprendre.autre_robe_citee("peau trop lisse, visage plastique", "ruby-the-midnight-muse-gown", PRODUITS))


class Alternance(unittest.TestCase):
    def test_handles_en_file_et_tirage(self):
        with tempfile.TemporaryDirectory() as tmp:
            for st, nom in (("approved", "2026-09-07_100300_carousel_tour_ruby-the-midnight-muse-gown"),
                            ("approved", "2026-09-07_100500_ai-studio_bretonne-the-cozy-striped-knit"),
                            ("pending", "2026-09-07_100800_carousel_porte-pose_sweater-zoe 2")):
                os.makedirs(os.path.join(tmp, "queue", st, nom))
            en_file = core.handles_en_file(tmp)
            self.assertEqual(en_file["ruby-the-midnight-muse-gown"], {"carousel"})
            self.assertEqual(core.handle_du_dossier("2026-09-07_100300_carousel_tour_ruby-the-midnight-muse-gown", PRODUITS), "ruby-the-midnight-muse-gown")
            self.assertEqual(core.handle_du_dossier("2026-09-07_100200_carousel_porte-pose_bianca-gown"), "bianca-gown")
            self.assertEqual(core.handle_du_dossier("2026-09-07_100500_ai-studio_bretonne-knit 2"), "bretonne-knit")
            self.assertEqual(en_file["bretonne-the-cozy-striped-knit"], {"post"})
            self.assertIn("sweater-zoe", en_file)  # suffixe « 2 » du Finder ignoré
            core.ROOT, old = tmp, core.ROOT
            try:
                prods = [dict(p, images=[{"src": "x.jpg"}]) for p in PRODUITS]
                chosen = core.pick_products(prods, {"used_captions": [], "used_products": []}, 2)
                self.assertTrue(all(p["handle"] not in en_file for p in chosen), [p["handle"] for p in chosen])
            finally:
                core.ROOT = old


class NomsAccents(unittest.TestCase):
    def test_vespera_avec_accent(self):
        trouves, introuvables, _ = core.resoudre_produits(PRODUITS, "Vespéra, Zoé et Nocturne")
        self.assertEqual([p["handle"] for p in trouves], ["vespera-the-velvet-gown", "sweater-zoe"])
        self.assertEqual(introuvables, ["Nocturne"])


class ModeTest(unittest.TestCase):
    def test_fake_image_et_verdicts(self):
        self.assertTrue(g.FAKE)
        resp = g.gemini(g.IMAGE_MODEL, [{"text": "test"}], "fake")
        self.assertTrue(resp.get("fake"))
        self.assertIn("inlineData", resp["candidates"][0]["content"]["parts"][0])
        v = g.check_candidate.__wrapped__ if hasattr(g.check_candidate, "__wrapped__") else None
        resp2 = g.gemini(g.CHECK_MODEL, [{"text": "Answer ONLY with JSON"}], "fake")
        j = json.loads(resp2["candidates"][0]["content"]["parts"][0]["text"])
        self.assertEqual(j["verdict"], "pass")
        self.assertTrue(j["worn"] and not j["still_life"] and j["face_clean"])

    def test_budget_intact_en_mode_test(self):
        bp = os.path.join(ROOT, "engine", "budget.json")
        avant = open(bp).read() if os.path.exists(bp) else None
        g._budget_guard()
        apres = open(bp).read() if os.path.exists(bp) else None
        self.assertEqual(avant, apres)


class Purge(unittest.TestCase):
    def test_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "queue", "approved", "2026-09-07_100100_carousel_tour_luxury-dress")
            os.makedirs(d)
            for f in ("slide-1.jpg", "essai-slide-3_dos-1-recale.jpg", "ref-1.jpg", "retiree-slide-2.jpg", "meta.json"):
                open(os.path.join(d, f), "w").write("x")
            r = os.path.join(tmp, "queue", "rejected", "2026-08-01_000000_ai-studio_vieux")
            os.makedirs(r); open(os.path.join(r, "media.jpg"), "w").write("x")
            vieux = time.time() - 40 * 86400
            os.utime(r, (vieux, vieux))
            items = purge.plan(root=tmp)
            chemins = sorted(os.path.relpath(p, tmp) for p, _, _ in items)
            self.assertIn("queue/approved/2026-09-07_100100_carousel_tour_luxury-dress/essai-slide-3_dos-1-recale.jpg", chemins)
            self.assertIn("queue/approved/2026-09-07_100100_carousel_tour_luxury-dress/ref-1.jpg", chemins)
            self.assertNotIn("queue/approved/2026-09-07_100100_carousel_tour_luxury-dress/retiree-slide-2.jpg", chemins)
            self.assertIn("queue/rejected/2026-08-01_000000_ai-studio_vieux", chemins)
            self.assertTrue(all(os.path.exists(p) for p, _, _ in items), "simulation : rien supprimé")


if __name__ == "__main__":
    unittest.main()
