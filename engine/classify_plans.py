#!/usr/bin/env python3
"""Classe chaque slide des 21 carrousels exemples de Laurie (mdv-refs/exemples-carrousels/<n>/) par TYPE DE PLAN
→ mdv-refs/plans.json {type: [chemins]}. Sert de référence de cadrage aux slides 2-4 des carrousels générés.
Types : plein_pied · trois_quarts · closeup_matiere · dos · marche · assise · detail_accessoire · lineup · flatlay · autre
"""
import json, os, sys, base64
ENGINE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ENGINE)
import generate_ai as gai
SRC = os.path.join(ENGINE, "mdv-refs", "exemples-carrousels"); OUT = os.path.join(ENGINE, "mdv-refs", "plans.json")
TYPES = ["plein_pied", "trois_quarts", "closeup_matiere", "dos", "marche", "assise", "detail_accessoire", "lineup", "flatlay", "autre"]
PROMPT = ("Classify this fashion photograph into exactly ONE shot type and answer ONLY with JSON {\"type\": \"...\", \"worn\": true/false}. "
          "Types: plein_pied (one woman, full length, standing), trois_quarts (waist-up or knee-up, garment bodice visible), "
          "closeup_matiere (tight crop on fabric/bodice/detail, face partly or fully out of frame), dos (seen from behind), "
          "marche (walking, in motion), assise (seated), detail_accessoire (bag/shoes/hands close-up), lineup (several silhouettes side by side), "
          "flatlay (garment not worn: flat, on hanger, on chair), autre. worn = a person is wearing the garment.")
key = gai.api_key(); plans = {t: [] for t in TYPES}; n = 0
for sub in sorted(os.listdir(SRC), key=lambda x: int(x) if x.isdigit() else 999):
    d = os.path.join(SRC, sub)
    if not os.path.isdir(d): continue
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith((".jpg", ".jpeg", ".png")): continue
        p = os.path.join(d, f)
        try:
            resp = gai.gemini(gai.CHECK_MODEL, [{"text": PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": gai.b64_of(p)}}], key)
            txt = resp["candidates"][0]["content"]["parts"][0]["text"]; j = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
            t = j.get("type") if j.get("type") in TYPES else "autre"
            plans[t].append({"path": os.path.relpath(p, ENGINE), "carrousel": sub, "worn": bool(j.get("worn"))}); n += 1
        except Exception as e:
            plans["autre"].append({"path": os.path.relpath(p, ENGINE), "carrousel": sub, "erreur": str(e)[:80]})
json.dump(plans, open(OUT, "w"), indent=1, ensure_ascii=False)
print(f"{n} slides classées →", {t: len(v) for t, v in plans.items() if v})
