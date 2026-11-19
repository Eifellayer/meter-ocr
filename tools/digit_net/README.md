# Ziffernnetz (Experiment, noch nicht im Einsatz)

Trainingswerkzeuge für eine kleine Ziffernerkennung für unscharfe Rollenziffern (synthetische Daten,
NumPy-CNN, Export als int8-JSON; `digit_net.py` ist die reine Python-Inferenz für die App).

Stand 20.11.2026: Auf synthetischen Daten ~93 %, an echten unscharfen Kamerabildern aber zu oft
sicher falsch (z. B. 8 → 5, 6 → 9). Darum nicht in 0.2.0 eingebaut. Nächster Schritt laut
RELEASE-PLAN.md: lernende Ziffernbibliothek je Zähler (Experiment 2), gestartet mit einem einmal
eingetragenen Zählerstand.

    python3 mkdata.py 24 500 train.npz           # 240 000 synthetische Ziffern
    python3 traincnn.py train.npz 10 12 24 64 cnn.npz
    python3 export.py cnn.npz digit_net.json
