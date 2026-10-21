"""Core imports must work without the separately installed symbolic adapter."""
import subprocess
import sys
import unittest


class OptionalBackendTests(unittest.TestCase):
    def test_core_wildcard_and_protocol_imports_do_not_require_pyspect(self):
        script = r'''
import builtins
import sys
original = builtins.__import__
def without_pyspect(name, *args, **kwargs):
    if name == 'pyspect' or name.startswith('pyspect.'):
        raise ModuleNotFoundError('pyspect intentionally unavailable', name=name)
    return original(name, *args, **kwargs)
builtins.__import__ = without_pyspect
import interval_logic as il
from interval_logic import *
from protocol import Booking, decide_booking
import portion as P
assert not any(name == 'pyspect' or name.startswith('pyspect.') for name in sys.modules)
assert not any(name.startswith('interval_logic.backends') for name in sys.modules)
assert decide_booking(Booking(1, P.closedopen(1, 2)).contract).satisfiable
trace = il.Trace(P.closedopen(0, 2), propositions={'p': P.closedopen(0, 2)})
assert il.satisfies(il.Always('p'), trace, 0)
for name in ('PyspectBackend', 'PyspectStateSet'):
    try:
        getattr(il, name)
    except ModuleNotFoundError as error:
        assert 'installed separately' in str(error)
    else:
        raise AssertionError('optional adapter unexpectedly loaded')
try:
    il.unknown_attribute
except AttributeError:
    pass
else:
    raise AssertionError('unknown attribute should fail')
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
