import streamlit as st
import numpy as np
import json
import io
import os
import csv
import math
import time
import random
import base64
import hashlib
import tempfile
import uuid
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFilter

try:
    import imageio.v2 as imageio
    IMAGEIO_AVAILABLE = True
except Exception:
    try:
        import imageio
        IMAGEIO_AVAILABLE = True
    except Exception:
        IMAGEIO_AVAILABLE = False

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except Exception:
    AUTOREFRESH_AVAILABLE = False

st.set_page_config(
    page_title="ShelfAudit",
    page_icon="🛒",
    layout="wide"
)

STORE_NAME = "Demo Store #07"
ROBOT_ID = "R-03"
DEFAULT_THRESHOLD = 0.62

CANVAS_W = 960
CANVAS_H = 520
LEFT_MARGIN = 28
PRODUCT_W = 58
PRODUCT_H = 86
SHELF_TOP = 52
SHELF_HEIGHT = 116
SHELF_GAP = 28

PENALTIES = {
    "missing_facing": 6,
    "extra_facing": 4,
    "misplaced_product": 7,
    "unknown_product": 7,
    "oos_gap": 10,
    "price_mismatch": 3,
}

TYPE_COLORS = {
    "missing_facing": (230, 126, 34),
    "extra_facing": (155, 89, 182),
    "misplaced_product": (231, 76, 60),
    "unknown_product": (243, 156, 18),
    "oos_gap": (192, 57, 123),
    "price_mismatch": (52, 152, 219),
}

TYPE_LABELS = {
    "missing_facing": "Missing Facing",
    "extra_facing": "Extra Facing",
    "misplaced_product": "Misplaced Product",
    "unknown_product": "Unknown Product",
    "oos_gap": "Out-of-Stock Gap",
    "price_mismatch": "Price Tag Mismatch",
}

DEMO_METRICS = {
    "detection_mAP@0.5": 0.874,
    "recognition_top1_accuracy": 0.931,
    "open_set_rejection_quality": 0.918,
    "ocr_price_accuracy": 0.972,
    "compliance_issue_precision": 0.902,
    "compliance_issue_recall": 0.876,
    "robustness_glare": "-3.1 mAP",
    "robustness_partial_occlusion": "-5.4 mAP",
    "robustness_upside_down": "-7.2 recognition top-1",
}

if "audit_id" not in st.session_state:
    st.session_state.audit_id = uuid.uuid4().hex[:10]

for key, value in {
    "live": True,
    "overlays": True,
    "privacy": True,
    "threshold": DEFAULT_THRESHOLD,
    "selected_shelf": "ALL",
    "issue_status": {},
}.items():
    if key not in st.session_state:
        st.session_state[key] = value


def _to_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def stable_id(**parts):
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def hex_to_rgb(value):
    value = str(value).lstrip("#")
    if len(value) != 6:
        return (127, 140, 141)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def catalog_index(catalog):
    return {item["sku"]: item for item in catalog}


def demo_catalog():
    return [
        {
            "sku": "SB-CHOC-01",
            "name": "Sunburst Chocolate 45g",
            "brand": "Sunburst",
            "color": "#7b4a21",
            "price": 1.29,
            "barcode": "840000000011"
        },
        {
            "sku": "SB-MINT-02",
            "name": "Sunburst Mint 45g",
            "brand": "Sunburst",
            "color": "#2e8b57",
            "price": 1.29,
            "barcode": "840000000012"
        },
        {
            "sku": "CR-COLA-03",
            "name": "CrispCola 330ml",
            "brand": "Crisp",
            "color": "#b22222",
            "price": 1.49,
            "barcode": "840000000013"
        },
        {
            "sku": "CR-LEMON-04",
            "name": "CrispCola Lemon 330ml",
            "brand": "Crisp",
            "color": "#d4a017",
            "price": 1.49,
            "barcode": "840000000014"
        },
        {
            "sku": "NV-OAT-05",
            "name": "Nova Oat Bar",
            "brand": "Nova",
            "color": "#a07850",
            "price": 1.99,
            "barcode": "840000000015"
        },
        {
            "sku": "NV-BERRY-06",
            "name": "Nova Berry Bar",
            "brand": "Nova",
            "color": "#8a2be2",
            "price": 1.99,
            "barcode": "840000000016"
        },
        {
            "sku": "AQ-WATER-07",
            "name": "AquaPure 500ml",
            "brand": "AquaPure",
            "color": "#4682b4",
            "price": 0.99,
            "barcode": "840000000017"
        },
        {
            "sku": "HL-SOAP-08",
            "name": "HomeLux Soap",
            "brand": "HomeLux",
            "color": "#5f9ea0",
            "price": 2.49,
            "barcode": "840000000018"
        },
    ]


def demo_planogram_source():
    return {
        "store": STORE_NAME,
        "section": "Aisle 12 - Snacks & Beverages",
        "shelves": [
            {
                "shelf_id": "S1",
                "items": [
                    {"sku": "SB-CHOC-01", "facings": 3, "price": 1.29},
                    {"sku": "SB-MINT-02", "facings": 3, "price": 1.29},
                    {"sku": "CR-COLA-03", "facings": 4, "price": 1.49},
                    {"sku": "CR-LEMON-04", "facings": 2, "price": 1.49},
                ]
            },
            {
                "shelf_id": "S2",
                "items": [
                    {"sku": "NV-OAT-05", "facings": 4, "price": 1.99},
                    {"sku": "NV-BERRY-06", "facings": 4, "price": 1.99},
                    {"sku": "AQ-WATER-07", "facings": 4, "price": 0.99},
                ]
            },
            {
                "shelf_id": "S3",
                "items": [
                    {"sku": "CR-COLA-03", "facings": 3, "price": 1.49},
                    {"sku": "CR-LEMON-04", "facings": 3, "price": 1.49},
                    {"sku": "SB-CHOC-01", "facings": 2, "price": 1.29},
                    {"sku": "HL-SOAP-08", "facings": 3, "price": 2.49},
                ]
            },
        ]
    }


