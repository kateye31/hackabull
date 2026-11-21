### FloodNet (single-image water mask)

| Metric | Result |
| --- | --- |
| FloodNet images scored | 10 |
| Pixel counts (TP / FP / FN) | 96,986 / 23,019 / 25,984 |
| Water IoU | 66.4% |
| Water precision / recall | 80.8% / 78.9% |
| Mean image IoU (nonempty union) | 29.7% |

## Sample and interpretation

- Dataset: FloodNet supervised segmentation test split, from the [dataset authors](https://github.com/BinaLab/FloodNet-Supervised_v1.0), using the [192 x 256 mirror](https://huggingface.co/datasets/doantrongthai/floodnet).
- Sample selection: First 10 matched test samples in filename order. Image IDs: 10163, 10164, 10167, 10174, 10183, 10808, 10812, 10813, 10814, 10823.
- Positive label IDs: 3 (flooded road), 5 (water), and 8 (pool), verified against the mirror metadata.
- IoU over pooled pixels was 66.4%. Mean image IoU was 29.7%, reflecting much poorer performance on several images. The sample is small and has only post-storm images. It measures single-image water segmentation. Accuracy of newly flooded area, incident classification, and depth is unmeasured.

## Person A detection handoff

The runnable detection bundle includes a real Hurricane Ian comparison in Estero, Florida. The pre-storm imagery is from [Lee County's 2021 orthophoto collection](https://gisftpdata.leegov.com/AerialPhotos/2021ColorAerials/2021%20Imagery%20Report-Lee%20County%20-Pictometry%20International%20Corp_Signed_060421.pdf). The post-storm imagery is from [NOAA's Hurricane Ian aerial survey](https://oceanservice.noaa.gov/news/sep22/ngs-storm-imagery-ian.html), tile 17/35745/55553 from September 30, 2022. Exact source URLs, bounds, and scale are in the scene metadata.

- From the repository root, install with `python -m pip install -r detection/requirements.txt` and regenerate Estero with `python -m detection.detect data/scenes/ian-estero`. Give Person B the generated scene directory with its imagery, metadata, detections, overlay, and close-ups.
- ORB alignment used 177 inliers. The detector produced three unconfirmed standing-water candidates. Verified that all three pins fall within the scene bounds and that the output JSON references nine local layer and close-up images. Field labels and road/building masks were unavailable, so the candidates have no confirmed flood or street classification.
- A brighter minimum for blue-water candidates reduced suspected shadow artifacts on a separate Bonita Springs crop, from 17 flags to one. It may also miss genuinely dark water. The FloodNet scores above were identical with and without this adjustment.
