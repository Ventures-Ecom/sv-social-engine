#!/usr/bin/env python3
"""
PURGE — libère l'espace que le moteur accumule (07/09/2026 : 93 dossiers rejetés = 40 Mo, essais recalés
et références produit versionnés à vie dans les dossiers livrés, .git à 85 Mo).

Usage :  python3 engine/purge.py            → simulation (rien n'est supprimé, liste + poids)
         python3 engine/purge.py --apply    → suppression réelle
         options : --rejected-jours 30  (âge minimum des dossiers rejetés supprimés)
                   --atelier-jours 2    (âge minimum des ateliers abandonnés)

Ce qui est supprimé :
  1. dans queue/approved, queue/published, queue/archive : les essais recalés (essai-*-recale.jpg)
     et les références produit téléchargées (ref-*.jpg, reference*.jpg) — jamais publiés, versionnés ;
  2. dans queue/published et queue/archive uniquement : les slides retirées (retiree-*.jpg) ;
     (jamais dans pending/approved : Laurie peut encore les remettre avec « slide_on »)
  3. queue/rejected/<dossier> plus vieux que N jours (local uniquement, ignoré par git) ;
  4. queue/_atelier/<dossier> plus vieux que N jours (générations interrompues).
Les suppressions du point 1-2 touchent des fichiers versionnés : committer ensuite (le Cockpit le fait
au prochain clic ; en cloud, l'étape « Archiver » des workflows).
"""
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue")
RECALE = re.compile(r"^(essai-.*-recale\.jpg|ref-\d+\.jpg|reference(-\d+)?\.jpg)$")
RETIREE = re.compile(r"^retiree-.*\.jpg$")


def _taille(p):
    if os.path.isfile(p):
        return os.path.getsize(p)
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs)


def plan(root=ROOT, rejected_jours=30, atelier_jours=2, now=None):
    """Liste (chemin, motif, octets) de ce qui serait supprimé. Pure lecture."""
    now = now or time.time()
    out = []
    for st in ("approved", "published", "archive"):
        base = os.path.join(root, "queue", st)
        if not os.path.isdir(base):
            continue
        for it in sorted(os.listdir(base)):
            d = os.path.join(base, it)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if RECALE.match(f):
                    out.append((p, "essai recalé / référence produit", _taille(p)))
                elif RETIREE.match(f) and st != "approved":
                    out.append((p, "slide retirée d'un contenu déjà publié", _taille(p)))
    for st, jours in (("rejected", rejected_jours), ("_atelier", atelier_jours)):
        base = os.path.join(root, "queue", st)
        if not os.path.isdir(base):
            continue
        for it in sorted(os.listdir(base)):
            d = os.path.join(base, it)
            if os.path.isdir(d) and now - os.path.getmtime(d) > jours * 86400:
                out.append((d, f"{st} de plus de {jours} j", _taille(d)))
    return out


def main(argv):
    apply = "--apply" in argv
    def opt(name, default):
        return int(argv[argv.index(name) + 1]) if name in argv and argv.index(name) + 1 < len(argv) else default
    items = plan(rejected_jours=opt("--rejected-jours", 30), atelier_jours=opt("--atelier-jours", 2))
    total = sum(t for _, _, t in items)
    for p, motif, t in items:
        print(f"{'SUPPRIMÉ ' if apply else 'à supprimer'} {t / 1e6:6.2f} Mo  {os.path.relpath(p, ROOT)}  ({motif})")
        if apply:
            (shutil.rmtree if os.path.isdir(p) else os.remove)(p)
    print(f"{'Libéré' if apply else 'Libérable'} : {total / 1e6:.1f} Mo sur {len(items)} élément(s)"
          + ("" if apply else " — relancer avec --apply pour supprimer"))


if __name__ == "__main__":
    main(sys.argv[1:])
