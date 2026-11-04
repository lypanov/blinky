#!/usr/bin/env python3
"""Unit tests for blink detector arbitration and named ROIs. No numpy/camera."""

from __future__ import annotations

import unittest

from blink_trust import (
    PREDICTED_BLINK3_HZ,
    choose_trusted,
    named_board,
    parse_roi_arg,
    search_window,
)


class RoiTests(unittest.TestCase):
    def test_auto_default(self) -> None:
        self.assertEqual(parse_roi_arg(None), ("auto", None))
        self.assertEqual(parse_roi_arg("auto"), ("auto", None))

    def test_named_regions(self) -> None:
        self.assertEqual(parse_roi_arg("top")[0], "top")
        self.assertEqual(parse_roi_arg("nano4k")[0], "bottom")
        self.assertEqual(parse_roi_arg("primer20k")[0], "top")
        self.assertEqual(parse_roi_arg("full")[0], "full")

    def test_manual(self) -> None:
        kind, xywh = parse_roi_arg("340,104,106,102")
        self.assertEqual(kind, "manual")
        self.assertEqual(xywh, (340, 104, 106, 102))

    def test_search_split(self) -> None:
        self.assertEqual(search_window("top", 640, 480), (0, 0, 640, 240))
        self.assertEqual(search_window("bottom", 640, 480), (0, 240, 640, 240))

    def test_bad_roi(self) -> None:
        with self.assertRaises(ValueError):
            parse_roi_arg("left")

    def test_named_board(self) -> None:
        self.assertEqual(named_board("nano4k"), "nano4k")
        self.assertEqual(named_board("primer-20k"), "primer20k")
        self.assertIsNone(named_board("top"))
        self.assertIsNone(named_board(None))


class TrustTests(unittest.TestCase):
    def test_agreeing_detectors_trust_edge(self) -> None:
        method, _ = choose_trusted(
            edge_hz=3.424,
            fft_hz=3.444,
            fft_snr=10.0,
            edge_count=185,
            duration_s=27.0,
        )
        self.assertEqual(method, "edge")

    def test_disagreement_is_untrusted(self) -> None:
        # Steady 20K LED whose FFT leaked the Nano 4K 3.43 Hz blink.
        method, reason = choose_trusted(
            edge_hz=3.941,
            fft_hz=3.430,
            fft_snr=22.5,
            edge_count=40,
            duration_s=8.0,
        )
        self.assertEqual(method, "untrusted")
        self.assertIn("disagree", reason)

    def test_undercount_disagreement_is_untrusted(self) -> None:
        method, reason = choose_trusted(
            edge_hz=3.45,
            fft_hz=6.852,
            fft_snr=8.0,
            edge_count=40,
            duration_s=25.0,
        )
        self.assertEqual(method, "untrusted")
        self.assertIn("disagree", reason)

    def test_no_edges_uses_fft(self) -> None:
        method, _ = choose_trusted(
            edge_hz=None, fft_hz=3.43, fft_snr=6.0, edge_count=0, duration_s=20.0
        )
        self.assertEqual(method, "fft")

    def test_predicted_blink3(self) -> None:
        self.assertAlmostEqual(PREDICTED_BLINK3_HZ, 3.433, places=3)


if __name__ == "__main__":
    unittest.main()
