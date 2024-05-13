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
"""Contains class and methods for noise models"""


class NoiseModel:
    """Build a noise model based on ``Conditional``, ``Operation`` and ``metadata``.

    Args:
        model (dict[~.NoiseConditional->Union[Operation, Channel]]): Model data for
            the noise model as a ``{Conditional: Noisy_gate}`` dictionary.
        kwargs: Keyword arguments for specifying metadata related to noise model.

    **Example**

    .. code-block:: python

        # Set up the conditions
        c0 = qml.noise.op_eq(qml.PauliX) | qml.noise.op_eq(qml.PauliY)
        c1 = qml.noise.op_eq(qml.Hadamard) & qml.noise.wires_in([0, 1])
        c2 = qml.noise.op_eq(qml.RX)

        @qml.BooleanFn
        def c3(op, **kwargs):
            return isinstance(op, qml.RY) and op.parameters[0] >= 0.5

        # Set up noisy ops
        n0 = qml.noise.partial_wires(qml.AmplitudeDamping, 0.4)

        def n1(op, **kwargs):
            ThermalRelaxationError(0.4, kwargs["t1"], 0.2, 0.6, op.wires)

        def n2(op, **kwargs):
            qml.RX(op.parameters[0] * 0.05, op.wires)

        n3 = qml.noise.partial_wires(qml.PhaseDamping, 0.9)

        # Set up noise model
        noise_model = qml.NoiseModel({c0: n0, c1: n1, c2: n2}, t1=0.04)
        noise_model += {c3: n3}

    >>> noise_model
    NoiseModel({
        OpEq(PauliX) | OpEq(PauliY): AmplitudeDamping(0.4, wires),
        OpEq(Hadamard) & WiresIn([0, 1]): n1,
        OpEq(RX): n2,
        BooleanFn(c3): PhaseDamping(0.9, wires)
    }, t1=0.04)
    """

    def __init__(self, model, **kwargs):
        self._model = model
        self._metadata = kwargs

    @property
    def model(self):
        """Gives the conditional model for the noise model"""
        return self._model

    @property
    def metadata(self):
        """Gives the metadata for the noise model"""
        return self._metadata

    def __add__(self, data):
        if not isinstance(data, NoiseModel):
            return NoiseModel(self._model + data, **self.metadata)

        return NoiseModel(self._model + data._model, **dict(self._metadata + data._metadata))

    def __radd__(self, data):
        return self.__add__(data)

    def __sub__(self, data):
        if not isinstance(data, NoiseModel):
            return NoiseModel(
                {k: v for k, v in self._model.items() if k not in data}, **self.metadata
            )

        return NoiseModel(
            {k: v for k, v in self._model.items() if k not in data._model},
            **dict({k: v for k, v in self._metadata.items() if k not in data._metadata}),
        )
