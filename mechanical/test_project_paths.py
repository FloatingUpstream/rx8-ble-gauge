"""Portable defaults, without requiring CAD or Blender."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from project_paths import aux_root, prototype_output


class OutputTests(unittest.TestCase):
    def test_clean_clone_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(aux_root(), Path(__file__).resolve().parents[1] / ".local/aux")

    def test_aux_override(self):
        with patch.dict(os.environ, {"GAUGE_AUX": "/tmp/gauge-output"}):
            self.assertEqual(
                prototype_output("cradle-v4"), Path("/tmp/gauge-output/mechanical/cradle-v4")
            )


if __name__ == "__main__":
    unittest.main()
