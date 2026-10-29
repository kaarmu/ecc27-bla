"""Declared crossing model shared by the coordinator, numerical worker and checks.

Pure Python, so the Python 3.13 worker and the coordinator read one definition.
Coordinates are route-local and eastbound; westbound is their rotation by pi.
Local time tau = t - s for departure s. Exact analytic facts use Fractions;
the worker uses the float values on its grid.
"""
from fractions import Fraction as F

WHEELBASE = .32
BODY_SIZE = (.32, .16)  # toy body length and width [m]; illustrative, not measured
BODY_RADIUS = .18       # circumscribed disk, hypot(.16, .08) = .179 rounded upward
TRACKING = .01          # extra allocation allowance; not a tracking proof
SPEED = .45
ENTRY = (-1.6, -.4, 0., 0., SPEED)  # local (x, y, h, delta, v) at tau = 0
CROSSING = 7            # presence interval [s, s+7]; the reference clears at s+7
LEASE = 8               # lease interval [s, s+8]; allocations stay promised until its end
CLEAR_WINDOW = (7, 8)   # local TLT target window
ENTRY_WINDOW = (0, .5)  # local pass-3 entry window
MANAGED = 1.2           # managed square [-1.2, 1.2]^2
LANE = (-.8, 0.)        # eastbound road, reference-point y-bounds of the copied map
EXIT = ((1.4, 2.), (-.68, -.12))    # exit_e reference-point x- and y-bounds
LANE_STRIP = (-.46, -.34)           # offered corridor is cropped to this y-strip
VMAX = .6
CONTROLS = dict(min_steer=-.1, max_steer=.1, min_accel=-.15, max_accel=.15)
CHART = dict(h=(-.5, .5), d=(-.15, .15), v=(.3, .6))  # nonperiodic route-local chart


def exact(value):
    return F(str(value)) if isinstance(value, float) else F(value)


def eligible_departures(departures, deadline):
    """Departures whose declared reference clears by the deadline: s+7 <= d."""
    return tuple(s for s in departures if s + CROSSING <= deadline)


def tlt_evidence_applies(departure, deadline):
    """The local window [7,8] lies in [s, d]; then it strengthens 'clear by d'."""
    return departure + CLEAR_WINDOW[1] <= deadline


def speed_bound_excludes(departure, deadline):
    """Independent necessary condition: the reference point must travel to exit_e."""
    distance = exact(EXIT[0][0]) - exact(ENTRY[0])
    return exact(VMAX) * (deadline - departure) < distance


def select_departure(service_departures, deadline, promised):
    """Fixed client rule: the earliest eligible departure whose reference access
    a_s is explicitly promised by the accepted owner guarantee.

    It reads only the agreement, which is known before execution; it never
    depends on how the manager later uses unpromised space.
    """
    choices = [s for s in eligible_departures(service_departures, deadline) if s in promised]
    return min(choices) if choices else None


def reference(tau, speed=SPEED):
    """Exact route-local state of the zero-input reference at local time tau."""
    x, y, h, d, _ = map(exact, ENTRY)
    return (x + exact(speed) * exact(tau), y, h, d, exact(speed))


def client_argument(departure, deadline, *, speed=SPEED, lateral=ENTRY[1]):
    """Exact consequences of following one straight zero-input reference.

    With h = delta = 0 and u = 0, the Bicycle5D equations give
    x = x0 + v tau, y = y0 exactly (the worker checks the sampled residual).
    The body is the declared disk.
    """
    r, v = exact(BODY_RADIUS), exact(speed)
    x0, y = exact(ENTRY[0]), exact(lateral)
    x_clear = x0 + v * CROSSING
    lane_low, lane_high = map(exact, LANE)
    return dict(
        access_compliance='Body(xi_s(t)) = Body(z(t)) on [s, s+7]; a_s gives containment',
        body_in_lane=lane_low <= y - r and y + r <= lane_high,
        body_clear_at_exit=x_clear - r > exact(MANAGED),
        reaches_exit=x_clear >= exact(EXIT[0][0]),
        timely=departure + CROSSING <= deadline,
        body_y=(y - r, y + r), exit_x=x_clear, exit_body_min_x=x_clear - r)


def mask_to_task():
    """Implications between the reference-point masks and the full-body task."""
    r = exact(BODY_RADIUS)
    strip, lane = tuple(map(exact, LANE_STRIP)), tuple(map(exact, LANE))
    body_in_lane = (lane[0] + r, lane[1] - r)  # admissible reference-point y-range
    road = lane  # road_e's straight part has the lane's y-range (plus the center octagon)
    return [
        dict(relation='lane strip ± body radius ⊆ eastbound lane',
             holds=body_in_lane[0] <= strip[0] and strip[1] <= body_in_lane[1],
             consequence='every corridor state keeps the full body in the lane'),
        dict(relation='road_e (reference point) ⊆ body-in-lane',
             holds=body_in_lane[0] <= road[0] and road[1] <= body_in_lane[1],
             consequence='road mask alone does not keep the body in the lane'),
        dict(relation='exit_e: x ≥ 1.4 ⇒ body clear of managed square',
             holds=exact(EXIT[0][0]) - r > exact(MANAGED),
             consequence='reaching the goal mask clears the full body in x'),
        dict(relation='exit_e y-range ± body radius ⊆ lane',
             holds=lane[0] <= exact(EXIT[1][0]) - r and exact(EXIT[1][1]) + r <= lane[1],
             consequence='goal mask alone does not keep the body in the lane'),
    ]


# Each physical predicate: arguments, controlling actor, horizon, evidence.
PREDICATES = (
    dict(symbol=r'H_\kappa', meaning='r_j(t) ⊇ R_κ(t): the allocation covers the entire inflated reservation',
         arguments='allocation r_j', actor='owner', horizon='lease [s, s+8]',
         evidence='owner promise; R_κ is the four-pass corridor projected over (h,δ,v), inflated per time slab'),
    dict(symbol='a_s', meaning='Body(ξ_s(t)) ⊆ r_j(t): the reference body is covered',
         arguments='allocation r_j; declared reference ξ_s', actor='owner', horizon='presence [s, s+7]',
         evidence='geometric consequence of H_κ: every swept reference-body box lies in R_κ (conservative raster check)'),
    dict(symbol=r'S_a(\theta)', meaning='⋁ a_s over eligible s ∈ D_θ with s+7 ≤ d_θ',
         arguments='allocation r_j', actor='owner', horizon='[min D_θ, d_θ]',
         evidence='definition (finite disjunction); Boolean algebra'),
    dict(symbol='B_j', meaning='Body(z_j(t)) ⊆ r_j(t) while the vehicle is present',
         arguments='allocation r_j; vehicle trajectory z_j', actor='client, given r_j', horizon='presence [s, s+7]',
         evidence='client policy: following a covered ξ_s gives containment (analytic, perfect nominal model)'),
    dict(symbol=r'S_u(\theta)', meaning='body stays in the lane and clears the managed square with x ≥ 1.4 by d_θ',
         arguments='vehicle trajectory z_j', actor='client', horizon='[s, d_θ]',
         evidence='analytic for straight references; sampled rollout corroborates; TLT is a separate feasibility check'),
)
