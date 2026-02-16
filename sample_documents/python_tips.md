# Python Tips and Best Practices

## Virtual Environments

Always use virtual environments to isolate your project dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

This prevents conflicts between different projects that might need different versions of the same package.

## Type Hints

Python 3.5+ supports type hints. They make your code more readable and help catch bugs:

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"

def process_items(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}
```

## List Comprehensions

List comprehensions are more Pythonic and often faster than loops:

```python
# Instead of:
squares = []
for x in range(10):
    squares.append(x ** 2)

# Use:
squares = [x ** 2 for x in range(10)]
```

## Context Managers

Use `with` statements for resource management:

```python
# Files are automatically closed
with open('file.txt', 'r') as f:
    content = f.read()

# Works with database connections, locks, etc.
```

## F-strings

F-strings (Python 3.6+) are the cleanest way to format strings:

```python
name = "Alice"
age = 30
print(f"{name} is {age} years old")
print(f"Next year, {name} will be {age + 1}")
```

## The Walrus Operator

Python 3.8 introduced `:=` for assignment expressions:

```python
# Instead of:
line = input()
while line != "quit":
    print(line)
    line = input()

# Use:
while (line := input()) != "quit":
    print(line)
```

## Dataclasses

For simple data containers, use dataclasses:

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float
    
    def distance_from_origin(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5
```

## Error Handling

Be specific with exceptions:

```python
try:
    value = int(user_input)
except ValueError:
    print("Please enter a valid number")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Useful Standard Library Modules

- `pathlib`: Modern path handling
- `collections`: Specialized container types
- `itertools`: Efficient looping utilities
- `functools`: Higher-order functions
- `typing`: Type hint support