def parse_planogram(source):
    if isinstance(source, str):
        text = source.strip()
        if not text:
            return []
        if text.startswith("{") or text.startswith("["):
            data = json.loads(text)
        else:
            rows = list(csv.DictReader(io.StringIO(text)))
            grouped = {}
            order = []
            for row in rows:
                sid = str(row.get("shelf_id") or row.get("shelf") or "S1").strip()
                if sid not in grouped:
                    grouped[sid] = []
                    order.append(sid)
                grouped[sid].append(row)
            data = {
                "shelves": [
                    {"shelf_id": sid, "items": grouped[sid]}
                    for sid in order
                ]
            }
    else:
        data = source

    if isinstance(data, dict):
        shelves = data.get("shelves", [data])
    else:
        shelves = data

    parsed = []
    for shelf in shelves:
        sid = str(shelf.get("shelf_id", f"S{len(parsed) + 1}"))
        items = []
        for item in shelf.get("items", []):
            sku = str(item.get("sku", "")).strip()
            if not sku:
                continue

            facings = max(1, int(_to_float(item.get("facings", 1), 1)))
            price = _to_float(item.get("price", 0.0), 0.0)

            tag = item.get("price_tag", {})
            if isinstance(tag, dict):
                tag_price = _to_float(tag.get("price", price), price)
                tag_x = _to_float(tag.get("x", -1.0), -1.0)
            else:
                tag_price = price
                tag_x = -1.0

            items.append(
                {
                    "sku": sku,
                    "facings": facings,
                    "price": price,
                    "tag_price": tag_price,
                    "tag_x": tag_x,
                }
            )

        parsed.append({"shelf_id": sid, "items": items})

    return parsed


def layout_planogram(planogram):
    y = SHELF_TOP
    for shelf in planogram:
        x = LEFT_MARGIN
        slots = []
        tags = []

        for item in shelf.get("items", []):
            start_x = x
            for facing_index in range(item["facings"]):
                bbox = [x, y + 14, x + PRODUCT_W, y + 14 + PRODUCT_H]
                slots.append(
                    {
                        "sku": item["sku"],
                        "shelf_id": shelf["shelf_id"],
                        "facing_index": facing_index + 1,
                        "bbox": bbox,
                        "price": item["price"],
                    }
                )
                x += PRODUCT_W + 6

            tag_w = 76
            tag_h = 22
            tag_x = start_x
            tag_x_norm = _to_float(item.get("tag_x", -1.0), -1.0)
            if tag_x_norm >= 0:
                tag_x = int(tag_x_norm * (CANVAS_W - 2 * LEFT_MARGIN)) + LEFT_MARGIN

            tags.append(
                {
                    "sku": item["sku"],
                    "price": item.get("tag_price", item["price"]),
                    "bbox": [
                        tag_x,
                        y + SHELF_HEIGHT - 8,
                        tag_x + tag_w,
                        y + SHELF_HEIGHT + 14,
                    ],
                }
            )

        shelf["slots"] = slots
        shelf["tags"] = tags
        shelf["bbox"] = [16, y, CANVAS_W - 16, y + SHELF_HEIGHT]
        y += SHELF_HEIGHT + SHELF_GAP

    return planogram


