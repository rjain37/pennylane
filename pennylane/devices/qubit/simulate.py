# Copyright 2018-2023 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Simulate a quantum script."""
# pylint: disable=protected-access
from collections import Counter
from typing import Optional

from numpy.random import default_rng
import numpy as np

import pennylane as qml
from pennylane.measurements import (
    CountsMP,
    ExpectationMP,
    ProbabilityMP,
    SampleMP,
    VarianceMP,
)
from pennylane.typing import Result

from .initialize_state import create_initial_state
from .apply_operation import apply_operation
from .measure import measure
from .sampling import measure_with_samples
from ..default_qubit import Conditional, MidMeasureMP


INTERFACE_TO_LIKE = {
    # map interfaces known by autoray to themselves
    None: None,
    "numpy": "numpy",
    "autograd": "autograd",
    "jax": "jax",
    "torch": "torch",
    "tensorflow": "tensorflow",
    # map non-standard interfaces to those known by autoray
    "auto": None,
    "scipy": "numpy",
    "jax-jit": "jax",
    "jax-python": "jax",
    "JAX": "jax",
    "pytorch": "torch",
    "tf": "tensorflow",
    "tensorflow-autograph": "tensorflow",
    "tf-autograph": "tensorflow",
}


class _FlexShots(qml.measurements.Shots):
    """Shots class that allows zero shots."""

    # pylint: disable=super-init-not-called
    def __init__(self, shots=None):
        if isinstance(shots, int):
            self.total_shots = shots
            self.shot_vector = (qml.measurements.ShotCopies(shots, 1),)
        else:
            self.__all_tuple_init__([s if isinstance(s, tuple) else (s, 1) for s in shots])

        self._frozen = True


def _postselection_postprocess(state, is_state_batched, shots):
    """Update state after projector is applied."""
    if is_state_batched:
        raise ValueError(
            "Cannot postselect on circuits with broadcasting. Use the "
            "qml.transforms.broadcast_expand transform to split a broadcasted "
            "tape into multiple non-broadcasted tapes before executing if "
            "postselection is used."
        )

    # The floor function is being used here so that a norm very close to zero becomes exactly
    # equal to zero so that the state can become invalid. This way, execution can continue, and
    # bad postselection gives results that are invalid rather than results that look valid but
    # are incorrect.
    norm = qml.math.norm(state)

    if not qml.math.is_abstract(state) and qml.math.allclose(norm, 0.0):
        norm = 0.0

    if shots:
        # Clip the number of shots using a binomial distribution using the probability of
        # measuring the postselected state.
        postselected_shots = (
            [np.random.binomial(s, float(norm**2)) for s in shots]
            if not qml.math.is_abstract(norm)
            else shots
        )

        # _FlexShots is used here since the binomial distribution could result in zero
        # valid samples
        shots = _FlexShots(postselected_shots)

    state = state / norm
    return state, shots


def get_final_state(circuit, debugger=None, interface=None):
    """
    Get the final state that results from executing the given quantum script.

    This is an internal function that will be called by the successor to ``default.qubit``.

    Args:
        circuit (.QuantumScript): The single circuit to simulate
        debugger (._Debugger): The debugger to use
        interface (str): The machine learning interface to create the initial state with

    Returns:
        Tuple[TensorLike, bool]: A tuple containing the final state of the quantum script and
            whether the state has a batch dimension.

    """
    circuit = circuit.map_to_standard_wires()

    prep = None
    if len(circuit) > 0 and isinstance(circuit[0], qml.operation.StatePrepBase):
        prep = circuit[0]

    state = create_initial_state(sorted(circuit.op_wires), prep, like=INTERFACE_TO_LIKE[interface])

    # initial state is batched only if the state preparation (if it exists) is batched
    is_state_batched = bool(prep and prep.batch_size is not None)
    measurement_values = {}
    for op in circuit.operations[bool(prep) :]:
        if isinstance(op, Conditional):
            meas_id = op.meas_val.measurements[0].hash
            if meas_id not in measurement_values:
                raise KeyError(f"Measurement key {meas_id} not found.")
            if not measurement_values[meas_id]:
                continue
            op = op.then_op
        state = apply_operation(op, state, is_state_batched=is_state_batched, debugger=debugger)
        if isinstance(op, MidMeasureMP):
            state, measurement_values[op.hash] = state
        # Handle postselection on mid-circuit measurements
        if isinstance(op, qml.Projector):
            state, circuit._shots = _postselection_postprocess(
                state, is_state_batched, circuit.shots
            )

        # new state is batched if i) the old state is batched, or ii) the new op adds a batch dim
        is_state_batched = is_state_batched or (op.batch_size is not None)

    for _ in range(len(circuit.wires) - len(circuit.op_wires)):
        # if any measured wires are not operated on, we pad the state with zeros.
        # We know they belong at the end because the circuit is in standard wire-order
        state = qml.math.stack([state, qml.math.zeros_like(state)], axis=-1)

    return state, is_state_batched, measurement_values


