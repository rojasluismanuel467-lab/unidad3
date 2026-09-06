"""Re-renderiza los documentos de resultados desde los JSONs en artifacts/.

Diseñado para correrse desde el pre-commit hook: es rápido (solo lee JSONs y
formatea markdown), no reentrena nada. Si faltan JSONs (p.ej. nunca se corrió
mitigación), el script avisa y sale con codigo 0 (no bloquea el commit).

Uso manual: `python regenerate_docs.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from parte_c_combinacion import (
    build_comparative_table,
    build_model_card,
    build_pm_response,
    table_to_markdown,
)

ART = Path("artifacts")
REQUIRED = [
    ART / "baseline_metrics.json",
    ART / "tecnicas_individuales.json",
    ART / "tecnicas_combinadas.json",
]


def main() -> int:
    missing = [p for p in REQUIRED if not p.exists()]
    if missing:
        print(
            "regenerate_docs: skip -- faltan artifacts de mitigación:",
            file=sys.stderr,
        )
        for p in missing:
            print(f"  - {p}", file=sys.stderr)
        print(
            "  Regenera con: python parte_b_mitigacion.py && python parte_c_combinacion.py",
            file=sys.stderr,
        )
        return 0  # no bloquea el commit

    with open(ART / "baseline_metrics.json") as f:
        baseline = json.load(f)
    with open(ART / "tecnicas_individuales.json") as f:
        tecnicas_ind = json.load(f)
    with open(ART / "tecnicas_combinadas.json") as f:
        combined = json.load(f)

    tabla = build_comparative_table(baseline, tecnicas_ind, combined)
    md_tabla = table_to_markdown(tabla)

    pm = build_pm_response(baseline, tecnicas_ind, combined)
    n_words = len(pm.split())
    if n_words > 200:
        print(
            f"regenerate_docs: ERROR -- respuesta al PM excede 200 palabras ({n_words})",
            file=sys.stderr,
        )
        return 1

    n_features = baseline.get("n_features")
    if n_features is None:
        # Fallback: leer del pickle de X_train
        import pickle
        with open(ART / "X_train.pkl", "rb") as f:
            n_features = pickle.load(f).shape[1]

    model_card = build_model_card(baseline, combined, n_features)

    resultados_txt = f"""# RESULTADOS -- Auditoria de sesgo por `gender`

## Tabla comparativa

{md_tabla}

- DPD/EOD: mas cerca de 0 = mas equitativo.
- Adversarial reporta media +- std sobre {len(tecnicas_ind['adversarial']['runs'])} seeds (Zhang et al. 2018).
- AUC del combinado corresponde al predictor adversarial subyacente (el ThresholdOptimizer no expone probas comparables).

## Respuesta al PM

{pm}
"""

    entregable_pm = f"""# Auditoría de sesgo por `gender`

## Tabla comparativa

{md_tabla}

## Correo para el PM

{pm}
"""

    Path("RESULTADOS.md").write_text(resultados_txt, encoding="utf-8")
    Path("MODEL_CARD.md").write_text(model_card, encoding="utf-8")
    Path("ENTREGABLE_PM.md").write_text(entregable_pm, encoding="utf-8")
    print(f"regenerate_docs: OK -- documentos re-renderizados desde {ART}/")
    print(f"  (respuesta PM: {n_words} palabras, tabla: {len(tabla)} filas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