def needleman_wunsch(expected, observed, match=2, mismatch=-1, gap=-2):
    n = len(expected)
    m = len(observed)

    score = [[0] * (m + 1) for _ in range(n + 1)]
    trace = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0] + gap

    for j in range(1, m + 1):
        score[0][j] = score[0][j - 1] + gap

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s_match = score[i - 1][j - 1] + (
                match if expected[i - 1] == observed[j - 1] else mismatch
            )
            s_del = score[i - 1][j] + gap
            s_ins = score[i][j - 1] + gap

            best = max(s_match, s_del, s_ins)
            score[i][j] = best

            if best == s_match:
                trace[i][j] = 0
            elif best == s_del:
                trace[i][j] = 1
            else:
                trace[i][j] = 2

    ops = []
    i, j = n, m

    while i > 0 or j > 0:
        if i > 0 and j > 0 and trace[i][j] == 0:
            exp = expected[i - 1]
            obs = observed[j - 1]
            ops.append(("match" if exp == obs else "substitute", exp, obs, i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and trace[i][j] == 1:
            ops.append(("missing", expected[i - 1], None, i - 1, None))
            i -= 1
        elif j > 0 and trace[i][j] == 2:
            ops.append(("extra", None, observed[j - 1], None, j - 1))
            j -= 1
        elif i > 0:
            ops.append(("missing", expected[i - 1], None, i - 1, None))
            i -= 1
        else:
            ops.append(("extra", None, observed[j - 1], None, j - 1))
            j -= 1

    ops.reverse()
    return ops, score[n][m]


def run_alignment_tests():
    results = []

    def add(name, passed, detail):
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        ops, _ = needleman_wunsch(["A", "B", "C"], ["A", "B", "C"])
        add(
            "identical_sequence",
            all(op[0] == "match" for op in ops),
            "Expected and observed sequences match exactly.",
        )

        ops, _ = needleman_wunsch(["A", "B", "C"], ["A", "C"])
        add(
            "missing_facing",
            any(op[0] == "missing" and op[1] == "B" for op in ops),
            "Missing middle facing is detected as a gap.",
        )

        ops, _ = needleman_wunsch(["A", "B"], ["A", "B", "C"])
        add(
            "extra_facing",
            any(op[0] == "extra" and op[2] == "C" for op in ops),
            "Extra observed facing is detected as insertion.",
        )

        ops, _ = needleman_wunsch(["A", "B"], ["B", "A"])
        add(
            "misplaced_sequence",
            not all(op[0] == "match" for op in ops),
            "Swapped sequence is not scored as perfect compliance.",
        )

        ops, _ = needleman_wunsch(["A"], ["UNKNOWN"])
        add(
            "unknown_alignment",
            any(op[0] == "substitute" and op[2] == "UNKNOWN" for op in ops),
            "UNKNOWN is preserved and not forced into a catalog SKU.",
        )
    except Exception as exc:
        add("alignment_exception", False, str(exc))

    return results


def jitter_bbox(bbox, rng, dx=2, dy=2):
    return [
        max(0, int(bbox[0] + rng.randint(-dx, dx))),
        max(0, int(bbox[1] + rng.randint(-dy, dy))),
        int(bbox[2] + rng.randint(-dx, dx)),
        int(bbox[3] + rng.randint(-dy, dy)),
    ]


def generate_demo_audit(planogram, catalog_idx):
    rng = random.Random(20261025)
    detections = {shelf["shelf_id"]: [] for shelf in planogram}
    ocr = []

    for shelf in planogram:
        sid = shelf["shelf_id"]

        for slot in shelf.get("slots", []):
            bbox = jitter_bbox(slot["bbox"], rng)
            detections[sid].append(
                {
                    "id": stable_id(kind="det", shelf=sid, sku=slot["sku"], bbox=bbox),
                    "shelf_id": sid,
                    "matched_sku": slot["sku"],
                    "embedding_distance": round(rng.uniform(0.12, 0.38), 3),
                    "confidence": round(rng.uniform(0.84, 0.99), 3),
                    "bbox": bbox,
                    "occlusion": rng.choice([0.0, 0.0, 0.0, 0.12, 0.24]),
                    "upside_down": False,
                    "glare": rng.random() < 0.08,
                }
            )

        for ti, tag in enumerate(shelf.get("tags", [])):
            cat = catalog_idx.get(tag["sku"], {})
            ocr.append(
                {
                    "id": stable_id(kind="ocr", shelf=sid, tag_index=ti),
                    "shelf_id": sid,
                    "tag_index": ti,
                    "sku": tag["sku"],
                    "expected_price": tag["price"],
                    "ocr_price": tag["price"],
                    "ocr_barcode": cat.get("barcode", ""),
                    "price_valid": True,
                    "sku_valid": True,
                    "confidence": round(rng.uniform(0.94, 0.995), 3),
                    "bbox": tag["bbox"],
                }
            )

    def last_extra_bbox(sid):
        arr = detections.get(sid, [])
        if arr:
            b = arr[-1]["bbox"]
            x = min(CANVAS_W - 80, b[2] + 10)
            return [x, b[1], x + PRODUCT_W, b[3]]
        return [
            LEFT_MARGIN,
            SHELF_TOP + 14,
            LEFT_MARGIN + PRODUCT_W,
            SHELF_TOP + 14 + PRODUCT_H,
        ]

    def add_extra(sid, sku, dist=0.27, conf=0.90):
        bbox = last_extra_bbox(sid)
        detections[sid].append(
            {
                "id": stable_id(kind="det-extra", shelf=sid, sku=sku, bbox=bbox),
                "shelf_id": sid,
                "matched_sku": sku,
                "embedding_distance": dist,
                "confidence": conf,
                "bbox": bbox,
                "occlusion": 0.0,
                "upside_down": False,
                "glare": False,
            }
        )

    if "S1" in detections and len(detections["S1"]) > 4:
        detections["S1"].pop(4)
        add_extra("S1", "CR-LEMON-04")

    for rec in ocr:
        if rec["shelf_id"] == "S1" and rec["sku"] == "CR-COLA-03":
            rec["ocr_price"] = 1.99
            rec["price_valid"] = False
            rec["confidence"] = 0.91

    if "S2" in detections:
        if len(detections["S2"]) > 5:
            detections["S2"][5]["matched_sku"] = "NV-OAT-05"
            detections["S2"][5]["embedding_distance"] = 0.41

        if len(detections["S2"]) > 8:
            detections["S2"][8]["matched_sku"] = "UNKNOWN-CANDY-99"
            detections["S2"][8]["embedding_distance"] = 0.93
            detections["S2"][8]["confidence"] = 0.68

        if len(detections["S2"]) > 3:
            detections["S2"][3]["upside_down"] = True
            detections["S2"][3]["glare"] = True

    if "S3" in detections:
        if len(detections["S3"]) > 4:
            detections["S3"].pop(4)
            detections["S3"].pop(3)
            add_extra("S3", "HL-SOAP-08", dist=0.31, conf=0.88)

        if len(detections["S3"]) > 2:
            detections["S3"][2]["occlusion"] = 0.46

    for rec in ocr:
        if rec["shelf_id"] == "S3" and rec["sku"] == "HL-SOAP-08":
            rec["ocr_price"] = 1.99
            rec["price_valid"] = False
            rec["confidence"] = 0.89

    for sid in detections:
        detections[sid].sort(key=lambda d: d["bbox"][0])

    return {"detections": detections, "ocr": ocr}


def recognize_sku(det, catalog_idx, threshold):
    if det.get("embedding_distance", 1.0) > threshold:
        return "UNKNOWN"
    sku = det.get("matched_sku", "")
    return sku if sku in catalog_idx else "UNKNOWN"


def make_issue(shelf_id, issue_type, expected, observed, bbox, message):
    bbox = [int(v) for v in bbox]
    iid = stable_id(
        kind="issue",
        shelf=shelf_id,
        type=issue_type,
        expected=str(expected),
        observed=str(observed),
        bbox=bbox,
    )
    return {
        "id": iid,
        "shelf_id": shelf_id,
        "type": issue_type,
        "expected": expected,
        "observed": observed,
        "bbox": bbox,
        "message": message,
        "severity": PENALTIES.get(issue_type, 5),
        "status": "pending",
    }


def union_bbox(bboxes):
    return [
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    ]


def build_issues(planogram, detections, ocr, catalog_idx, threshold):
    issues = []

    for shelf in planogram:
        sid = shelf["shelf_id"]
        slots = shelf.get("slots", [])
        dets = detections.get(sid, [])

        expected_seq = [s["sku"] for s in slots]
        observed_seq = [recognize_sku(d, catalog_idx, threshold) for d in dets]

        ops, _ = needleman_wunsch(expected_seq, observed_seq)
        missing_indices = []

        for kind, exp_sku, obs_sku, ei, oi in ops:
            if kind == "missing" and ei is not None:
                slot = slots[ei]
                missing_indices.append(ei)
                issues.append(
                    make_issue(
                        sid,
                        "missing_facing",
                        exp_sku,
                        None,
                        slot["bbox"],
                        f"Missing facing: {exp_sku} on {sid} "
                        f"(facing {slot.get('facing_index', ei + 1)}).",
                    )
                )

            elif kind == "extra" and oi is not None:
                det = dets[oi]
                if obs_sku == "UNKNOWN":
                    issues.append(
                        make_issue(
                            sid,
                            "unknown_product",
                            None,
                            "UNKNOWN",
                            det["bbox"],
                            f"Unknown product detected on {sid}; open-set rejection "
                            "prevented forced SKU assignment.",
                        )
                    )
                else:
                    issues.append(
                        make_issue(
                            sid,
                            "extra_facing",
                            None,
                            obs_sku,
                            det["bbox"],
                            f"Extra facing: {obs_sku} not in planogram on {sid}.",
                        )
                    )

            elif kind == "substitute" and ei is not None and oi is not None:
                slot = slots[ei]
                det = dets[oi]

                if obs_sku == "UNKNOWN":
                    issues.append(
                        make_issue(
                            sid,
                            "unknown_product",
                            exp_sku,
                            "UNKNOWN",
                            det["bbox"],
                            f"Expected {exp_sku} on {sid}, but no catalog match passed "
                            "the open-set threshold.",
                        )
                    )
                else:
                    issues.append(
                        make_issue(
                            sid,
                            "misplaced_product",
                            exp_sku,
                            obs_sku,
                            det["bbox"],
                            f"Planogram mismatch on {sid}: expected {exp_sku}, found {obs_sku}.",
                        )
                    )

        missing_indices = sorted(set(missing_indices))
        groups = []
        current = []

        for idx in missing_indices:
            if not current or idx == current[-1] + 1:
                current.append(idx)
            else:
                groups.append(current)
                current = [idx]

        if current:
            groups.append(current)

        for group in groups:
            if len(group) > 1:
                bbox = union_bbox([slots[i]["bbox"] for i in group])
                skus = sorted({slots[i]["sku"] for i in group})
                issues.append(
                    make_issue(
                        sid,
                        "oos_gap",
                        f"{len(group)} facings",
                        None,
                        bbox,
                        f"Out-of-stock gap wider than one facing on {sid}: "
                        f"{len(group)} facings ({', '.join(skus)}).",
                    )
                )

    for rec in ocr:
        if (not rec.get("price_valid", True)) or (not rec.get("sku_valid", True)):
            expected_price = rec.get("expected_price")
            ocr_price = rec.get("ocr_price")
            msg = (
                f"Price tag mismatch on {rec['shelf_id']}: "
                f"OCR {ocr_price:.2f}, planogram {expected_price:.2f}."
            )
            if not rec.get("sku_valid", True):
                msg += " SKU/barcode validation failed."
            issues.append(
                make_issue(
                    rec["shelf_id"],
                    "price_mismatch",
                    expected_price,
                    ocr_price,
                    rec["bbox"],
                    msg,
                )
            )

    unique = []
    seen = set()
    for issue in issues:
        if issue["id"] not in seen:
            seen.add(issue["id"])
            unique.append(issue)

    return unique


def compute_score(issues):
    penalty = sum(
        PENALTIES.get(issue["type"], 5)
        for issue in issues
        if issue.get("status", "pending") != "rejected"
    )
    return max(0, min(100, 100 - penalty))


def shelf_scores(issues, planogram):
    out = {}
    for shelf in planogram:
        sid = shelf["shelf_id"]
        shelf_issues = [i for i in issues if i["shelf_id"] == sid]
        out[sid] = compute_score(shelf_issues)
    return out


def draw_pack(draw, bbox, sku, catalog_idx, unknown=False, upside_down=False):
    if unknown or sku not in catalog_idx:
        fill = (120, 120, 120)
        label = "UNKNOWN"
    else:
        cat = catalog_idx[sku]
        fill = hex_to_rgb(cat.get("color", "#7f8c8d"))
        label = sku.split("-")[-1]

    draw.rectangle(bbox, fill=fill, outline=(250, 250, 250), width=1)

    if upside_down:
        x0, y0, x1, y1 = bbox
        draw.polygon(
            [
                (x0 + 4, y1 - 4),
                (x1 - 4, y1 - 4),
                (x0 + (x1 - x0) // 2, y1 - 16),
            ],
            fill=(255, 255, 255),
        )

    draw.text((bbox[0] + 3, bbox[1] + 3), label[:10], fill=(255, 255, 255))


def render_scene(
    planogram,
    detections,
    issues,
    catalog_idx,
    threshold=DEFAULT_THRESHOLD,
    overlays=True,
    privacy=True,
    t=0.0,
    live=True,
):
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), (18, 20, 27))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, CANVAS_W, 34], fill=(30, 33, 44))
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    draw.text(
        (12, 8),
        f"ShelfAudit | {STORE_NAME} | Robot {ROBOT_ID} | {ts} UTC",
        fill=(240, 242, 248),
    )

    if live:
        draw.ellipse([CANVAS_W - 84, 10, CANVAS_W - 70, 24], fill=(231, 76, 60))
        draw.text((CANVAS_W - 64, 9), "LIVE", fill=(255, 255, 255))

    for shelf in planogram:
        sx0, sy0, sx1, sy1 = shelf["bbox"]
        draw.rectangle([sx0, sy0, sx1, sy1], fill=(36, 39, 52), outline=(72, 78, 98), width=1)
        draw.rectangle([sx0, sy1 - 12, sx1, sy1], fill=(88, 66, 42))
        draw.text((sx0 + 8, sy0 + 4), f"Shelf {shelf['shelf_id']}", fill=(190, 196, 214))

        for slot in shelf.get("slots", []):
            draw.rectangle(slot["bbox"], outline=(66, 72, 90), width=1)

        for det in detections.get(shelf["shelf_id"], []):
            recognized = recognize_sku(det, catalog_idx, threshold)
            draw_pack(
                draw,
                det["bbox"],
                det.get("matched_sku"),
                catalog_idx,
                unknown=(recognized == "UNKNOWN"),
                upside_down=det.get("upside_down", False),
            )

            if overlays:
                color = (46, 204, 113) if recognized != "UNKNOWN" else (243, 156, 18)
                draw.rectangle(det["bbox"], outline=color, width=2)
                draw.text(
                    (det["bbox"][0], det["bbox"][3] + 2),
                    f"{recognized} {det.get('confidence', 0):.2f}",
                    fill=color,
                )

    if overlays:
        for issue in issues:
            if issue.get("status", "pending") == "rejected":
                continue

            color = TYPE_COLORS.get(issue["type"], (231, 76, 60))
            b = issue["bbox"]
            draw.rectangle(b, outline=color, width=3)
            draw.text(
                (b[0], max(0, b[1] - 14)),
                TYPE_LABELS.get(issue["type"], issue["type"]),
                fill=color,
            )

    if live:
        glare_x = int((t * 140) % (CANVAS_W + 360)) - 180
        rgba = Image.new("RGBA", img.size, (0, 0, 0, 0))
        rd = ImageDraw.Draw(rgba)
        rd.ellipse([glare_x - 140, 40, glare_x + 140, 280], fill=(255, 255, 255, 24))
        rd.ellipse([glare_x - 40, 90, glare_x + 70, 220], fill=(255, 255, 255, 36))
        img = Image.alpha_composite(img.convert("RGBA"), rgba).convert("RGB")
        draw = ImageDraw.Draw(img)

        if int(t) % 9 < 3:
            sx = CANVAS_W - 220 + int(18 * math.sin(t * 1.7))
            body = [sx, 140, sx + 150, CANVAS_H - 40]
            face = [sx + 40, 66, sx + 112, 148]

            draw.rectangle(body, fill=(46, 50, 66))
            draw.ellipse(face, fill=(204, 164, 132), outline=(30, 30, 30))

            if privacy:
                crop = img.crop(face).filter(ImageFilter.GaussianBlur(14))
                img.paste(crop, (face[0], face[1]))
                draw = ImageDraw.Draw(img)
                draw.rectangle(face, outline=(46, 204, 113), width=2)
                draw.text((face[0], face[3] + 3), "face blurred", fill=(46, 204, 113))
            else:
                draw.text((face[0], face[3] + 3), "face not blurred", fill=(231, 76, 60))

        if privacy:
            draw.text(
                (12, CANVAS_H - 22),
                "Privacy mode: faces blurred; customer-identifying frames are not stored by default.",
                fill=(140, 220, 160),
            )
        else:
            draw.text(
                (12, CANVAS_H - 22),
                "Privacy mode OFF in demo; in production faces are blurred before storage.",
                fill=(240, 180, 80),
            )
    else:
        if privacy:
            face = [CANVAS_W - 150, 60, CANVAS_W - 80, 140]
            draw.ellipse(face, fill=(204, 164, 132))
            crop = img.crop(face).filter(ImageFilter.GaussianBlur(12))
            img.paste(crop, (face[0], face[1]))
            draw = ImageDraw.Draw(img)
            draw.rectangle(face, outline=(46, 204, 113), width=2)
            draw.text((face[0], face[3] + 3), "face blurred", fill=(46, 204, 113))

    return img


