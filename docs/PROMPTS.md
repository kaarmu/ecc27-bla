## Chat -> LOGIC.md

Read the current `LOGIC.md` and the available conversation from start to
finish. If running in a fresh context, use the supplied conversation
transcript; if neither the conversation nor a transcript is available,
request it before editing.

Update `LOGIC.md` directly to incorporate the latest agreed logic definitions
and semantic feedback. Later accepted decisions supersede earlier conflicting
decisions. Do not treat tentative suggestions or unaccepted assistant
proposals as agreements. Preserve unaffected definitions and decisions.

Integrate the changes as concise, self-contained definitions in a coherent
reading order, replacing superseded statements rather than appending a change
log. Preserve necessary assumptions, qualifications, and edge cases. Exclude
code-design and implementation details unless needed to state the logic.

Edit only `LOGIC.md`. Check that the updated definitions, notation, examples,
and cross-references are consistent. Report the changes and list unresolved
questions separately from the canonical definitions. If agreement is unclear
or accepted decisions conflict without a clear superseding decision, leave
the affected content unchanged and report the issue rather than inventing a
resolution. Continue with independent, settled updates.

## LOGIC.md -> CODE.md

Read `LOGIC.md` and `CODE.md`. `LOGIC.md` is the canonical definition of the
interval logic; `CODE.md` specifies the intended Python classes, functions,
types, and interfaces. Authority flows from `LOGIC.md` to `CODE.md` to code.
Do not infer `CODE.md` from the existing implementation.

Identify and correct contradictions, missing requirements, and misleading
semantic implications in `CODE.md`, including names that suggest the wrong
meaning. Edit `CODE.md` directly. Justify each substantive change against a
specific definition or requirement in `LOGIC.md`. Preserve compatible design
choices where the logic leaves freedom; historical differences or naming
preferences alone do not justify a rewrite.

Edit only `CODE.md`. If `LOGIC.md` is ambiguous or contradictory, report the
issue and leave dependent contract changes unresolved rather than silently
choosing new semantics. Continue with independent changes. Make routine
interface-design choices where the logic leaves freedom and identify them as
design choices rather than mathematical requirements.

Check the revised contract for coverage of the logic and internal consistency
across interfaces, descriptions, examples, and verification requirements.
Report the changes with their upstream basis and any remaining gaps or
unresolved questions.

## CODE.md -> Code

### 1. Removal / reset

Read `CODE.md`, then inspect the implementation, tests, and examples for
divergences. `CODE.md` is the authoritative implementation contract; existing
code and tests are evidence of current behavior, not design authority.

Plan and execute the cleanup. Apply only mechanical corrections that require
no new semantic or algorithmic decisions, such as an unambiguous rename and
its references. For other divergences, remove the smallest coherent
implementation components that embody the conflicting design. Preserve
conforming components and tests that express required behavior, even if those
tests will fail until rebuilding is complete. Remove or update tests and
examples only when their expectations contradict the contract.

Temporary import failures and a broken test suite are acceptable at this
stage. Do not add replacement implementations, compatibility layers, new
features, or placeholder behavior. Do not edit `LOGIC.md` or `CODE.md`. If the
contract is ambiguous or contradictory, report the issue and defer affected
cleanup while continuing independent work.

Check the diff against the cleanup plan and run relevant checks to document
the resulting state. Report completed actions, deferred items, and unresolved
questions in this conversation, distinguishing observed failures from expected
but unverified breakages. Finish after cleanup without starting the rebuild
or creating a handoff document.

### 2. Rewrite / rebuild

Start independently in a fresh context. Read `CODE.md` as the sole code-design
authority and derive the required implementation from that contract. Then
inspect the remaining code and tests to identify conforming components and
unmet requirements. Let the contract determine the structure of new code.
Do not use cleanup narratives, handoff documents, or deleted implementations
as design inputs. Do not edit `LOGIC.md` or `CODE.md`.

Rebuild missing or divergent components to implement all required contract
behavior. Preserve conforming components and prefer fresh implementations
over adapting structures based on conflicting designs. Keep the code minimal
and direct. Add private helpers where needed to implement the contract, but
do not introduce unrelated abstractions, extra public interfaces, or behavior
beyond it. Make routine implementation choices where the contract leaves
freedom.

If the contract is ambiguous or contradictory, report the issue rather than
silently choosing new semantics. Continue independent work and identify any
requirements that remain blocked.

Update tests and examples to match the contract. Satisfy the verification
requirements in `CODE.md`, run the relevant tests and project checks, and
resolve implementation failures. Do not weaken required assertions to make
checks pass. Completion requires coverage of every required contract behavior
and passing relevant checks; report any unverified requirements explicitly.

Report what changed, the checks run and their results, and any unresolved
issues. Do not claim completion while required work remains.
