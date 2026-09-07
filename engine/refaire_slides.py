#!/usr/bin/env python3
"""Refait les slides 2-3 d'un carrousel « porte-pose » existant à partir de sa slide 1 (la pièce PORTÉE) avec la
grammaire du tour du produit (07/09/2026, demande Laurie : « plus le truc du fauteuil et à plat »).
Usage : python3 engine/refaire_slides.py approved <dossier> [<dossier>…]
Les anciennes slides 2-3 sont renommées retiree-… (cachées, jamais publiées). Coût ≈ 2-4 générations par carrousel."""
import json, os, sys, random, shutil, time, base64
ENGINE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(ENGINE); sys.path.insert(0, ENGINE)
import generate as core, generate_ai as g
from PIL import Image


def refaire(state, item, key):
    d = os.path.join(ROOT, "queue", state, item)
    hero = os.path.join(d, "slide-1.jpg")
    if not os.path.exists(hero):
        print(f"❌ {item} : pas de slide-1"); return False
    # produit = handle suffixe du dossier
    prods = sorted([p for p in core.fetch_products() if p.get("images")], key=lambda p: -len(p["handle"]))
    # le produit se lit d'abord dans la légende (« The Héloïse ») : le réordonnancement du Cockpit renomme les dossiers
    meta0 = json.load(open(os.path.join(d, "meta.json")))
    import re as _re
    mm = _re.search(r"The ([A-Za-zÀ-ÿ]+)", meta0.get("caption", "") + " " + meta0.get("description", ""))
    prod = None
    if mm:
        prod = next((p for p in prods if core.first_name(p["title"]).lower() == mm.group(1).lower()), None)
    if not prod:
        prod = next((p for p in prods if item.endswith(p["handle"])), None)
    print(f"  produit : {prod['title'] if prod else '?'}")
    if not prod:
        print(f"❌ {item} : produit introuvable"); return False
    name = core.first_name(prod["title"])
    refs = []
    for i, im in enumerate(prod["images"][:4]):
        rp = os.path.join(d, f"ref-{i+1}.jpg"); core.fetch_image(im["src"], 1200).save(rp, quality=92); refs.append(rp)
    ref_dos = g._ref_dos_par_vision(refs, key)
    # anciennes slides posées → retirées
    for f in sorted(os.listdir(d)):
        if f.startswith("slide-") and f != "slide-1.jpg":
            os.rename(os.path.join(d, f), os.path.join(d, "retiree-" + f)); print(f"  retirée : {f}")
    cfg = json.load(open(os.path.join(ENGINE, "scenes.json")))
    # le lieu se LIT dans la slide 1 (07/09 : un décor écrit en dur ne correspondait pas → 6 essais « lieu différent »)
    scene_text = "the same place as the first image"
    try:
        resp = g.gemini(g.CHECK_MODEL, [{"text": "Describe in ONE sentence (max 30 words) the LOCATION and LIGHT of this photo: type of place, walls/ground, notable objects, time of day, light color. Answer ONLY the sentence."},
                                        {"inline_data": {"mime_type": "image/jpeg", "data": g.b64_of(hero)}}], key)
        scene_text = resp["candidates"][0]["content"]["parts"][0]["text"].strip()[:300]
        print(f"  lieu lu dans la slide 1 : {scene_text}")
    except Exception:
        pass
    plans = ["trois_quarts", "dos" if ref_dos else "marche", "closeup_matiere"]
    faits = ["plein_pied"]; journal = []; idx = 1
    for plan in plans:
        if len(faits) >= 3: break
        idx += 1; fname = f"slide-{idx}.jpg"; ok = False
        for essai in (1, 2):
            g._budget_guard()
            consigne = ("Create a NEW photograph from the SAME fashion shoot as the first image: the SAME woman (same face, same hairstyle), wearing the SAME garment, in the SAME location with the SAME light and color palette. "
                        f"This new frame is {g.PLAN_INSTRUCTIONS[plan]}. The garment is WORN by her: a person is always in the frame — never a still life, never on a chair, never laid flat. "
                        "Every garment detail stays EXACTLY as in the product reference photos. Crisp, sharp, real unretouched photograph, no text. "
                        "The camera MOVES: this frame must be clearly different from the first image (different distance, angle and pose) — never a crop or copy of it. "
                        f"THE LOCATION DOES NOT CHANGE: {scene_text}. Do not add stairs, balustrades, columns or any element absent from the first image." + g.lecons_texte(prod["handle"]))
            parts = [{"text": consigne}, {"inline_data": {"mime_type": "image/jpeg", "data": g.b64_of(hero)}}] + [{"inline_data": {"mime_type": "image/jpeg", "data": g.b64_of(r)}} for r in refs]
            resp = g.gemini(g.IMAGE_MODEL, parts, key); raw = None
            for cc in resp.get("candidates", []):
                for pt in cc.get("content", {}).get("parts", []):
                    dd = pt.get("inlineData") or pt.get("inline_data")
                    if dd: raw = base64.b64decode(dd["data"])
            if not raw:
                journal.append({f"{fname} essai {essai}": "pas d'image"}); time.sleep(8); continue
            cp = os.path.join(d, fname); g.save_jpeg(raw, cp)
            ref_v = ref_dos if (plan == "dos" and ref_dos) else refs[0]
            v = g.check_candidate(ref_v, cp, key)
            if not (v.get("dress_identical") and not v.get("invented_details")): v = g.check_candidate(ref_v, cp, key)
            portee = g._slide_est_portee(cp, key); plan_ok, lieu, doublon, lu = g._verifie_plan(hero, cp, plan, key)
            journal.append({f"{fname} essai {essai} ({plan})": {"controle": v, "portee": portee, "plan_ok": plan_ok, "lieu": lieu, "doublon": doublon}})
            if v.get("dress_identical") and not v.get("invented_details") and portee and plan_ok and lieu and not doublon:
                core.cover(Image.open(cp).convert("RGB"), 1080, 1350).save(cp, quality=92); g.clean_noise(cp); ok = True; break
            os.rename(cp, os.path.join(d, f"essai-{fname[:-4]}_{plan}-{essai}-recale.jpg"))
        if ok: faits.append(plan)
        else: idx -= 1
    for rp in refs: os.remove(rp)
    json.dump(journal, open(os.path.join(d, "controle-refaire.json"), "w"), indent=2, ensure_ascii=False)
    mp = os.path.join(d, "meta.json"); m = json.load(open(mp))
    m["recette"] = "tour_du_produit (slides refaites 07/09)"; m["plans"] = faits
    m["description"] = f"Carousel from one shoot: the {name}, {' → '.join(faits)} — same muse, same place, garment always worn."
    if m.get("caption", "").startswith("Worn, then at rest"):
        m["caption"] = f"{name} ~ frame by frame. #inayaparis #quietluxury #eveningdress"
    json.dump(m, open(mp, "w"), indent=2, ensure_ascii=False)
    print(f"{'✅' if len(faits) >= 3 else '⚠️'} {item} : {' → '.join(faits)} ({len(faits)} slides)")
    return len(faits) >= 3


if __name__ == "__main__":
    state = sys.argv[1]; items = sys.argv[2:]
    key = g.api_key()
    for it in items:
        refaire(state, it, key)