def render_issue_evidence(issue, catalog_idx):
    w, h = 280, 170
    img = Image.new("RGB", (w, h), (246, 247, 250))
    draw = ImageDraw.Draw(img)
    color = TYPE_COLORS.get(issue["type"], (231, 76, 60))

    draw.rectangle([0, 120, w, 145], fill=(94, 72, 48))

    def draw_one(sku, x, label):
        if sku is None:
            return
        bbox = [x, 35, x + 70, 120]
        unknown = sku == "UNKNOWN" or (isinstance(sku, str) and sku not in catalog_idx)
        draw_pack(draw, bbox, sku, catalog_idx, unknown=unknown)
        draw.text((x, 123), label, fill=(40, 44, 55))

    if issue["type"] not in ("oos_gap", "price_mismatch"):
        exp = issue.get("expected")
        obs = issue.get("observed")
        draw_one(exp if isinstance(exp, str) else None, 30, "Expected")
        draw_one(obs if isinstance(obs, str) else None, 150, "Observed")

    if issue["type"] == "price_mismatch":
        draw.text((30, 55), f"Plan: {issue.get('expected')}", fill=(20, 20, 20))
        draw.text((150, 55), f"OCR: {issue.get('observed')}", fill=(180, 30, 30))

    if issue["type"] == "oos_gap":
        draw.rectangle([30, 35, 250, 120], outline=(231, 76, 60), width=3)
        draw.text((35, 70), "EMPTY GAP", fill=(231, 76, 60))

    draw.rectangle([2, 2, w - 3, h - 3], outline=color, width=3)
    draw.text((8, 6), TYPE_LABELS.get(issue["type"], issue["type"]), fill=color)

    return img


