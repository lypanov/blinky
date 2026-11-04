#!/usr/bin/env python3
"""Unit tests for LED colour, blob geometry, and board assignment. No camera."""

from __future__ import annotations

import unittest

import numpy as np

from led_detect import (
    BOARD_NANO4K,
    BOARD_PRIMER20K,
    analyze_frames,
    assign_boards,
    board_measure_roi,
    classify_led_color,
    detect_blobs,
    score_led_exposure,
)


def disk(frame: np.ndarray, x: int, y: int, rgb: tuple[int, int, int], radius: int = 4) -> None:
    h, w, _ = frame.shape
    yy, xx = np.ogrid[:h, :w]
    mask = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
    frame[mask] = rgb


class ColorTests(unittest.TestCase):
    def test_red_vs_orange(self) -> None:
        self.assertEqual(classify_led_color(240, 8, 6), "red")
        self.assertEqual(classify_led_color(174, 66, 19), "orange")
        self.assertEqual(classify_led_color(255, 140, 40), "orange")
        self.assertEqual(classify_led_color(10, 10, 10), "other")


class BlobAndScoreTests(unittest.TestCase):
    def test_detects_compact_coloured_blobs(self) -> None:
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        disk(frame, 40, 30, (220, 12, 8), 3)
        disk(frame, 70, 32, (180, 70, 20), 3)
        blobs = detect_blobs(frame)
        colors = sorted(b["color"] for b in blobs)
        self.assertGreaterEqual(len(blobs), 2)
        self.assertIn("red", colors)
        self.assertIn("orange", colors)

    def test_gray_floor_is_not_an_led(self) -> None:
        frame = np.full((80, 80, 3), (72, 54, 50), dtype=np.uint8)
        disk(frame, 40, 40, (74, 52, 51), 6)
        self.assertEqual(detect_blobs(frame), [])

    def test_bloom_and_wash_score_lower_than_distinct_leds(self) -> None:
        good = np.zeros((120, 160, 3), dtype=np.uint8)
        disk(good, 40, 30, (200, 10, 8), 3)
        disk(good, 80, 32, (170, 70, 22), 3)
        disk(good, 42, 80, (210, 15, 10), 3)
        bloom = np.full((120, 160, 3), 150, dtype=np.uint8)
        bloom[20:70, 30:90] = (255, 180, 180)
        sg = score_led_exposure(good)
        sb = score_led_exposure(bloom)
        self.assertGreater(sg["score"], sb["score"])
        self.assertTrue(sg["has_red"])
        self.assertTrue(sg["has_orange"])


