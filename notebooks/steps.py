from contextlib import contextmanager

@contextmanager
def step(msg: str, disable: int = 4):
    counter = list(getattr(step, "counter", (0,)))
    counter[-1] += 1

    if len(counter) == 1:
        println(f"⏺ Step {counter[0]}: {msg}")
    else:
        println(
            f"⏺ Step {'.'.join(map(str, counter))}: {msg}",
            marker=["├", "│"],
        )

    step.counter = tuple(counter + [0])
    _disable = getattr(step, "disable", 4)
    step.disable = disable

    try:
        yield
    finally:
        pass

    step.disable = _disable
    step.counter = step.counter[:-1]

    if len(step.counter) == 1:
        println("╯", left=0)
    else:
        println("", marker=["├─╯", "│"])


def reset_step():
    step.counter = (0,)
    step.disable = 4


def println(*lines: str, **kwds):
    assert all(isinstance(line, str) for line in lines)

    lines = [""] if len(lines) == 0 else list(lines)
    marker = kwds.get("marker", "│")

    top = kwds.get("top", kwds.get("y", 0))
    bottom = kwds.get("bottom", kwds.get("y", 0))
    left = kwds.get("left", kwds.get("x", 0))
    right = kwds.get("right", kwds.get("x", 0))

    indent = len(getattr(step, "counter", (0,))) - 1
    if indent >= getattr(step, "disable", 4):
        return

    ms = [marker] if isinstance(marker, str) else list(marker)
    ms = [m + " " for m in ms]
    ms += [ms[-1]] * (indent - len(ms))
    ws = "".join(reversed(ms[:indent]))

    max_width = max(len(line) for line in lines) + left + right
    lines = [
        ws + (" " * left + line + " " * right).ljust(max_width)
        for line in lines
    ]
    lines = [ws] * top + lines + [ws] * bottom

    print("\n".join(lines))


def printeq(arg, *args):
    lines = [str(arg)]
    lines += [f"= {value!s}" for value in args]
    println(*lines)
