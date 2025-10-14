import pytest

from src.constants import FALSY_STRINGS, TRUTHY_STRINGS, coerce_bool


@pytest.mark.parametrize("value", sorted(TRUTHY_STRINGS))
def test_coerce_bool_truthy_strings(value: str) -> None:
    assert coerce_bool(value) is True
    assert coerce_bool(value.upper()) is True
    assert coerce_bool(f"  {value}  ") is True


@pytest.mark.parametrize("value", [True, 1, 3.14])
def test_coerce_bool_truthy_non_strings(value: object) -> None:
    assert coerce_bool(value) is True


@pytest.mark.parametrize("value", sorted(FALSY_STRINGS))
def test_coerce_bool_falsy_strings(value: str) -> None:
    assert coerce_bool(value, default=True) is False
    assert coerce_bool(value.upper(), default=True) is False
    assert coerce_bool(f"  {value}  ", default=True) is False


class UnstableBool:
    def __init__(self, *, raises: bool) -> None:
        self._raises = raises

    def __bool__(self) -> bool:
        if self._raises:
            raise ValueError("boom")
        return False


@pytest.mark.parametrize("value", [False, 0, 0.0, UnstableBool(raises=False)])
def test_coerce_bool_falsy_non_strings(value: object) -> None:
    assert coerce_bool(value, default=True) is False


@pytest.mark.parametrize(
    "value",
    [None, "", "maybe", UnstableBool(raises=True)],
)
def test_coerce_bool_falls_back_to_default(value: object) -> None:
    assert coerce_bool(value, default=True) is True
    assert coerce_bool(value, default=False) is False
