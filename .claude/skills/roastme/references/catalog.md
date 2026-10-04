# Catalog of patterns to roast

The project targets **Python 3.12** (`requires-python = ">=3.12"`), so everything below is
available. Each pattern has: what "before" looks like, what "after" looks like, what to watch out
for and a docs link.

Levels: **basics** (must know), **intermediate** (worth knowing), **advanced** (niche, use with
care).

---

## Loops and collections

### List / set / dict comprehension — basics

```python
# before
names = []
for ship in ships:
    if ship.is_active:
        names.append(ship.name)

# after
names = [ship.name for ship in ships if ship.is_active]
```

Read it out loud: "the ship's name for every ship in ships, if it is active".
Dict: `{ship.id: ship.name for ship in ships}`. Set: `{ship.system for ship in ships}`.

Watch out: only when the loop **builds a collection** and nothing else. Logging, `await`,
mutating other objects, or two `for` clauses + a condition → keep the loop.
📚 https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions

### Generator in `sum` / `min` / `max` / `"".join` — basics

```python
# before
total = 0
for item in cargo:
    total += item.count

# after
total = sum(item.count for item in cargo)
```

No square brackets — there is no need to build a list just to sum it.
`max(ships, key=lambda ship: ship.jump_range)` instead of tracking "the best one" by hand.
📚 https://docs.python.org/3/library/functions.html#max

### `any()` / `all()` — basics

```python
# before
for widget in widgets:
    if widget.is_modified():
        return True
return False

# after
return any(widget.is_modified() for widget in widgets)
```

Stops at the first hit, just like `return` inside the loop.
📚 https://docs.python.org/3/library/functions.html#any

### `next()` with a default — intermediate

```python
# before
found = None
for station in stations:
    if station.name == wanted_name:
        found = station
        break

# after
found = next((station for station in stations if station.name == wanted_name), None)
```

Watch out: with long conditions the loop is often more readable — then keep it.
📚 https://docs.python.org/3/library/functions.html#next

### `enumerate` and `zip(strict=True)` — basics

```python
# before
for i in range(len(events)):
    print(i, events[i])

# after
for index, event in enumerate(events):
    print(index, event)
```

`zip(names, values, strict=True)` raises when the lists differ in length instead of silently
truncating.
📚 https://docs.python.org/3/library/functions.html#zip

### `itertools.pairwise` / `itertools.batched` — intermediate

`pairwise([a, b, c])` → `(a, b), (b, c)` — instead of `zip(items, items[1:])` or indexes.
`batched(items, 3)` (3.12) → chunks of 3 — instead of slicing by hand.
📚 https://docs.python.org/3/library/itertools.html

### Unpacking — basics

```python
first, *rest = parts
system_name, body_name = line.split(":", 1)
```

Instead of `parts[0]`, `parts[1:]`. Watch out: unpacking raises on the wrong number of
elements — usually a feature.

---

## Dictionaries

### `dict.get` / `setdefault` — basics

```python
# before
if key in prices:
    price = prices[key]
else:
    price = 0

# after
price = prices.get(key, 0)
```

Watch out: if the original deliberately raised `KeyError`, `get` changes that.
📚 https://docs.python.org/3/library/stdtypes.html#dict.get

### A dict instead of an `if/elif` chain — basics

```python
# before
if rank == 0:
    label = "Harmless"
elif rank == 1:
    label = "Mostly Harmless"
elif rank == 2:
    label = "Novice"

# after
RANK_LABELS = {0: "Harmless", 1: "Mostly Harmless", 2: "Novice"}
label = RANK_LABELS[rank]
```

Data instead of logic. Works when every branch only returns/assigns a value.

### `collections.defaultdict` / `Counter` — intermediate

```python
# before
by_system = {}
for body in bodies:
    if body.system not in by_system:
        by_system[body.system] = []
    by_system[body.system].append(body)

# after
by_system = defaultdict(list)
for body in bodies:
    by_system[body.system].append(body)
```

Counting occurrences: `Counter(event.type for event in events)`, then `.most_common(3)`.
📚 https://docs.python.org/3/library/collections.html

### Merging dicts with `|` — basics

