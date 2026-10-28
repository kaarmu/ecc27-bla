import subprocess
import sys
import unittest

from ltms_reachability import Axis, GridSpec, TimeWindow, WindowPolicy


class LTMSConfigTests(unittest.TestCase):
    def test_configuration_import_does_not_load_numerical_dependencies(self):
        subprocess.run([sys.executable, "-c", "import sys; import ltms_reachability; "
                        "assert not {'numpy', 'jax', 'pyspect'} & sys.modules.keys()"], check=True)

    def test_time_samples_include_both_endpoints(self):
        spec = GridSpec.bicycle5d()
        self.assertEqual(spec.axes[0].points, 76)
        self.assertEqual(spec.axes[3].pyspect_spec()['name'], '*h')
        self.assertEqual(len(spec.fingerprint()), 64)
        self.assertNotEqual(spec.fingerprint(), spec.fingerprint(dynamics={'wheelbase': .4}))

    def test_invalid_configuration_is_rejected(self):
        for build in (lambda: GridSpec.bicycle5d(time_step=.23),
                      lambda: Axis('x', 1, 0, 5),
                      lambda: TimeWindow(1, 1, False),
                      lambda: WindowPolicy(min_entry=3, max_entry=2)):
            with self.assertRaises(ValueError):
                build()
