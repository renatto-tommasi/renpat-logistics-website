"""Exercise production route-picker handlers with an offline Node VM DOM harness."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js is required for route-picker tests")
class RouteDestinationTests(unittest.TestCase):
    def check_case(self, name):
        script = Path(__file__).with_name("route_destination_cases.cjs")
        result = subprocess.run(
            ["node", str(script), name], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unsupported_destination_preserves_existing_cargo(self):
        self.check_case("existing_cargo")

    def test_changing_unsupported_city_replaces_generated_note(self):
        self.check_case("replace_city")

    def test_supported_destination_removes_only_generated_note(self):
        self.check_case("supported_city")

    def test_cards_preserve_state_qualified_city_and_cargo(self):
        self.check_case("card_city")

    def test_repeated_card_click_does_not_duplicate_city(self):
        self.check_case("repeat_card")

    def test_supported_card_clears_generated_city(self):
        self.check_case("supported_card")

    def test_main_destination_change_clears_generated_city(self):
        self.check_case("manual_destination")

    def test_form_reset_clears_generated_note_tracking(self):
        self.check_case("reset_state")

    def test_user_authored_destination_note_is_preserved(self):
        self.check_case("preserve_manual_notes")

    def test_user_edit_to_generated_note_is_preserved(self):
        self.check_case("edited_generated_note")
