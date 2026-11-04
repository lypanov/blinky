#!/usr/bin/env python3
"""Unit tests for webcam MCP V4L2 helpers. No camera, ffmpeg, or mcp required."""

from __future__ import annotations

import unittest

from controls import (
    clamp_value,
    expand_gated_updates,
    freeze_auto_exposure,
    measure_rgb,
    parse_v4l2_ctrls,
    resolve_updates,
    set_order,
    settable_updates,
    suggest_nudge,
    well_exposed,
)

V4L2_LOGITECH = """
User Controls

                     brightness 0x00980900 (int)    : min=0 max=255 step=1 default=128 value=128 flags=has-min-max
                       contrast 0x00980901 (int)    : min=0 max=255 step=1 default=32 value=32 flags=has-min-max
                     saturation 0x00980902 (int)    : min=0 max=255 step=1 default=32 value=32 flags=has-min-max
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1
                           gain 0x00980913 (int)    : min=0 max=255 step=1 default=0 value=234 flags=has-min-max
           power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=2 value=2 (60 Hz)
				0: Disabled
				1: 50 Hz
				2: 60 Hz
      white_balance_temperature 0x0098091a (int)    : min=0 max=10000 step=10 default=4000 value=5669 flags=inactive, has-min-max
                      sharpness 0x0098091b (int)    : min=0 max=255 step=1 default=224 value=224 flags=has-min-max
         backlight_compensation 0x0098091c (int)    : min=0 max=2 step=1 default=1 value=1 flags=has-min-max

Camera Controls

                  auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=3 value=3 (Aperture Priority Mode)
				1: Manual Mode
				3: Aperture Priority Mode
         exposure_time_absolute 0x009a0902 (int)    : min=1 max=10000 step=1 default=166 value=57 flags=inactive, has-min-max
     exposure_dynamic_framerate 0x009a0903 (bool)   : default=0 value=1
                 focus_absolute 0x009a090a (int)    : min=0 max=255 step=0 default=0 value=0 flags=has-min-max
"""


class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controls = parse_v4l2_ctrls(V4L2_LOGITECH)
        self.by_name = {c["name"]: c for c in self.controls}

    def test_names(self) -> None:
        self.assertEqual(
            [c["name"] for c in self.controls],
            [
                "brightness",
                "contrast",
                "saturation",
                "white_balance_automatic",
                "gain",
                "power_line_frequency",
                "white_balance_temperature",
                "sharpness",
                "backlight_compensation",
                "auto_exposure",
                "exposure_time_absolute",
                "exposure_dynamic_framerate",
                "focus_absolute",
            ],
        )

    def test_ranges_and_values(self) -> None:
        gain = self.by_name["gain"]
        self.assertEqual(gain["min"], 0)
        self.assertEqual(gain["max"], 255)
        self.assertEqual(gain["default"], 0)
        self.assertEqual(gain["value"], 234)
        self.assertFalse(gain["inactive"])

    def test_inactive_gated_controls(self) -> None:
        self.assertTrue(self.by_name["white_balance_temperature"]["inactive"])
        self.assertTrue(self.by_name["exposure_time_absolute"]["inactive"])
        self.assertEqual(self.by_name["auto_exposure"]["value"], 3)
        self.assertEqual(self.by_name["auto_exposure"]["value_label"], "Aperture Priority Mode")

    def test_menu(self) -> None:
        ae = self.by_name["auto_exposure"]
        self.assertEqual(ae["menu"], {1: "Manual Mode", 3: "Aperture Priority Mode"})
        plf = self.by_name["power_line_frequency"]
        self.assertEqual(plf["menu"][2], "60 Hz")


class UpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.known = {c["name"]: c for c in parse_v4l2_ctrls(V4L2_LOGITECH)}

    def test_aliases_and_gating(self) -> None:
        updates = resolve_updates({"exposure": 200, "gain": 80}, self.known)
        self.assertEqual(updates["exposure_time_absolute"], 200)
        self.assertEqual(updates["auto_exposure"], 1)
        self.assertEqual(updates["gain"], 80)

    def test_white_balance_gate(self) -> None:
        updates = resolve_updates({"white_balance": 4500}, self.known)
        self.assertEqual(updates["white_balance_temperature"], 4500)
        self.assertEqual(updates["white_balance_automatic"], 0)

    def test_clamp(self) -> None:
        self.assertEqual(clamp_value(self.known["brightness"], 999), 255)
        self.assertEqual(clamp_value(self.known["white_balance_temperature"], 4007), 4000)

    def test_set_order_manual_first(self) -> None:
        ordered = [name for name, _ in set_order({"gain": 10, "auto_exposure": 1, "exposure_time_absolute": 80})]
        self.assertEqual(ordered[0], "auto_exposure")
        self.assertIn("exposure_time_absolute", ordered[1:])

    def test_unknown_control(self) -> None:
        with self.assertRaises(ValueError):
            resolve_updates({"nope": 1}, self.known)

    def test_expand_gated(self) -> None:
        self.assertEqual(
            expand_gated_updates({"exposure_time_absolute": 100}),
            {"exposure_time_absolute": 100, "auto_exposure": 1},
        )

    def test_expand_does_not_override_explicit_auto(self) -> None:
        out = expand_gated_updates({"auto_exposure": 3, "exposure_time_absolute": 166})
        self.assertEqual(out["auto_exposure"], 3)
        filtered = settable_updates(out)
        self.assertNotIn("exposure_time_absolute", filtered)
        self.assertEqual(filtered["auto_exposure"], 3)


class ExposureTests(unittest.TestCase):
    def test_measure_mid_gray(self) -> None:
        # 2x2 pixels, luma 128
        data = bytes([128, 128, 128] * 4)
        metrics = measure_rgb(data, 2, 2)
        self.assertEqual(metrics["mean_luma"], 128.0)
        self.assertEqual(metrics["clip_hi_frac"], 0.0)
        self.assertEqual(metrics["clip_lo_frac"], 0.0)
        self.assertTrue(well_exposed(metrics))

    def test_measure_clipped_white(self) -> None:
        data = bytes([255, 255, 255] * 4)
        metrics = measure_rgb(data, 2, 2)
        self.assertEqual(metrics["mean_luma"], 255.0)
        self.assertEqual(metrics["clip_hi_frac"], 1.0)
        self.assertFalse(well_exposed(metrics))

    def test_nudge_reduces_gain_when_bright(self) -> None:
        known = {c["name"]: c for c in parse_v4l2_ctrls(V4L2_LOGITECH)}
        metrics = {"mean_luma": 200.0, "clip_hi_frac": 0.08, "clip_lo_frac": 0.0}
        nudge = suggest_nudge(known, metrics)
        self.assertIsNotNone(nudge)
        assert nudge is not None
        self.assertIn("gain", nudge)
        self.assertLess(nudge["gain"], known["gain"]["value"])

    def test_black_frame_does_not_nudge(self) -> None:
        known = {c["name"]: c for c in parse_v4l2_ctrls(V4L2_LOGITECH)}
        metrics = {"mean_luma": 0.2, "clip_hi_frac": 0.0, "clip_lo_frac": 1.0}
        self.assertEqual(suggest_nudge(known, metrics), {})

    def test_nudge_none_when_ok(self) -> None:
        known = {c["name"]: c for c in parse_v4l2_ctrls(V4L2_LOGITECH)}
        known["gain"]["value"] = 40
        metrics = {"mean_luma": 118.0, "clip_hi_frac": 0.001, "clip_lo_frac": 0.0}
        self.assertIsNone(suggest_nudge(known, metrics))

    def test_dark_room_background_is_ok(self) -> None:
        metrics = {"mean_luma": 120.0, "clip_hi_frac": 0.008, "clip_lo_frac": 0.11}
        self.assertTrue(well_exposed(metrics))

    def test_freeze_auto_exposure(self) -> None:
        known = {c["name"]: c for c in parse_v4l2_ctrls(V4L2_LOGITECH)}
        freeze = freeze_auto_exposure(known)
        self.assertEqual(freeze["auto_exposure"], 1)
        # Inactive AE shutter is stale; use the driver default and keep gain.
        self.assertEqual(freeze["exposure_time_absolute"], 166)
        self.assertEqual(freeze["gain"], 234)


if __name__ == "__main__":
    unittest.main()
