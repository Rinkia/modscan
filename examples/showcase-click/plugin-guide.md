# Plugin Guide

## `click.decorators:confirmation_option`

- **Category:** hook
- **Location:** click.decorators:380
- **Example status:** executed

## How to Extend This

**What it is**

`confirmation_option` is a public function in `click.decorators` (at `click.decorators:380`). It is a hook-style extension point, re-exported from the package's public entry point so you can import it directly from the package.

**When to use it**

Use this hook when your plugin or mod needs to plug into the behavior provided by `confirmation_option`. Because it's re-exported publicly and validated as an importable callable, it is intended to be called directly in your extension code.

**Steps to plug in**

1. Import the function from the package's public entry point.
2. Call `confirmation_option()` — its signature takes no arguments.
3. Apply it as part of your extension code where the hook is expected.

**Notes**

- Signature: `def confirmation_option()` — no parameters are documented.
- Verified as an importable callable, so no additional registration step is stated in the available facts.

### Example

```python
from click.decorators import confirmation_option


@confirmation_option()
def my_command():
    pass
```

## `click.decorators:version_option`

- **Category:** hook
- **Location:** click.decorators:421
- **Example status:** executed

## How to Extend This: `version_option`

### What it is
`version_option` is a public hook function in the `click.decorators` module (`click.decorators:version_option`). It is re-exported from the package's public entry point, so it's part of the officially supported API surface.

### When to use it
Use this extension point when you want to plug into the `version_option` hook to attach version information via a decorator. Because it's re-exported at the package level, you can import and apply it directly in your own code.

### Steps to plug in
1. **Import the hook** from the package's public entry point.
2. **Call `version_option(version)`**, passing the `version` argument as defined by its signature.
3. **Apply it** as part of your extension, then verify your integration by confirming the symbol is an importable callable (its validation method).

### Notes / limits
- The signature is `version_option(version)` — supply the `version` parameter.
- Only the `version` parameter is documented here; no other parameters or behavior are specified in the available facts.

### Example

```python
from click.decorators import version_option


@version_option(version="1.0.0")
def cli():
    pass
```

## `click.types:ParamType`

- **Category:** subclass
- **Location:** click.types:42
- **Example status:** verified

## How to Extend This: Custom Parameter Types with `ParamType`

### What it is

`ParamType` (`click.types:42`) is an abstract base class (inheriting from `abc.ABC`) that defines a custom parameter type. It is a public class, re-exported from the package's public entry point, and is designed to be subclassed.

### When to use it

Use `ParamType` when you need a custom parameter type beyond the built-in ones — for example, to define your own validation or conversion logic for a command's parameters.

### Steps to plug in

1. **Subclass `ParamType`.** Create a class that inherits from `click.types.ParamType` (or the equivalent name from the package's public entry point).
2. **Implement the abstract members.** Because `ParamType` is an ABC, provide concrete implementations for the abstract methods it declares.
3. **Instantiate your subclass.** The extension is validated via subclass instantiation, so create an instance of your custom type for use.

> Note: The specific abstract methods to override and how the instance is wired into a command are not covered by the facts provided here — consult the class definition for the required members.

### Example

```python
from click.types import ParamType


class MyParamType(ParamType):
    def convert(self, value, param, ctx):
        return value


instance = MyParamType()
```