`settings = defaults | user_settings` instead of `copy()` + `update()`. `d |= other` updates
in place.

---

## Control flow

### Guard clause (early `return`) — basics

```python
# before
def handle(event):
    if event is not None:
        if event.is_valid:
            process(event)

# after
def handle(event):
    if event is None or not event.is_valid:
        return
    process(event)
```

Less indentation, the main path stays on top.

### `match` / `case` — intermediate

```python
# before
if isinstance(event, FSDJump):
    ...
elif isinstance(event, Docked):
    ...

# after
match event:
    case FSDJump(StarSystem=system_name):
        ...
    case Docked():
        ...
```

Best when branching on the **type** or **shape** of data. For a plain comparison against
constants a dict is often simpler.
📚 https://docs.python.org/3/tutorial/controlflow.html#match-statements

### Walrus `:=` — intermediate

```python
# before
match_result = pattern.search(line)
if match_result:
    use(match_result)

# after
if match_result := pattern.search(line):
    use(match_result)
```

Only in simple `if` / `while`. Inside complex expressions it hurts readability.
📚 https://docs.python.org/3/whatsnew/3.8.html#assignment-expressions

### Conditional expression and `or` — basics

`label = name if name else "Unknown"` → `label = name or "Unknown"`.
Watch out: `or` treats `0`, `""`, `[]` as missing. When `0` is a valid value, use
`x if x is not None else default`.

### Chained comparisons and `in` — basics

`if 0 <= volume <= 1:` instead of `volume >= 0 and volume <= 1`.
`if status in ("Docked", "Landed"):` instead of `status == "Docked" or status == "Landed"`.

### `contextlib.suppress` — intermediate

```python
# before
try:
    path.unlink()
except FileNotFoundError:
    pass

# after
with suppress(FileNotFoundError):
    path.unlink()
```

📚 https://docs.python.org/3/library/contextlib.html#contextlib.suppress

---

## Types and classes

### `X | None` and built-in generics — basics

`Optional[str]` → `str | None`, `Union[A, B]` → `A | B`, `List[int]` → `list[int]`,
`typing.Callable` / `typing.AsyncGenerator` → `collections.abc`. Ruff: `UP007`, `UP035`, `UP045`.

### PEP 695 generics — advanced

```python
# before
T = TypeVar("T")
class ValueChanged(Message, Generic[T]): ...

# after
class ValueChanged[T](Message): ...
```

Also `type ShipId = int` instead of `ShipId: TypeAlias = int`. Ruff: `UP046`, `UP040`.
📚 https://docs.python.org/3/whatsnew/3.12.html#pep-695-type-parameter-syntax

### `enum.StrEnum` — basics

`class JournalEventType(str, Enum)` → `class JournalEventType(StrEnum)`. `str(member)` then
returns the value, not `"JournalEventType.X"`. Ruff: `UP042`.

### `typing.Self` and `@override` — intermediate

`def copy(self) -> Self:` instead of the class name in quotes. `@override` (3.12) on an
overriding method — the type checker catches a typo in the name.

### `@dataclass(slots=True, frozen=True)` — intermediate

For plain data objects outside Pydantic. `frozen=True` = immutable, `slots=True` = less memory
and no accidental new attributes.

---

## Files, text, asyncio

### `pathlib` — basics

`Path(dir) / "Journal.log"` instead of `os.path.join`, `path.read_text(encoding="utf-8")` instead
of `open` + `read`, `sorted(directory.glob("Journal*.log"))`.

### f-string with `=` and `removeprefix` / `removesuffix` — basics

`f"{jump_range=}"` → `jump_range=42.1` (quick debugging). `name.removeprefix("$")` instead of
`name[1:] if name.startswith("$") else name`.

### `asyncio.TaskGroup` and `asyncio.timeout` — advanced

`async with asyncio.TaskGroup() as group:` instead of manual `create_task` + `gather` — an error
in one task cancels the rest. `async with asyncio.timeout(5):` instead of `wait_for`.
📚 https://docs.python.org/3/library/asyncio-task.html#task-groups

### `functools.cache` — intermediate

For pure functions called many times with the same arguments. Not for methods that depend on
the object's state.
