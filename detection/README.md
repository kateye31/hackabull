# ReTrace flood detection

Person A owns aerial image alignment, new-water detection, evaluation, and the evidence handed to Person B.

From the repository root, install the detection dependencies and run the included Hurricane Ian scene:

```sh
python -m pip install -r detection/requirements.txt
python -m detection.detect data/scenes/ian-estero
```

The scene directory contains the original images and geographic metadata. Detection writes `detections.json`, `after_aligned.png`, `overlay.png`, and issue close-ups under `crops/`. Give Person B the whole scene directory so the paths in `detections.json` resolve. Exact imagery sources are in `scene.json`.

The Estero scene has three unconfirmed standing-water candidates. The RGB detector can confuse shadows or other smooth surfaces with water and can miss dark water. Road and building classification requires footprint masks aligned to the before image. See [evaluation results](RESULTS.md) for the FloodNet scores and their limits.

To reproduce the synthetic check:

```sh
python -m detection.make_demo_scene --out data/scenes/demo
python -m detection.detect data/scenes/demo
python -m detection.evaluate scene data/scenes/demo
```