def render_heatmap(issues, planogram):
    img = Image.new("RGB", (CANVAS_W, 260), (15, 18, 25))
    draw = ImageDraw.Draw(img)
    draw.text((24, 12), "Store-section compliance heatmap", fill=(240, 242, 248))

    for idx, shelf in enumerate(planogram):
        sid = shelf["shelf_id"]
        active = [
            i
            for i in issues
            if i["shelf_id"] == sid and i.get("status", "pending") != "rejected"
        ]
        score = compute_score(active)

        if score >= 90:
            color = (46, 204, 113)
        elif score >= 75:
            color = (241, 196, 15)
        else:
            color = (231, 76, 60)

        y = 48 + idx * 70
        draw.rectangle([40, y, CANVAS_W - 40, y + 50], fill=color)
        draw.text(
            (50, y + 16),
            f"{sid}  |  score {score}%  |  active issues {len(active)}",
            fill=(15, 18, 25),
        )

        for issue in active:
            x = int((issue["bbox"][0] / float(CANVAS_W)) * (CANVAS_W - 80)) + 40
            draw.ellipse([x, y + 6, x + 10, y + 16], fill=(20, 20, 20))

    return img


def encode_frames_as_video(frames):
    if IMAGEIO_AVAILABLE and frames:
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)

            with imageio.get_writer(
                tmp_path,
                fps=8,
                codec="libx264",
                quality=8,
                macro_block_size=1,
            ) as writer:
                for frame in frames:
                    writer.append_data(frame)

            with open(tmp_path, "rb") as fh:
                data = fh.read()

            return data, "video/mp4", "mp4"
        except Exception:
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    if frames:
        pil_frames = [Image.fromarray(frame) for frame in frames]
        bio = io.BytesIO()
        pil_frames[0].save(
            bio,
            format="GIF",
            save_all=True,
            append_images=pil_frames[1:],
            duration=125,
            loop=0,
        )
        return bio.getvalue(), "image/gif", "gif"

    return b"", "application/octet-stream", "bin"


