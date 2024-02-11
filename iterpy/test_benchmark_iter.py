import inspect
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from iterpy.iter import Iter


@dataclass(frozen=True)
class AnnotatedArgument:
    name: str
    annotation: types.GenericAlias | type | None


def _get_callable_annotated_args(
    method: Callable[[Any], Any],
) -> Sequence[AnnotatedArgument]:
    annotated_args = inspect.get_annotations(method)
    annotated_arguments = [
        AnnotatedArgument(name=arg_name, annotation=annotation)
        for (arg_name, annotation) in annotated_args.items()
        if arg_name not in ("self", "return", "cls")
    ]

    return annotated_arguments


def _populate_values_for_arg(
    arg: AnnotatedArgument,
) -> Any:
    if arg.annotation is int:
        return 0
    if arg.annotation is str:
        return ""

    PREDICATE = "Callable[[~T], bool]"
    MAPPER = "Callable[[~T], ~S]"
    REDUCER = "Callable[[~T, ~T], ~T]"
    HASHER = "Callable[[~T], str]"

    if PREDICATE in str(arg.annotation):
        return lambda x: True  # noqa: ARG005
    if MAPPER in str(arg.annotation):
        return lambda x: x
    if REDUCER in str(arg.annotation):
        return lambda x, y: x  # noqa: ARG005
    if HASHER in str(arg.annotation):
        return lambda x: str(x)

    raise ValueError(f"Unsupported type: {arg.annotation}")


def _annotated_args_to_mapping(
    annotated_args: Sequence[AnnotatedArgument],
) -> Mapping[str, Any]:
    return {
        arg.name: _populate_values_for_arg(arg)
        for arg in annotated_args
    }


@dataclass(frozen=True)
class IterBenchmarkExample:
    iter_items: Sequence[int]
    method: Callable[[Any], Any]
    method_args: Mapping[str, Any] | None

    def call_method(self) -> Any:
        iterator = Iter(self.iter_items)
        if self.method_args:
            return self.method(iterator, **self.method_args)
        return self.method(iterator)


def _is_public(method_name: str) -> bool:
    return not method_name.startswith("_")


def _name_to_callable(
    name: str,
) -> Callable[[Any], Any]:
    return getattr(Iter, name)


def _excluded(
    method: Callable[[Any], Any], excluded_fns: Sequence[str]
) -> bool:
    return any(substring in str(method) for substring in excluded_fns)


def _extract_public_methods_with_default_args(
    iter_benchmark_items: Sequence[Any],
    excluded_methods: Sequence[str],
) -> Sequence[IterBenchmarkExample]:
    # Get all public methods from Iter class
    method_names = dir(Iter)

    public_methods = (
        Iter(method_names)
        .filter(_is_public)
        .map(_name_to_callable)
        .filter(
            lambda method: not _excluded(method, excluded_methods)
        )
    )

    arguments = public_methods.map(_get_callable_annotated_args).map(
        _annotated_args_to_mapping
    )

    combined = Iter(zip(public_methods, arguments, strict=True)).map(
        lambda x: IterBenchmarkExample(
            iter_items=iter_benchmark_items,
            method=x[0],
            method_args=x[1],
        )
    )

    return combined.to_list()


@pytest.mark.parametrize(
    ("example"),
    _extract_public_methods_with_default_args(
        iter_benchmark_items=list(range(1_000)),
        excluded_methods=[
            "pmap"  # pmap requires pickling a lambda, which is not supported
        ],
    ),
)
@pytest.mark.benchmark()
def test_benchmark_iter(
    example: IterBenchmarkExample,
) -> None:
    example.call_method()
