# Copyright 2018-2024 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the transform ``qml.transform.split_non_commuting`` """
import itertools

import pytest

import pennylane as qml

# Two commuting groups: [[0, 3], [1, 2, 4]]
# Four groups based on wire overlaps: [[0, 2], [1], [3], [4]]
single_term_obs_list = [
    qml.X(0),
    qml.Y(0),
    qml.Z(1),
    qml.X(0) @ qml.Y(1),
    qml.Y(0) @ qml.Z(1),
]

single_term_pauli_groups = [
    [qml.X(0), qml.X(0) @ qml.Y(1)],
    [qml.Y(0), qml.Z(1), qml.Y(0) @ qml.Z(1)],
]

single_term_naive_groups = [
    [qml.X(0), qml.Z(1)],
    [qml.Y(0)],
    [qml.X(0) @ qml.Y(1)],
    [qml.Y(0) @ qml.Z(1)],
]

# contains the following observables: X(0), Y(0), Y(0) @ Z(1), X(1), Z(1), X(0) @ Y(1)
# pauli groups: [[0, 5], [1, 3], [2, 4]]
# naive groups: [[0, 3], [1, 4], [2], [5]]
complex_obs_list = [
    qml.X(0),  # single observable
    0.5 * qml.Y(0),  # scalar product
    qml.X(0) + qml.Y(0) @ qml.Z(1) + 2.0 * qml.X(1) + qml.I(),  # sum
    1.5 * qml.I(),  # identity
    qml.Hamiltonian(
        [0.1, 0.2, 0.3, 0.4], [qml.Z(1), qml.X(0) @ qml.Y(1), qml.Y(0) @ qml.Z(1), qml.I()]
    ),
]

complex_no_grouping_obs = [
    qml.X(0),
    qml.Y(0),
    qml.Y(0) @ qml.Z(1),
    qml.X(1),
    qml.Z(1),
    qml.X(0) @ qml.Y(1),
]


def complex_no_grouping_processing_fn(results):
    """The expected processing function without grouping of complex_obs_list"""

    return (
        results[0],
        0.5 * results[1],
        results[0] + results[2] + 2.0 * results[3] + 1.0,
        1.5,
        0.1 * results[4] + 0.2 * results[5] + 0.3 * results[2] + 0.4,
    )


complex_pauli_groups = [
    [qml.X(0), qml.X(0) @ qml.Y(1)],
    [qml.Y(0), qml.X(1)],
    [qml.Y(0) @ qml.Z(1), qml.Z(1)],
]


def complex_pauli_processing_fn(results):
    """The expected processing function for pauli grouping of complex_obs_list"""
    group0, group1, group2 = results
    return (
        group0[0],
        0.5 * group1[0],
        group0[0] + group2[0] + 2.0 * group1[1] + 1.0,
        1.5,
        0.1 * group2[1] + 0.2 * group0[1] + 0.3 * group2[0] + 0.4,
    )


complex_naive_groups = [
    [qml.X(0), qml.X(1)],
    [qml.Y(0), qml.Z(1)],
    [qml.Y(0) @ qml.Z(1)],
    [qml.X(0) @ qml.Y(1)],
]


def complex_naive_processing_fn(results):
    """The expected processing function for naive grouping of complex_obs_list"""

    group0, group1, group2, group3 = results
    return (
        group0[0],
        0.5 * group1[0],
        group0[0] + group2 + 2.0 * group0[1] + 1.0,
        1.5,
        0.1 * group1[1] + 0.2 * group3 + 0.3 * group2 + 0.4,
    )


