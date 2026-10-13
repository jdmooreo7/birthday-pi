"""Face spike: detect faces in /photos, group them by person, report speed and memory.

Writes face crops grouped by person to /results/person_NN/ plus summary.json,
so a human can judge accuracy by eye.
"""
import json
import os
import resource
import sys
import time

import cv2
import numpy as np

PHOTOS, RESULTS = "/photos", "/results"
MAX_SIDE = 1920          # photos are resized to screen size on import
MIN_FACE = 40            # ignore faces smaller than this (pixels, after resize)
SCORE = 0.8              # detection confidence
MATCH = 0.363            # SFace cosine-similarity threshold from OpenCV Zoo
MIN_PHOTOS = 3           # product rule: a person needs 3 photos to be offered


def peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def load(path):
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def main():
    t0 = time.time()
    detector = cv2.FaceDetectorYN.create("/models/yunet.onnx", "", (320, 320), SCORE)
    recognizer = cv2.FaceRecognizerSF.create("/models/sface.onnx", "")
    load_s = time.time() - t0
    print(f"models loaded in {load_s:.2f}s, peak {peak_mb():.0f} MB")

    names = sorted(f for f in os.listdir(PHOTOS) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
    skipped = sorted(set(os.listdir(PHOTOS)) - set(names))
    faces, per_photo = [], []
    for name in names:
        t = time.time()
        img = load(os.path.join(PHOTOS, name))
        if img is None:
            skipped.append(name)
            continue
        h, w = img.shape[:2]
        detector.setInputSize((w, h))
        _, dets = detector.detect(img)
        found = 0
        for det in dets if dets is not None else []:
            if min(det[2], det[3]) < MIN_FACE:
                continue
            aligned = recognizer.alignCrop(img, det)
            feat = recognizer.feature(aligned).flatten()
            faces.append({"photo": name, "feat": feat / np.linalg.norm(feat), "crop": aligned,
                          "score": float(det[14]), "size": int(min(det[2], det[3]))})
            found += 1
        dt = time.time() - t
        per_photo.append(dt)
        print(f"  {name}: {found} face(s) in {dt:.2f}s")

    # Group faces: average-linkage agglomerative clustering on cosine similarity.
    clusters = [[i] for i in range(len(faces))]
    feats = np.array([f["feat"] for f in faces]) if faces else np.zeros((0, 128))
    sim = feats @ feats.T
    while len(clusters) > 1:
        best, pair = MATCH, None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                s = sim[np.ix_(clusters[a], clusters[b])].mean()
                if s > best:
                    best, pair = s, (a, b)
        if pair is None:
            break
        a, b = pair
        clusters[a] += clusters.pop(b)
    clusters.sort(key=len, reverse=True)

    people = []
    for n, members in enumerate(clusters, 1):
        photos = sorted({faces[i]["photo"] for i in members})
        folder = os.path.join(RESULTS, f"person_{n:02d}")
        os.makedirs(folder, exist_ok=True)
        for i in members:
            cv2.imwrite(os.path.join(folder, f"{os.path.splitext(faces[i]['photo'])[0]}_{i}.jpg"), faces[i]["crop"])
        people.append({"person": f"person_{n:02d}", "faces": len(members), "photos": photos,
                       "offered": len(photos) >= MIN_PHOTOS})

    summary = {
        "photos": len(per_photo), "skipped": skipped, "faces": len(faces), "groups": len(people),
        "groups_offered_3plus_photos": sum(p["offered"] for p in people),
        "model_load_s": round(load_s, 2),
        "per_photo_s": {"mean": round(float(np.mean(per_photo)), 2) if per_photo else None,
                        "max": round(max(per_photo), 2) if per_photo else None},
        "total_s": round(time.time() - t0, 1), "peak_rss_mb": round(peak_mb()),
        "est_1000_photos_min": round(float(np.mean(per_photo)) * 1000 / 60, 1) if per_photo else None,
        "people": people,
    }
    # Save each face's embedding and group, for threshold calibration.
    np.save(os.path.join(RESULTS, "embeddings.npy"), feats)
    group_of = {i: n for n, members in enumerate(clusters, 1) for i in members}
    with open(os.path.join(RESULTS, "faces.json"), "w") as f:
        json.dump([{"photo": faces[i]["photo"], "group": group_of[i], "score": round(faces[i]["score"], 3),
                    "size": faces[i]["size"]} for i in range(len(faces))], f)
    with open(os.path.join(RESULTS, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "people"}, indent=2))
    for p in people:
        print(f"  {p['person']}: {p['faces']} face(s) in {len(p['photos'])} photo(s){'  <- offered' if p['offered'] else ''}")


if __name__ == "__main__":
    sys.exit(main())