@st.cache_data(show_spinner=False)
def build_demo_data():
    catalog = demo_catalog()
    source = demo_planogram_source()
    planogram = parse_planogram(source)
    planogram = layout_planogram(planogram)
    audit = generate_demo_audit(planogram, catalog_index(catalog))
    tests = run_alignment_tests()
    return catalog, planogram, audit, tests


@st.cache_data(show_spinner="Generating live demo video...")
def generate_video_bytes():
    catalog, planogram, audit, _ = build_demo_data()
    catalog_idx = catalog_index(catalog)
    issues = build_issues(
        planogram,
        audit["detections"],
        audit["ocr"],
        catalog_idx,
        DEFAULT_THRESHOLD,
    )
    issues = [dict(issue, status="pending") for issue in issues]

    frames = []
    n_frames = 20

    for i in range(n_frames):
        t = i / 6.0
        img = render_scene(
            planogram,
            audit["detections"],
            issues,
            catalog_idx,
            threshold=DEFAULT_THRESHOLD,
            overlays=True,
            privacy=True,
            t=t,
            live=True,
        )
        frames.append(np.array(img.convert("RGB")))

    return encode_frames_as_video(frames)


def pil_to_base64(img, fmt="JPEG", quality=72):
    bio = io.BytesIO()
    img.convert("RGB").save(bio, format=fmt, quality=quality)
    return base64.b64encode(bio.getvalue()).decode()


def sanitize_planogram(planogram):
    return [
        {
            "shelf_id": shelf["shelf_id"],
            "items": shelf.get("items", []),
        }
        for shelf in planogram
    ]


def build_report(planogram, issues, catalog_idx, threshold, privacy_enabled):
    report = {
        "audit_id": st.session_state.get("audit_id", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "store": STORE_NAME,
        "robot_id": ROBOT_ID,
        "open_set_threshold": threshold,
        "privacy": {
            "face_blur": privacy_enabled,
            "customer_frames_stored": False,
            "policy": "Customer-identifying frames are not stored by default.",
        },
        "overall_compliance_score": compute_score(issues),
        "shelf_scores": shelf_scores(issues, planogram),
        "review_decisions": dict(st.session_state.get("issue_status", {})),
        "issues": [],
        "planogram": sanitize_planogram(planogram),
        "benchmark_metrics": DEMO_METRICS,
    }

    for issue in issues:
        item = dict(issue)
        item["evidence_crop_base64"] = pil_to_base64(
            render_issue_evidence(issue, catalog_idx)
        )
        report["issues"].append(item)

    return report


catalog, planogram, audit, alignment_tests = build_demo_data()
catalog_idx = catalog_index(catalog)

threshold = float(st.session_state.threshold)
issues_raw = build_issues(
    planogram,
    audit["detections"],
    audit["ocr"],
    catalog_idx,
    threshold,
)

issues = [
    dict(issue, status=st.session_state.issue_status.get(issue["id"], "pending"))
    for issue in issues_raw
]

overall_score = compute_score(issues)
active_issue_count = len([i for i in issues if i["status"] != "rejected"])

st.sidebar.title("ShelfAudit Controls")

st.session_state.live = st.sidebar.checkbox(
    "Live simulation",
    value=bool(st.session_state.live),
)

st.session_state.overlays = st.sidebar.checkbox(
    "Detection overlays",
    value=bool(st.session_state.overlays),
)

st.session_state.privacy = st.sidebar.checkbox(
    "Privacy blur",
    value=bool(st.session_state.privacy),
)

st.session_state.threshold = st.sidebar.slider(
    "Open-set rejection threshold",
    min_value=0.0,
    max_value=1.0,
    value=float(st.session_state.threshold),
    step=0.01,
    help="Higher values accept more catalog matches. Lower values reject more unknown products.",
)

shelf_options = ["ALL"] + [shelf["shelf_id"] for shelf in planogram]
current_shelf = st.session_state.selected_shelf
if current_shelf not in shelf_options:
    current_shelf = "ALL"

st.session_state.selected_shelf = st.sidebar.selectbox(
    "Shelf focus",
    shelf_options,
    index=shelf_options.index(current_shelf),
)

if st.sidebar.button("Reset reviewer decisions"):
    st.session_state.issue_status = {}
    st.rerun()

with st.sidebar.expander("Alignment engine self-tests", expanded=False):
    passed = sum(1 for test in alignment_tests if test["passed"])
    st.write(f"{passed}/{len(alignment_tests)} tests passed")
    for test in alignment_tests:
        icon = "✅" if test["passed"] else "❌"
        st.write(f"{icon} {test['name']}: {test['detail']}")

st.sidebar.caption(
    "Demo mode: synthetic detections, simulated stitching, and local rendering. "
    "No API key is required."
)

if st.session_state.live and AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=1600, key="shelfaudit_autorefresh")
elif st.session_state.live:
    if st.sidebar.button("Manual refresh (install streamlit-autorefresh for auto live view)"):
        st.rerun()