class BoardGeometryTests(unittest.TestCase):
    def _five_leds(self, blinking_20k: bool = True) -> list[dict]:
        # Primer 20K (upper): two steady orange + one blinking orange.
        # Nano 4K (lower): one steady red + one blinking red.
        def led(i, x, y, color, state):
            return {
                "id": i,
                "x": float(x),
                "y": float(y),
                "x0": x - 4,
                "y0": y - 4,
                "w": 8,
                "h": 8,
                "area": 20,
                "color": color,
                "state": state,
                "sat": 0.8,
                "hue": 20.0 if color == "orange" else 2.0,
            }

        return [
            led(0, 200, 80, "orange", "steady"),
            led(1, 230, 82, "orange", "steady"),
            led(2, 180, 100, "orange", "blinking" if blinking_20k else "steady"),
            led(3, 205, 280, "red", "steady"),
            led(4, 235, 282, "red", "blinking"),
        ]

    def test_three_plus_two_assigns_20k_and_4k(self) -> None:
        assigned = assign_boards(self._five_leds())
        boards = assigned["boards"]
        self.assertIn(BOARD_PRIMER20K, boards)
        self.assertIn(BOARD_NANO4K, boards)
        self.assertEqual(boards[BOARD_PRIMER20K]["n_leds"], 3)
        self.assertEqual(boards[BOARD_NANO4K]["n_leds"], 2)
        self.assertLess(boards[BOARD_PRIMER20K]["cy"], boards[BOARD_NANO4K]["cy"])

    def test_relative_layout_keeps_20k_on_top(self) -> None:
        # Colour count would prefer the lower trio as 20K; layout wins.
        def led(i, x, y, color, state):
            return {
                "id": i, "x": float(x), "y": float(y), "x0": x - 4, "y0": y - 4,
                "w": 8, "h": 8, "area": 20, "color": color, "state": state,
                "sat": 0.8, "hue": 20.0 if color == "orange" else 2.0,
            }
        leds = [
            led(0, 200, 80, "red", "steady"),
            led(1, 230, 82, "red", "blinking"),
            led(2, 205, 280, "orange", "steady"),
            led(3, 235, 282, "orange", "steady"),
            led(4, 215, 300, "orange", "blinking"),
        ]
        boards = assign_boards(leds)["boards"]
        self.assertLess(boards[BOARD_PRIMER20K]["cy"], boards[BOARD_NANO4K]["cy"])
        self.assertLessEqual(boards[BOARD_PRIMER20K]["n_leds"], 3)
        self.assertLessEqual(boards[BOARD_NANO4K]["n_leds"], 2)

    def test_does_not_use_usb_coordinates(self) -> None:
        # Shift the whole pattern; assignment must follow geometry, not a fixed box.
        leds = self._five_leds()
        for led in leds:
            led["x"] += 90
            led["y"] += 40
            led["x0"] += 90
            led["y0"] += 40
        boards = assign_boards(leds)["boards"]
        self.assertEqual(boards[BOARD_PRIMER20K]["n_leds"], 3)
        self.assertEqual(boards[BOARD_NANO4K]["n_leds"], 2)

    def test_measure_roi_named_board(self) -> None:
        assigned = assign_boards(self._five_leds())
        result = {"boards": assigned["boards"]}
        roi = board_measure_roi(result, "nano4k")
        self.assertIsNotNone(roi)
        x, y, w, h = roi
        self.assertGreater(y, 200)
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertIsNotNone(board_measure_roi(result, "primer20k"))

    def test_never_targets_a_steady_led(self) -> None:
        leds = self._five_leds(blinking_20k=False)
        boards = assign_boards(leds)["boards"]
        self.assertIsNone(boards[BOARD_PRIMER20K]["measure_roi"])
        self.assertIsNone(boards[BOARD_PRIMER20K]["target_led_id"])
        nano = boards[BOARD_NANO4K]
        self.assertIsNotNone(nano["measure_roi"])
        self.assertEqual(nano["target_led_id"], 4)
        roi = nano["measure_roi"]
        self.assertLess(roi["w"], 50)
        self.assertLess(roi["h"], 50)
        self.assertTrue(roi["x"] <= 235 <= roi["x"] + roi["w"])
        self.assertTrue(roi["y"] <= 282 <= roi["y"] + roi["h"])

    def test_finds_bloomed_blinker_via_variance_peak(self) -> None:
        # A 4K-style blinker that blooms past MAX_BLOB_AREA on the max frame
        # must still be targeted from the temporal-variance peak.
        h, w = 240, 320
        fps = 30.0
        frames = []
        for i in range(60):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            disk(frame, 100, 50, (180, 70, 20), 3)
            disk(frame, 130, 52, (175, 68, 18), 3)
            if i % 8 < 4:
                disk(frame, 90, 70, (190, 75, 22), 3)
            disk(frame, 105, 180, (220, 12, 8), 3)
            if i % 8 < 4:
                disk(frame, 135, 182, (230, 10, 6), 12)
            frames.append(frame)
        result = analyze_frames(frames, fps)
        self.assertEqual(result["boards"][BOARD_PRIMER20K]["n_leds"], 3)
        self.assertEqual(result["boards"][BOARD_NANO4K]["n_leds"], 2)
        nano = result["boards"][BOARD_NANO4K]
        self.assertEqual(nano["n_blinking"], 1)
        self.assertIsNotNone(nano["measure_roi"])
        roi = nano["measure_roi"]
        self.assertTrue(roi["x"] <= 135 <= roi["x"] + roi["w"])
        self.assertTrue(roi["y"] <= 182 <= roi["y"] + roi["h"])

    def test_merges_split_cores_of_one_led(self) -> None:
        h, w = 240, 320
        fps = 30.0
        frames = []
        for i in range(60):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            disk(frame, 100, 50, (180, 70, 20), 3)
            disk(frame, 130, 52, (175, 68, 18), 3)
            if i % 8 < 4:
                disk(frame, 90, 70, (190, 75, 22), 3)
            # One steady 4K LED split into two 13 px fragments.
            disk(frame, 105, 180, (220, 12, 8), 3)
            disk(frame, 117, 181, (210, 10, 6), 3)
            if i % 8 < 4:
                disk(frame, 160, 182, (230, 10, 6), 3)
            frames.append(frame)
        result = analyze_frames(frames, fps)
        self.assertEqual(result["boards"][BOARD_NANO4K]["n_leds"], 2)
        xs = [led["x"] for led in result["leds"] if led.get("board") == BOARD_NANO4K]
        self.assertTrue(all(abs(a - b) > 20 for a, b in zip(sorted(xs), sorted(xs)[1:])))

    def test_drops_dim_reflections(self) -> None:
        h, w = 240, 320
        fps = 30.0
        frames = []
        for i in range(60):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            disk(frame, 100, 50, (180, 70, 20), 3)
            disk(frame, 130, 52, (175, 68, 18), 3)
            if i % 8 < 4:
                disk(frame, 90, 70, (190, 75, 22), 3)
            disk(frame, 105, 180, (220, 12, 8), 3)
            if i % 8 < 4:
                disk(frame, 135, 182, (230, 10, 6), 3)
            # Dim silk / box reflections that wander a little.
            flicker = 70 + (i % 5)
            disk(frame, 118, 40, (flicker, 20, 8), 2)
            disk(frame, 140, 175, (flicker, 8, 6), 2)
            frames.append(frame)
        result = analyze_frames(frames, fps)
        self.assertEqual(result["boards"][BOARD_PRIMER20K]["n_leds"], 3)
        self.assertEqual(result["boards"][BOARD_NANO4K]["n_leds"], 2)
        n_blink = sum(1 for led in result["leds"] if led["state"] == "blinking")
        self.assertEqual(n_blink, 2)