with qml.operation.disable_new_opmath_cm():

    # does not contain I(), used to test legacy opmath
    less_complex_obs_list = [
        qml.X(0),  # single observable
        0.5 * qml.Y(0),  # scalar product
        qml.X(0) + qml.Y(0) @ qml.Z(1) + 2.0 * qml.X(1),  # sum
        qml.Hamiltonian([0.1, 0.2, 0.3], [qml.Z(1), qml.X(0) @ qml.Y(1), qml.Y(0) @ qml.Z(1)]),
    ]

    less_complex_no_grouping_obs = [
        qml.X(0),
        qml.Y(0),
        qml.Y(0) @ qml.Z(1),
        qml.X(1),
        qml.Z(1),
        qml.X(0) @ qml.Y(1),
    ]

    less_complex_pauli_groups = [
        [qml.X(0), qml.X(0) @ qml.Y(1)],
        [qml.Y(0), qml.X(1)],
        [qml.Y(0) @ qml.Z(1), qml.Z(1)],
    ]

    less_complex_naive_groups = [
        [qml.X(0), qml.X(1)],
        [qml.Y(0), qml.Z(1)],
        [qml.Y(0) @ qml.Z(1)],
        [qml.X(0) @ qml.Y(1)],
    ]


def less_complex_no_grouping_processing_fn(results):
    """The expected processing function without grouping of less_complex_obs_list"""

    return (
        results[0],
        0.5 * results[1],
        results[0] + results[2] + 2.0 * results[3],
        0.1 * results[4] + 0.2 * results[5] + 0.3 * results[2],
    )


def less_complex_pauli_processing_fn(results):
    """The expected processing function for pauli grouping of less_complex_obs_list"""
    group0, group1, group2 = results
    return (
        group0[0],
        0.5 * group1[0],
        group0[0] + group2[0] + 2.0 * group1[1],
        0.1 * group2[1] + 0.2 * group0[1] + 0.3 * group2[0],
    )


def less_complex_naive_processing_fn(results):
    """The expected processing function for naive grouping of less_complex_obs_list"""

    group0, group1, group2, group3 = results
    return (
        group0[0],
        0.5 * group1[0],
        group0[0] + group2 + 2.0 * group0[1],
        0.1 * group1[1] + 0.2 * group3 + 0.3 * group2,
    )


# Measurements that accept observables as arguments
obs_measurements = [qml.expval, qml.var, qml.probs, qml.counts, qml.sample]

# measurements that accept wires as arguments
wire_measurements = [qml.probs, qml.counts, qml.sample]