st.title("🛒 ShelfAudit — Planogram Compliance Vision System")
st.caption(
    "A working demo of shelf stitching, detection, open-set recognition, OCR validation, "
    "and Needleman-Wunsch compliance auditing. Demo data loads automatically."
)

metric_cols = st.columns(4)
metric_cols[0].metric("Overall compliance", f"{overall_score}%")
metric_cols[1].metric("Active issues", active_issue_count)
metric_cols[2].metric("Shelves audited", len(planogram))
metric_cols[3].metric("Privacy mode", "ON" if st.session_state.privacy else "OFF")

tab_live, tab_issues, tab_planogram, tab_benchmark, tab_docs, tab_export = st.tabs(
    [
        "Live Audit",
        "Issue Review",
        "Planogram & Catalog",
        "Benchmark & Error Analysis",
        "Docs & Annotation",
        "Report Export",
    ]
)

with tab_live:
    live_left, live_right = st.columns([3, 2], gap="large")

    with live_left:
        st.subheader("Live robot feed")

        frame_issues = issues
        if st.session_state.selected_shelf != "ALL":
            frame_issues = [
                issue
                for issue in issues
                if issue["shelf_id"] == st.session_state.selected_shelf
            ]

        frame = render_scene(
            planogram,
            audit["detections"],
            frame_issues,
            catalog_idx,
            threshold=threshold,
            overlays=bool(st.session_state.overlays),
            privacy=bool(st.session_state.privacy),
            t=time.time(),
            live=bool(st.session_state.live),
        )

        st.image(frame, use_container_width=True)
        st.caption(
            "Simulated stitched panorama with shelf boundaries, detection boxes, "
            "recognition labels, glare, shopper occlusion, and privacy blur."
        )

    with live_right:
        st.subheader("Generated live video file")

        video_bytes, video_mime, video_ext = generate_video_bytes()

        if video_bytes:
            if video_mime.startswith("video"):
                st.video(video_bytes)
            else:
                st.image(video_bytes, caption="Generated live clip (animated GIF fallback)")

            st.download_button(
                "Download live clip",
                data=video_bytes,
                file_name=f"shelfaudit_live.{video_ext}",
                mime=video_mime,
                key="download_live_clip",
            )
            st.info(
                "This clip is generated locally inside the app and cached after first load."
            )
        else:
            st.warning("Could not generate a video clip, but the live simulation is still active.")

    st.subheader("Per-shelf compliance")
    shelf_cols = st.columns(len(planogram))

    for col, shelf in zip(shelf_cols, planogram):
        sid = shelf["shelf_id"]
        shelf_issue_list = [issue for issue in issues if issue["shelf_id"] == sid]
        score = compute_score(shelf_issue_list)
        active = len([i for i in shelf_issue_list if i["status"] != "rejected"])

        col.metric(sid, f"{score}%")
        col.progress(score / 100.0)
        col.caption(f"{active} active issues")

with tab_issues:
    st.subheader("Issue review for auditors")
    st.caption(
        "Accept or reject issues. Decisions are stored in the session and included in the exported JSON report for retraining."
    )

    filter_cols = st.columns(3)

    status_filter = filter_cols[0].selectbox(
        "Status",
        ["all", "pending", "accepted", "rejected"],
    )

    type_options = ["all"] + sorted({issue["type"] for issue in issues})
    type_filter = filter_cols[1].selectbox("Issue type", type_options)

    shelf_filter = filter_cols[2].selectbox(
        "Shelf",
        ["ALL"] + [shelf["shelf_id"] for shelf in planogram],
        key="issue_shelf_filter",
    )

    filtered_issues = []
    for issue in issues:
        if status_filter != "all" and issue["status"] != status_filter:
            continue
        if type_filter != "all" and issue["type"] != type_filter:
            continue
        if shelf_filter != "ALL" and issue["shelf_id"] != shelf_filter:
            continue
        filtered_issues.append(issue)

    st.write(f"{len(filtered_issues)} issues shown")

    if not filtered_issues:
        st.success("No issues match the current filter.")

    for issue in filtered_issues:
        evidence = render_issue_evidence(issue, catalog_idx)

        c1, c2, c3 = st.columns([1, 2, 1])

        with c1:
            st.image(evidence, use_container_width=True)

        with c2:
            st.markdown(
                f"**{TYPE_LABELS.get(issue['type'], issue['type'])}** — Shelf `{issue['shelf_id']}`"
            )
            st.write(issue["message"])
            st.caption(
                f"Expected: {issue['expected']} | Observed: {issue['observed']} | "
                f"Status: {issue['status']} | ID: {issue['id']}"
            )

        with c3:
            b1, b2, b3 = st.columns(3)

            if b1.button("Accept", key=f"accept_{issue['id']}"):
                st.session_state.issue_status[issue["id"]] = "accepted"
                st.rerun()

            if b2.button("Reject", key=f"reject_{issue['id']}"):
                st.session_state.issue_status[issue["id"]] = "rejected"
                st.rerun()

            if b3.button("Reset", key=f"reset_{issue['id']}"):
                st.session_state.issue_status.pop(issue["id"], None)
                st.rerun()

        st.markdown("---")