def measure_final_state(circuit, state, is_state_batched, rng=None, prng_key=None) -> Result:
    """
    Perform the measurements required by the circuit on the provided state.

    This is an internal function that will be called by the successor to ``default.qubit``.

    Args:
        circuit (.QuantumScript): The single circuit to simulate
        state (TensorLike): The state to perform measurement on
        is_state_batched (bool): Whether the state has a batch dimension or not.
        rng (Union[None, int, array_like[int], SeedSequence, BitGenerator, Generator]): A
            seed-like parameter matching that of ``seed`` for ``numpy.random.default_rng``.
            If no value is provided, a default RNG will be used.
        prng_key (Optional[jax.random.PRNGKey]): An optional ``jax.random.PRNGKey``. This is
            the key to the JAX pseudo random number generator. Only for simulation using JAX.
            If None, the default ``sample_state`` function and a ``numpy.random.default_rng``
            will be for sampling.

    Returns:
        Tuple[TensorLike]: The measurement results
    """

    circuit = circuit.map_to_standard_wires()

    if not circuit.shots:
        # analytic case

        if len(circuit.measurements) == 1:
            return measure(circuit.measurements[0], state, is_state_batched=is_state_batched)

        return tuple(
            measure(mp, state, is_state_batched=is_state_batched) for mp in circuit.measurements
        )

    # finite-shot case

    rng = default_rng(rng)
    results = measure_with_samples(
        circuit.measurements,
        state,
        shots=circuit.shots,
        is_state_batched=is_state_batched,
        rng=rng,
        prng_key=prng_key,
    )

    if len(circuit.measurements) == 1:
        if circuit.shots.has_partitioned_shots:
            return tuple(res[0] for res in results)

        return results[0]

    return results


# pylint: disable=too-many-arguments
def simulate(
    circuit: qml.tape.QuantumScript,
    rng=None,
    prng_key=None,
    debugger=None,
    interface=None,
    state_cache: Optional[dict] = None,
) -> Result:
    """Simulate a single quantum script.

    This is an internal function that will be called by the successor to ``default.qubit``.

    Args:
        circuit (QuantumTape): The single circuit to simulate
        rng (Union[None, int, array_like[int], SeedSequence, BitGenerator, Generator]): A
            seed-like parameter matching that of ``seed`` for ``numpy.random.default_rng``.
            If no value is provided, a default RNG will be used.
        prng_key (Optional[jax.random.PRNGKey]): An optional ``jax.random.PRNGKey``. This is
            the key to the JAX pseudo random number generator. If None, a random key will be
            generated. Only for simulation using JAX.
        debugger (_Debugger): The debugger to use
        interface (str): The machine learning interface to create the initial state with
        state_cache=None (Optional[dict]): A dictionary mapping the hash of a circuit to the pre-rotated state. Used to pass the state between forward passes and vjp calculations.

    Returns:
        tuple(TensorLike): The results of the simulation

    Note that this function can return measurements for non-commuting observables simultaneously.

    This function assumes that all operations provide matrices.

    >>> qs = qml.tape.QuantumScript([qml.RX(1.2, wires=0)], [qml.expval(qml.PauliZ(0)), qml.probs(wires=(0,1))])
    >>> simulate(qs)
    (0.36235775447667357,
    tensor([0.68117888, 0.        , 0.31882112, 0.        ], requires_grad=True))

    """
    has_mcm = has_mid_circuit_measurements(circuit)
    has_shots = circuit.shots.total_shots is not None
    if has_mcm and has_shots:
        tmpcirc = circuit.copy()
        tmpcirc._shots = qml.measurements.Shots(None)
        idx_sample = idx_sampling_measurements(circuit)
        for i in reversed(idx_sample):
            tmpcirc._measurements.pop(i)
        analytic_meas, tmp_dict = simulate_native_mcm(tmpcirc, rng, prng_key, debugger, interface)
        mcm_meas = [tmp_dict]
        for _ in range(circuit.shots.total_shots - 1):
            tmpmeas, tmp_dict = simulate_native_mcm(tmpcirc, rng, prng_key, debugger, interface)
            analytic_meas = [m + t for m, t in zip(analytic_meas, tmpmeas)]
            mcm_meas.append(tmp_dict)
        return gather_native_mid_circuit_measurements(circuit, analytic_meas, mcm_meas)
    state, is_state_batched, _ = get_final_state(circuit, debugger=debugger, interface=interface)
    if state_cache is not None:
        state_cache[circuit.hash] = state
    return measure_final_state(circuit, state, is_state_batched, rng=rng, prng_key=prng_key)