class TestUnits:
    """Unit tests for components of the ``split_non_commuting`` transform"""

    @pytest.mark.parametrize("measure_fn", obs_measurements)
    @pytest.mark.parametrize(
        "grouping_strategy, n_tapes", [(None, 5), ("default", 2), ("pauli", 2), ("naive", 4)]
    )
    def test_number_of_tapes(self, measure_fn, grouping_strategy, n_tapes):
        """Tests that the correct number of tapes is returned"""

        measurements = [measure_fn(op=o) for o in single_term_obs_list]
        tape = qml.tape.QuantumScript([qml.X(0), qml.CNOT([0, 1])], measurements, shots=100)
        tapes, _ = qml.transforms.split_non_commuting(tape, grouping_strategy=grouping_strategy)
        assert len(tapes) == n_tapes
        assert all(t.operations == [qml.X(0), qml.CNOT([0, 1])] for t in tapes)
        assert all(t.shots == tape.shots for t in tapes)

    @pytest.mark.parametrize(
        "grouping_strategy, n_tapes", [(None, 5), ("default", 2), ("pauli", 2), ("naive", 4)]
    )
    @pytest.mark.parametrize(
        "make_H",
        [
            lambda obs_list: qml.Hamiltonian([0.1, 0.2, 0.3, 0.4, 0.5], obs_list),
            lambda obs_list: qml.sum(
                *(qml.s_prod(c, o) for c, o in zip([0.1, 0.2, 0.3, 0.4, 0.5], obs_list))
            ),
        ],
    )
    def test_number_of_tapes_single_hamiltonian(self, grouping_strategy, n_tapes, make_H):
        """Tests that the correct number of tapes is returned for a single Hamiltonian"""

        obs_list = (
            [
                qml.operation.Tensor(*o.operands) if isinstance(o, qml.ops.Prod) else o
                for o in single_term_obs_list
            ]
            if not qml.operation.active_new_opmath()
            else single_term_obs_list
        )

        H = make_H(obs_list)
        tape = qml.tape.QuantumScript([qml.X(0), qml.CNOT([0, 1])], [qml.expval(H)], shots=100)
        tapes, _ = qml.transforms.split_non_commuting(tape, grouping_strategy=grouping_strategy)
        assert len(tapes) == n_tapes
        assert all(t.operations == [qml.X(0), qml.CNOT([0, 1])] for t in tapes)
        assert all(t.shots == tape.shots for t in tapes)

    @pytest.mark.parametrize(
        "grouping_strategy, n_tapes", [(None, 6), ("default", 4), ("pauli", 3), ("naive", 4)]
    )
    def test_number_of_tapes_complex_obs(self, grouping_strategy, n_tapes):
        """Tests number of tapes with mixed types of observables"""

        measurements = [qml.expval(o) for o in complex_obs_list]
        tape = qml.tape.QuantumScript([qml.X(0), qml.CNOT([0, 1])], measurements, shots=100)
        tapes, _ = qml.transforms.split_non_commuting(tape, grouping_strategy=grouping_strategy)
        assert len(tapes) == n_tapes
        assert all(t.operations == [qml.X(0), qml.CNOT([0, 1])] for t in tapes)
        assert all(t.shots == tape.shots for t in tapes)

    @pytest.mark.parametrize("grouping_strategy", [None, "default", "pauli", "naive"])
    @pytest.mark.parametrize(
        "make_H",
        [
            lambda obs_list: qml.Hamiltonian([0.1, 0.2, 0.3, 0.4, 0.5], obs_list),
            lambda obs_list: qml.sum(
                *(qml.s_prod(c, o) for c, o in zip([0.1, 0.2, 0.3, 0.4, 0.5], obs_list))
            ),
        ],
    )
    def test_existing_grouping_used_for_single_hamiltonian(self, grouping_strategy, make_H):
        """Tests that if a Hamiltonian has an existing grouping, it is used regardless of
        what is requested through the ``grouping_strategy`` argument."""

        obs_list = (
            [
                qml.operation.Tensor(*o.operands) if isinstance(o, qml.ops.Prod) else o
                for o in single_term_obs_list
            ]
            if not qml.operation.active_new_opmath()
            else single_term_obs_list
        )

        H = make_H(obs_list)
        H.compute_grouping()

        tape = qml.tape.QuantumScript([qml.X(0), qml.CNOT([0, 1])], [qml.expval(H)], shots=100)
        tapes, _ = qml.transforms.split_non_commuting(tape, grouping_strategy=grouping_strategy)
        assert len(tapes) == 2
        assert all(t.operations == [qml.X(0), qml.CNOT([0, 1])] for t in tapes)
        assert all(t.shots == tape.shots for t in tapes)

    @pytest.mark.parametrize("measure_fn", obs_measurements)
    def test_single_group(self, measure_fn):
        """Tests when all measurements can be taken at the same time"""

        with qml.queuing.AnnotatedQueue() as q:
            qml.PauliZ(0)
            qml.Hadamard(0)
            qml.CNOT((0, 1))
            measure_fn(op=qml.X(0))
            measure_fn(op=qml.Y(1))
            measure_fn(op=qml.Z(2))
            measure_fn(op=qml.X(0) @ qml.Y(1))
            measure_fn(op=qml.Y(1) @ qml.Z(2))

        tape = qml.tape.QuantumScript.from_queue(q, shots=100)
        tapes, fn = qml.transforms.split_non_commuting(tape)

        assert len(tapes) == 1
        assert fn([[0.1, 0.2, 0.3, 0.4, 0.5]]) == (0.1, 0.2, 0.3, 0.4, 0.5)

    @pytest.mark.parametrize("measure_fn", wire_measurements)
    def test_all_wire_measurements(self, measure_fn):
        """Tests that measurements based on wires don't need to be split"""

        with qml.queuing.AnnotatedQueue() as q:
            qml.PauliZ(0)
            qml.Hadamard(0)
            qml.CNOT((0, 1))
            measure_fn()
            measure_fn(wires=[0])
            measure_fn(wires=[1])
            measure_fn(wires=[0, 1])
            measure_fn(op=qml.PauliZ(0))
            measure_fn(op=qml.PauliZ(0) @ qml.PauliZ(2))

        tape = qml.tape.QuantumScript.from_queue(q)
        tapes, fn = qml.transforms.split_non_commuting(tape)

        assert len(tapes) == 1
        assert fn([[0.1, 0.2, 0.3, 0.4, 0.5, 0.6]]) == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)

    @pytest.mark.parametrize("obs_meas_1, obs_meas_2", itertools.combinations(obs_measurements, 2))
    @pytest.mark.parametrize(
        "wire_meas_1, wire_meas_2", itertools.combinations(wire_measurements, 2)
    )
    def test_mix_measurement_types(self, obs_meas_1, obs_meas_2, wire_meas_1, wire_meas_2):
        """Tests that tapes mixing different measurement types is handled correctly"""

        with qml.queuing.AnnotatedQueue() as q:
            obs_meas_1(op=qml.PauliX(0))
            obs_meas_2(op=qml.PauliZ(1))
            obs_meas_1(op=qml.PauliZ(0))
            wire_meas_1(wires=[0])
            wire_meas_2(wires=[1])
            wire_meas_1(wires=[0, 1])

        tape = qml.tape.QuantumScript.from_queue(q)
        tapes, _ = qml.transforms.split_non_commuting(tape)
        assert len(tapes) == 2
        assert tapes[0].measurements == [
            obs_meas_1(op=qml.PauliX(0)),
            obs_meas_2(op=qml.PauliZ(1)),
            wire_meas_2(wires=[1]),
        ]
        assert tapes[1].measurements == [
            obs_meas_1(op=qml.PauliZ(0)),
            wire_meas_1(wires=[0]),
            wire_meas_1(wires=[0, 1]),
        ]

    def test_grouping_strategies(self):
        """Tests that the tape is split correctly for different grouping strategies"""

        measurements = [
            qml.expval(c * o) for c, o in zip([0.1, 0.2, 0.3, 0.4, 0.5], single_term_obs_list)
        ]
        tape = qml.tape.QuantumScript([], measurements, shots=100)

        expected_tapes_no_grouping = [
            qml.tape.QuantumScript([], [qml.expval(o)], shots=100) for o in single_term_obs_list
        ]

        # pauli grouping produces [[0, 3], [1, 2, 4]]
        expected_tapes_pauli_grouping = [
            qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
            for group in single_term_pauli_groups
        ]

        # naive grouping produces [[0, 2], [1], [3], [4]]
        expected_tapes_naive_grouping = [
            qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
            for group in single_term_naive_groups
        ]

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy=None)
        for actual_tape, expected_tape in zip(tapes, expected_tapes_no_grouping):
            assert qml.equal(actual_tape, expected_tape)
        assert qml.math.allclose(fn([0.1, 0.2, 0.3, 0.4, 0.5]), [0.01, 0.04, 0.09, 0.16, 0.25])

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy="default")
        # When new opmath is disabled, c * o gives Hamiltonians, which leads to naive grouping
        if qml.operation.active_new_opmath():
            for actual_tape, expected_tape in zip(tapes, expected_tapes_pauli_grouping):
                assert qml.equal(actual_tape, expected_tape)
            assert qml.math.allclose(
                fn([[0.1, 0.2], [0.3, 0.4, 0.5]]), [0.01, 0.06, 0.12, 0.08, 0.25]
            )
        else:
            for actual_tape, expected_tape in zip(tapes, expected_tapes_naive_grouping):
                assert qml.equal(actual_tape, expected_tape)
            assert qml.math.allclose(
                fn([[0.1, 0.2], 0.3, 0.4, 0.5]), [0.01, 0.06, 0.06, 0.16, 0.25]
            )

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy="pauli")
        for actual_tape, expected_tape in zip(tapes, expected_tapes_pauli_grouping):
            assert qml.equal(actual_tape, expected_tape)
        assert qml.math.allclose(fn([[0.1, 0.2], [0.3, 0.4, 0.5]]), [0.01, 0.06, 0.12, 0.08, 0.25])

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy="naive")
        for actual_tape, expected_tape in zip(tapes, expected_tapes_naive_grouping):
            assert qml.equal(actual_tape, expected_tape)
        assert qml.math.allclose(fn([[0.1, 0.2], 0.3, 0.4, 0.5]), [0.01, 0.06, 0.06, 0.16, 0.25])

    @pytest.mark.usefixtures("new_opmath_only")
    @pytest.mark.parametrize(
        "make_H",
        [
            lambda obs_list: qml.Hamiltonian([0.1, 0.2, 0.3, 0.4, 0.5], obs_list),
            lambda obs_list: qml.sum(
                *(qml.s_prod(c, o) for c, o in zip([0.1, 0.2, 0.3, 0.4, 0.5], obs_list))
            ),
        ],
    )
    def test_grouping_strategies_single_hamiltonian(self, make_H):
        """Tests that a single Hamiltonian or Sum is split correctly"""

        expected_tapes_no_grouping = [
            qml.tape.QuantumScript([], [qml.expval(o)], shots=100) for o in single_term_obs_list
        ]

        expected_tapes_pauli_grouping = [
            qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
            for group in single_term_pauli_groups
        ]

        H = make_H(single_term_obs_list)
        tape = qml.tape.QuantumScript([], [qml.expval(H)], shots=100)

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy=None)
        for actual_tape, expected_tape in zip(tapes, expected_tapes_no_grouping):
            assert qml.equal(actual_tape, expected_tape)
        assert qml.math.allclose(fn([0.1, 0.2, 0.3, 0.4, 0.5]), 0.55)

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy="default")
        for actual_tape, expected_tape in zip(tapes, expected_tapes_pauli_grouping):
            assert qml.equal(actual_tape, expected_tape)
        assert qml.math.allclose(fn([[0.1, 0.2], [0.3, 0.4, 0.5]]), 0.52)

    @pytest.mark.usefixtures("legacy_opmath_only")
    def test_grouping_strategies_legacy_hamiltonian(self):
        """Tests that a single legacy Hamiltonian is split correctly"""

        obs_list = [
            qml.operation.Tensor(*o.operands) if isinstance(o, qml.ops.Prod) else o
            for o in single_term_obs_list
        ]
        pauli_groups = [
            [qml.operation.Tensor(*o.operands) if isinstance(o, qml.ops.Prod) else o for o in group]
            for group in single_term_pauli_groups
        ]

        expected_tapes_no_grouping = [
            qml.tape.QuantumScript([], [qml.expval(o)], shots=100) for o in obs_list
        ]

        expected_tapes_pauli_grouping = [
            qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
            for group in pauli_groups
        ]

        H = qml.ops.Hamiltonian([0.1, 0.2, 0.3, 0.4, 0.5], obs_list)
        tape = qml.tape.QuantumScript([], [qml.expval(H)], shots=100)

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy=None)
        for actual_tape, expected_tape in zip(tapes, expected_tapes_no_grouping):
            assert qml.equal(actual_tape, expected_tape)
        assert qml.math.allclose(fn([0.1, 0.2, 0.3, 0.4, 0.5]), 0.55)

        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy="default")
        for actual_tape, expected_tape in zip(tapes, expected_tapes_pauli_grouping):
            assert qml.equal(actual_tape, expected_tape)
        assert qml.math.allclose(fn([[0.1, 0.2], [0.3, 0.4, 0.5]]), 0.52)

    # This test case contains identity on no wires, which is only supported in new opmath
    @pytest.mark.usefixtures("new_opmath_only")
    @pytest.mark.parametrize(
        "grouping_strategy, expected_tapes, processing_fn, mock_results",
        [
            (
                None,
                [
                    qml.tape.QuantumScript([], [qml.expval(o)], shots=100)
                    for o in complex_no_grouping_obs
                ],
                complex_no_grouping_processing_fn,
                [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            ),
            (
                "naive",
                [
                    qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
                    for group in complex_naive_groups
                ],
                complex_naive_processing_fn,
                [[0.1, 0.2], [0.3, 0.4], 0.5, 0.6],
            ),
            (
                "pauli",
                [
                    qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
                    for group in complex_pauli_groups
                ],
                complex_pauli_processing_fn,
                [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
            ),
        ],
    )
    def test_grouping_strategies_complex(
        self, grouping_strategy, expected_tapes, processing_fn, mock_results
    ):
        """Tests that the tape is split correctly when containing more complex observables"""

        measurements = [qml.expval(o) for o in complex_obs_list]
        tape = qml.tape.QuantumScript([], measurements, shots=100)
        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy=grouping_strategy)

        for actual_tape, expected_tape in zip(tapes, expected_tapes):
            assert qml.equal(actual_tape, expected_tape)

        assert qml.math.allclose(fn(mock_results), processing_fn(mock_results))

    @pytest.mark.usefixtures("legacy_opmath_only")
    @pytest.mark.parametrize(
        "grouping_strategy, expected_tapes, processing_fn, mock_results",
        [
            (
                None,
                [
                    qml.tape.QuantumScript([], [qml.expval(o)], shots=100)
                    for o in less_complex_no_grouping_obs
                ],
                less_complex_no_grouping_processing_fn,
                [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            ),
            (
                "naive",
                [
                    qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
                    for group in less_complex_naive_groups
                ],
                less_complex_naive_processing_fn,
                [[0.1, 0.2], [0.3, 0.4], 0.5, 0.6],
            ),
            (
                "pauli",
                [
                    qml.tape.QuantumScript([], [qml.expval(o) for o in group], shots=100)
                    for group in less_complex_pauli_groups
                ],
                less_complex_pauli_processing_fn,
                [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
            ),
        ],
    )
    def test_grouping_strategies_complex_legacy(
        self, grouping_strategy, expected_tapes, processing_fn, mock_results
    ):
        """Tests that the tape is split correctly with legacy opmath"""

        measurements = [qml.expval(o) for o in less_complex_obs_list]
        tape = qml.tape.QuantumScript([], measurements, shots=100)
        tapes, fn = qml.transforms.split_non_commuting(tape, grouping_strategy=grouping_strategy)

        for actual_tape, expected_tape in zip(tapes, expected_tapes):
            assert qml.equal(actual_tape, expected_tape)

        assert qml.math.allclose(fn(mock_results), processing_fn(mock_results))

    @pytest.mark.parametrize("batch_type", (tuple, list))
    def test_batch_of_tapes(self, batch_type):
        """Test that `split_non_commuting` can transform a batch of tapes"""

        tape_batch = batch_type(
            [
                qml.tape.QuantumScript(
                    [qml.RX(1.2, 0)],
                    [qml.expval(qml.X(0)), qml.expval(qml.Y(0)), qml.expval(qml.X(1))],
                ),
                qml.tape.QuantumScript(
                    [qml.RY(0.5, 0)], [qml.expval(qml.Z(0)), qml.expval(qml.Y(0))]
                ),
            ]
        )
        tapes, fn = qml.transforms.split_non_commuting(tape_batch)

        expected_tapes = [
            qml.tape.QuantumScript([qml.RX(1.2, 0)], [qml.expval(qml.X(0)), qml.expval(qml.X(1))]),
            qml.tape.QuantumScript([qml.RX(1.2, 0)], [qml.expval(qml.Y(0))]),
            qml.tape.QuantumScript([qml.RY(0.5, 0)], [qml.expval(qml.Z(0))]),
            qml.tape.QuantumScript([qml.RY(0.5, 0)], [qml.expval(qml.Y(0))]),
        ]
        for actual_tape, expected_tape in zip(tapes, expected_tapes):
            assert qml.equal(actual_tape, expected_tape)

        result = ([0.1, 0.2], 0.2, 0.3, 0.4)
        assert fn(result) == ((0.1, 0.2, 0.2), (0.3, 0.4))


class TestIntegration:
    """Tests the ``split_non_commuting`` transform performed on a QNode"""


class TestDifferentiability:
    """Tests the differentiability of the ``split_non_commuting`` transform"""
