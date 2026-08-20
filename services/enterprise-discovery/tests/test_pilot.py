from __future__ import annotations

import unittest

from stackgraph_discovery.pilot import run_pilot


class PilotHarnessTests(unittest.TestCase):
    def test_rejects_a_workload_below_the_milestone_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 100"):
            run_pilot(99)


if __name__ == "__main__":
    unittest.main()