def simulate_native_mcm(
    circuit: qml.tape.QuantumScript,
    rng=None,
    prng_key=None,
    debugger=None,
    interface=None,
) -> Result:
    """Simulate a single quantum script with native mid-circuit measurements.

    Args:
        circuit (QuantumTape): The single circuit to simulate
        rng (Union[None, int, array_like[int], SeedSequence, BitGenerator, Generator]): A
            seed-like parameter matching that of ``seed`` for ``numpy.random.default_rng``.
            If no value is provided, a default RNG will be used.
        prng_key (Optional[jax.random.PRNGKey]): An optional ``jax.random.PRNGKey``. This is
            the key to the JAX pseudo random number generator. If None, a random key will be
            generated. Only for simulation using JAX.
        debugger (_Debugger): The debugger to use
        interface (str): The machine learning interface to create the initial state with

    Returns:
        tuple(TensorLike): The results of the simulation
        dict: The mid-circuit measurement results of the simulation

    """
    has_shots = circuit.shots.total_shots is not None
    if has_shots:
        raise ValueError(
            f"Invalid circuit.shots.total_shots value {circuit.shots.total_shots}; only None is supported."
        )
    state, is_state_batched, mcm_dict = get_final_state(
        circuit, debugger=debugger, interface=interface
    )
    return (
        measure_final_state(circuit, state, is_state_batched, rng=rng, prng_key=prng_key),
        mcm_dict,
    )


def has_mid_circuit_measurements(circuit):
    """Returns True if the circuit contains a MidMeasureMP object and False otherwise."""
    return any(isinstance(op, MidMeasureMP) for op in circuit._ops)


def idx_sampling_measurements(circuit):
    """Returns the indices of sample-like measurements (i.e. CountsMP, SampleMP)."""
    return [
        i
        for i, m in enumerate(circuit.measurements)
        if isinstance(m, (CountsMP, SampleMP, VarianceMP))
    ]


def idx_analytic_measurements(circuit):
    """Returns the indices of non sample-like measurements (i.e. not CountsMP, SampleMP)."""
    return [
        i
        for i, m in enumerate(circuit.measurements)
        if not isinstance(m, (CountsMP, SampleMP, VarianceMP))
    ]


def gather_native_mid_circuit_measurements(circuit, analytic_meas, mcm_meas):
    """Gathers and normalizes the results of native mid-circuit measurement runs."""
    idx_analytic = idx_analytic_measurements(circuit)
    normalized_meas = [None] * len(circuit.measurements)
    for i, m in zip(idx_analytic, analytic_meas):
        if isinstance(circuit.measurements[i], (ExpectationMP, ProbabilityMP)):
            normalized_meas[i] = m / circuit.shots.total_shots
        else:
            raise ValueError(
                f"Native mid-circuit measurement mode does not support {circuit.measurements[i].__class__.__name__} measurements."
            )
    idx_sample = idx_sampling_measurements(circuit)
    if any(isinstance(m, CountsMP) for m in circuit.measurements):
        counter = Counter()
        for d in mcm_meas:
            counter.update(d)
    for i in idx_sample:
        if isinstance(circuit.measurements[i], CountsMP):
            sha = circuit.measurements[i].mv.measurements[0].hash
            normalized_meas[i] = {0: len(mcm_meas) - counter[sha], 1: counter[sha]}
        elif isinstance(circuit.measurements[i], SampleMP):
            sha = circuit.measurements[i].mv.measurements[0].hash
            normalized_meas[i] = np.array([dct[sha] for dct in mcm_meas])
        elif isinstance(circuit.measurements[i], VarianceMP):
            sha = circuit.measurements[i].mv.measurements[0].hash
            normalized_meas[i] = qml.math.var(np.array([dct[sha] for dct in mcm_meas]))
        else:
            raise ValueError(
                f"Native mid-circuit measurement mode does not support {circuit.measurements[i].__class__.__name__} measurements."
            )
    return normalized_meas
