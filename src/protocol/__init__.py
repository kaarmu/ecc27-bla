"""Background machinery for the executable paper companion.

``contracts``: saturated Section II algebra and normalization.
``bookings``: validated records, restricted exact decisions and start sampling.
``policies``: callback records, affine utilities and individual output checks.
``verification``: independent interval checks and complete trace witnesses.
``presentation``: tables, lazily imported Plotly figures and offline export.

Admission, offer generation, bargaining and commitment are intentionally defined
in notebooks/protocol.ipynb, where reviewers can read the method in full.
The dependency is protocol -> interval_logic, never the reverse.
"""
from .contracts import Contract, normalize
from .bookings import (Service, Request, Booking, standing, BookingDecision,
                       UnsupportedContractError, decide_booking, Admission,
                       Certificate, CertifiedOffer, representative_starts, validate_standing)
from .policies import (PricedOffer, Policies, BargainRound, BargainingResult, BLA,
                       CommitResult, affine_policies, validate_bargaining,
                       checked_proposal, checked_acceptance, checked_concession,
                       validate_commit, policy_utilities)
from .verification import (independent_feasible_starts, joint_witness,
                           check_joint_behavior, check_boolean_algebra)
from .presentation import (fmt, table, protocol_horizon, plot_booking_progression,
                           plot_signal_traces, display_timeline,
                           illustrative_signal_scenarios, export_timelines)
from ._util import FULL, acc, use, grouped

__all__ = [
    'Contract', 'normalize', 'Service', 'Request', 'Booking', 'standing',
    'BookingDecision', 'UnsupportedContractError', 'decide_booking', 'Admission',
    'Certificate', 'CertifiedOffer', 'representative_starts', 'validate_standing',
    'PricedOffer', 'Policies', 'BargainRound', 'BargainingResult', 'BLA', 'CommitResult',
    'affine_policies', 'validate_bargaining', 'checked_proposal', 'checked_acceptance',
    'checked_concession', 'validate_commit', 'policy_utilities', 'independent_feasible_starts',
    'joint_witness', 'check_joint_behavior', 'check_boolean_algebra', 'fmt', 'table',
    'protocol_horizon', 'plot_booking_progression', 'plot_signal_traces',
    'display_timeline', 'illustrative_signal_scenarios', 'export_timelines',
    'FULL', 'acc', 'use', 'grouped',
]
