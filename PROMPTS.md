## Chat -> LOGIC.md
Consider our chat as a review with a waterfall of updates and adjustments.
Go through it from start to finish and collect only the most recent version
of the agreed logic definitions and semantic feedback.

Rewrite these as short, self-contained updates for `LOGIC.md`, arranged in
an order that makes sense when read stand-alone. Do not include code-design
or implementation details unless they are necessary to state the logic
itself.

## LOGIC.md -> CODE.md

There are now two central documents: `LOGIC.md`, which contains the
canonical definition of the interval logic, and `CODE.md`, which contains
the intended classes, functions, types, and interfaces.

Your task is to identify where `CODE.md` diverges from `LOGIC.md`. Parts
must be rewritten when they contradict the upstream document, and could
be rewritten when they were written with other ideas in mind. Even
something as "small" as function/object naming can be considered a divergence.

The workflow is:

`Chat -> LOGIC.md -> CODE.md -> Code`

Do not infer `CODE.md` from the existing code.

## CODE.md -> Code

### 1. Removal / reset

Make a plan to address or remove the parts of the code that diverge from
`CODE.md`. Only implement small tweaks that require essentially no effort,
such as simple renames. All other divergences should be handled with a
reset-style approach.

This step is cleaning: identify the fault line, clear it, and do not
hesitate to break the code base. Preserve only the parts that already
agree with `CODE.md`.

### 2. Rewrite / rebuild

Using `CODE.md` as the sole code-design reference, rebuild the removed or
missing parts cleanly. Prefer fresh implementations over adapting old
structures that were based on different ideas.

Keep the implementation minimal and direct. Do not add interfaces,
abstractions, or behavior that are not required by `CODE.md`.