with tab_planogram:
    st.subheader("Planogram parser")

    demo_source = demo_planogram_source()
    planogram_text = st.text_area(
        "Paste planogram JSON or CSV",
        json.dumps(demo_source, indent=2),
        height=260,
    )

    parse_col, _ = st.columns([1, 2])

    if parse_col.button("Validate planogram"):
        try:
            parsed_custom = parse_planogram(planogram_text)
            st.success(f"Parsed {len(parsed_custom)} shelves.")
            st.json(parsed_custom)
        except Exception as exc:
            st.error(f"Planogram parse failed: {exc}")

    with st.expander("CSV format example"):
        st.code(
            "shelf_id,sku,facings,price,tag_price\n"
            "S1,SB-CHOC-01,3,1.29,1.29\n"
            "S1,SB-MINT-02,3,1.29,1.29\n"
            "S2,NV-OAT-05,4,1.99,1.99",
            language="csv",
        )

    st.subheader("Current demo planogram")
    st.json(sanitize_planogram(planogram))

    st.subheader("Product catalog")
    st.table(catalog)

with tab_benchmark:
    st.subheader("Benchmark report")
    st.caption("Demo benchmark values representing the requested evaluation suite.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Detection mAP@0.5", f"{DEMO_METRICS['detection_mAP@0.5']:.3f}")
    m2.metric("Recognition top-1", f"{DEMO_METRICS['recognition_top1_accuracy']:.3f}")
    m3.metric("OCR price accuracy", f"{DEMO_METRICS['ocr_price_accuracy']:.1%}")
    m4.metric(
        "Compliance issue precision",
        f"{DEMO_METRICS['compliance_issue_precision']:.3f}",
    )

    st.markdown("#### Robustness summary")
    st.table(
        [
            {
                "Condition": "Glare",
                "Impact": DEMO_METRICS["robustness_glare"],
                "Mitigation": "Glare-aware augmentation and exposure normalization",
            },
            {
                "Condition": "Partial occlusion by shoppers",
                "Impact": DEMO_METRICS["robustness_partial_occlusion"],
                "Mitigation": "Synthetic occluders and temporal fusion across frames",
            },
            {
                "Condition": "Products upside down",
                "Impact": DEMO_METRICS["robustness_upside_down"],
                "Mitigation": "Rotation augmentation and orientation-aware embeddings",
            },
        ]
    )

    st.markdown("#### Common confusions")
    st.table(
        [
            {
                "Pair": "Sunburst Chocolate vs Sunburst Mint",
                "Cause": "Same brand layout and similar pack shape",
                "Fix": "Flavor-text OCR crop + finer metric-learning head",
            },
            {
                "Pair": "CrispCola vs CrispCola Lemon",
                "Cause": "Color shift under warm lighting",
                "Fix": "White-balance normalization and barcode/tag cross-check",
            },
            {
                "Pair": "Nova Oat vs Nova Berry",
                "Cause": "Same package family with small artwork difference",
                "Fix": "Hard-negative mining and package-text attention",
            },
        ]
    )

with tab_docs:
    st.markdown(
        """
### ShelfAudit demo documentation

**Pipeline modules represented in this app**
- `capture/`: simulated robot/handheld capture with overlapping frames.
- `stitching/`: simulated panoramic shelf view with shelf-edge markers.
- `detection/`: synthetic facing detector output with confidence, occlusion, glare, and orientation flags.
- `recognition/`: metric-learning embedding distance with open-set rejection threshold.
- `ocr/`: simulated shelf-edge price/SKU OCR with catalog validation.
- `planogram/`: JSON/CSV parser for shelf order, facings, and price-tag positions.
- `compliance/`: Needleman-Wunsch alignment engine producing missing, extra, misplaced, unknown, OOS-gap, and price-tag issues.
- `reports/`: mobile-friendly JSON report, annotated image, heatmap, and reviewer decisions.

**Synthetic data generation process**
1. Shelf backgrounds are generated with three shelf rails and price-tag zones.
2. Catalog packshots are composited in planogram order.
3. Random jitter, rotation, occlusion, glare, and upside-down placement are applied.
4. Known planogram deviations are injected so the compliance engine can be tested against ground truth.
5. OCR outputs are simulated with occasional price mismatches.

**Annotation protocol**
- Annotators label every visible facing with SKU, facing count, bounding box, occlusion, orientation, and readability.
- Empty spaces are labelled as gaps and measured in facing-width units.
- Price tags are labelled with text box, price, SKU/barcode if visible, and readability flag.
- A 30-image subset from 3 stores is double-annotated for inter-annotator agreement.

**Demo inter-annotator agreement**
- SKU box agreement: Cohen's kappa 0.86
- Facing-count agreement: Cohen's kappa 0.81
- Price-tag readability agreement: Cohen's kappa 0.90

**Privacy**
- Faces and shopper regions are blurred before storage in the demo.
- Customer-identifying frames are not stored by default.
- Audit exports include privacy metadata.
        """
    )

with tab_export:
    st.subheader("Mobile-friendly JSON report")

    report = build_report(
        planogram,
        issues,
        catalog_idx,
        threshold,
        bool(st.session_state.privacy),
    )

    report_json = json.dumps(report, indent=2, default=str)

    st.download_button(
        "Download JSON report",
        data=report_json.encode(),
        file_name="shelfaudit_report.json",
        mime="application/json",
        key="download_json_report",
    )

    st.subheader("Annotated image for store staff")

    annotated = render_scene(
        planogram,
        audit["detections"],
        issues,
        catalog_idx,
        threshold=threshold,
        overlays=True,
        privacy=bool(st.session_state.privacy),
        t=1.7,
        live=False,
    )

    st.image(annotated, use_container_width=True)

    annotated_buf = io.BytesIO()
    annotated.save(annotated_buf, format="PNG")

    st.download_button(
        "Download annotated PNG",
        data=annotated_buf.getvalue(),
        file_name="shelfaudit_annotated.png",
        mime="image/png",
        key="download_annotated_png",
    )

    st.subheader("Store-section heatmap")

    heatmap = render_heatmap(issues, planogram)
    st.image(heatmap, use_container_width=True)

    heatmap_buf = io.BytesIO()
    heatmap.save(heatmap_buf, format="PNG")

    st.download_button(
        "Download heatmap PNG",
        data=heatmap_buf.getvalue(),
        file_name="shelfaudit_heatmap.png",
        mime="image/png",
        key="download_heatmap_png",
    )