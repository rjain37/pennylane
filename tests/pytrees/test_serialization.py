import json

import pytest

from pennylane.ops import Hadamard, PauliX, Prod, Sum
from pennylane.pytrees import (
    PyTreeStructure,
    flatten,
    is_pytree,
    leaf,
    list_pytree_types,
    register_pytree,
)
from pennylane.pytrees.serialization import pytree_structure_dump, pytree_structure_load
from pennylane.wires import Wires


class CustomNode:

    def __init__(self, data, metadata):
        self.data = data
        self.metadata = metadata


def flatten_custom(node):
    return (node.data, node.metadata)


def unflatten_custom(data, metadata):
    return CustomNode(data, metadata)


register_pytree(CustomNode, flatten_custom, unflatten_custom, namespace="test")


def test_list_pytree_types():
    """Test for ``list_pytree_types()``."""
    assert list(list_pytree_types("test")) == [CustomNode]


@pytest.mark.parametrize(
    "cls, result",
    [
        (CustomNode, True),
        (list, True),
        (tuple, True),
        (Sum, True),
        (Prod, True),
        (PauliX, True),
        (int, False),
    ],
)
def test_is_pytree(cls, result):
    """Tests for ``is_pytree()``."""
    assert is_pytree(cls) is result


def test_structure_dump():
    _, struct = flatten(
        {
            "list": ["a", 1],
            "dict": {"a": 1},
            "tuple": ("a", 1),
            "custom": CustomNode([1, 5, 7], {"wires": Wires([1, "a", 3.4, None])}),
        }
    )

    assert json.loads(pytree_structure_dump(struct)) == [
        "builtins.dict",
        ["list", "dict", "tuple", "custom"],
        [
            ["builtins.list", None, [None, None]],
            [
                "builtins.dict",
                [
                    "a",
                ],
                [None],
            ],
            ["builtins.tuple", None, [None, None]],
            ["test.CustomNode", {"wires": [1, "a", 3.4, None]}, [None, None, None]],
        ],
    ]


def test_structure_load():
    jsoned = json.dumps(
        [
            "builtins.dict",
            ["list", "dict", "tuple", "custom"],
            [
                ["builtins.list", None, [None, None]],
                [
                    "builtins.dict",
                    [
                        "a",
                    ],
                    [None],
                ],
                ["builtins.tuple", None, [None, None]],
                ["test.CustomNode", {"wires": [1, "a", 3.4, None]}, [None, None, None]],
            ],
        ]
    )

    assert pytree_structure_load(jsoned) == PyTreeStructure(
        dict,
        ["list", "dict", "tuple", "custom"],
        [
            PyTreeStructure(list, None, [leaf, leaf]),
            PyTreeStructure(dict, ["a"], [leaf]),
            PyTreeStructure(tuple, None, [leaf, leaf]),
            PyTreeStructure(CustomNode, {"wires": [1, "a", 3.4, None]}, [leaf, leaf, leaf]),
        ],
    )