class BlinkClassificationTests(unittest.TestCase):
    def test_blinking_vs_steady_over_time(self) -> None:
        h, w = 240, 320
        fps = 30.0
        frames = []
        for i in range(60):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            # 20K upper: two steady orange, one blinking orange
            disk(frame, 100, 50, (180, 70, 20), 3)
            disk(frame, 130, 52, (175, 68, 18), 3)
            if i % 8 < 4:
                disk(frame, 90, 70, (190, 75, 22), 3)
            # 4K lower: one steady red, one blinking red
            disk(frame, 105, 180, (220, 12, 8), 3)
            if i % 8 < 4:
                disk(frame, 135, 182, (230, 10, 6), 3)
            frames.append(frame)
        result = analyze_frames(frames, fps)
        self.assertIn(BOARD_PRIMER20K, result["boards"])
        self.assertIn(BOARD_NANO4K, result["boards"])
        n_blink = sum(1 for led in result["leds"] if led["state"] == "blinking")
        n_steady = sum(1 for led in result["leds"] if led["state"] == "steady")
        self.assertGreaterEqual(n_blink, 1)
        self.assertGreaterEqual(n_steady, 2)
        self.assertEqual(result["boards"][BOARD_PRIMER20K]["n_leds"], 3)
        self.assertEqual(result["boards"][BOARD_NANO4K]["n_leds"], 2)


if __name__ == "__main__":
    unittest.main()
