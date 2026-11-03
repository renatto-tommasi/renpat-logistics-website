"""Map-scene behavior regression tests using the production JavaScript in a Node VM."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js is required for map-scene tests")
class RouteTransitionTests(unittest.TestCase):
    def check_case(self, name):
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("route_transition_cases.cjs")), name],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_form_fades_before_destinations_and_rail_moves_after_reveal(self):
        self.check_case("staged_reveal")

    def test_scroll_progress_clamps_and_reverses(self):
        self.check_case("scroll_clamps")

    def test_keyboard_focus_uses_card_position_not_dom_order(self):
        self.check_case("focus_geometry")

    def test_pointer_focus_does_not_jump_page(self):
        self.check_case("pointer_focus")

    def test_reduced_motion_uses_native_static_layout(self):
        self.check_case("reduced_motion")

    def test_non_overflowing_rail_has_finite_zero_progress(self):
        self.check_case("no_overflow")

    def test_empty_rail_does_not_crash(self):
        self.check_case("empty_cards")

    def test_small_viewport_falls_back_to_stacked_layout(self):
        self.check_case("small_viewport")

    def test_resize_remeasures_scene_geometry(self):
        self.check_case("resize")

    def test_hidden_panels_are_not_keyboard_interactive(self):
        self.check_case("interaction_gating")

    def test_rail_position_accounts_for_rendered_heading_height(self):
        self.check_case("measured_heading")

    def test_reduced_motion_changes_restore_native_interaction(self):
        self.check_case("motion_change")
