# Copyright 2023 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
r"""
.. currentmodule:: pennylane

This module provides support for hybrid quantum-classical compilation.
Through the use of the :func:`~.qjit` decorator, entire workflows
can be just-in-time (JIT) compiled --- including both quantum and
classical processing --- down to a machine binary on first
function execution. Subsequent calls to the compiled function will execute
the previously compiled binary, resulting in significant
performance improvements.

Currently, PennyLane supports the
`Catalyst <https://github.com/pennylaneai/catalyst>`__ hybrid compiler
with the :func:`~.qjit` decorator. A significant benefit of Catalyst
is the ability to preserve complex control flow around quantum
operations — such as if statements and for loops, and including measurement
feedback — during compilation, while continuing to support end-to-end
autodifferentiation.

.. note::

    Catalyst currently only supports the JAX interface of PennyLane.

Overview
--------

The main entry point to hybrid compilation in PennyLane
is via the qjit decorator.

.. autosummary::
    :toctree: api

    ~qjit

In addition, several developer functions are available to probe
available hybrid compilers.

.. autosummary::
    :toctree: api

    ~compiler.available_compilers
    ~compiler.available
    ~compiler.active_compiler
    ~compiler.active

Compiler
--------

The compiler module provides the infrastructure to integrate external
hybrid quantum-classical compilers with PennyLane, but does not provide
a built-in compiler.

Currently, only the `Catalyst <https://github.com/pennylaneai/catalyst>`__
hybrid compiler is supported with PennyLane, however there are plans
to incorporate additional compilers in the near future.

.. note::

    Catalyst is officially supported on Linux (x86_64) and macOS (aarch64) platforms.
    To install it, simply run the following ``pip`` command:

    .. code-block:: console

      pip install pennylane-catalyst

    Please see the :doc:`installation <catalyst:dev/installation>`
    guide for more information.

Basic usage
-----------

.. note::

    Catalyst supports compiling QNodes that use ``lightning.qubit``,
    ``lightning.kokkos``, ``braket.local.qubit``, and ``braket.aws.qubit``
    devices. It does not support ``default.qubit``.

    Please see the :doc:`Catalyst documentation <catalyst:index>` for more details on supported
    devices, operations, and measurements.

When using just-in-time (JIT) compilation, the compilation is triggered at the call site the
first time the quantum function is executed. For example, ``circuit`` is
compiled as early as the first call.

.. code-block:: python

    dev = qml.device("lightning.qubit", wires=2)

    @qjit
    @qml.qnode(dev)
    def circuit(theta):
        qml.Hadamard(wires=0)
        qml.RX(theta, wires=1)
        qml.CNOT(wires=[0,1])
        return qml.expval(qml.PauliZ(wires=1))

>>> circuit(0.5)  # the first call, compilation occurs here
array(0.)
>>> circuit(0.5)  # the precompiled quantum function is called
array(0.)

Alternatively, if argument type hints are provided, compilation
can occur 'ahead of time' when the function is decorated.

.. code-block:: python

    from jax.core import ShapedArray

    @qml.qjit  # compilation happens at definition
    @qml.qnode(dev)
    def circuit(x: complex, z: ShapedArray(shape=(3,), dtype=jnp.float64)):
        theta = jnp.abs(x)
        qml.RY(theta, wires=0)
        qml.Rot(z[0], z[1], z[2], wires=0)
        return qml.state()

>>> circuit(0.2j, jnp.array([0.3, 0.6, 0.9]))  # calls precompiled function
array([0.75634905-0.52801002j, 0. +0.j,
    0.35962678+0.14074839j, 0. +0.j])

The Catalyst compiler also supports capturing imperative Python control flow
in compiled programs, resulting in control flow being interpreted at runtime
rather than in Python at compile time. You can enable this feature via the
``autograph=True`` keyword argument.

.. code-block:: python

    @qml.qjit(autograph=True)
    @qml.qnode(dev)
    def circuit(x: int):

        if x < 5:
            qml.Hadamard(wires=0)
        else:
            qml.T(wires=0)

        return qml.expval(qml.PauliZ(0))

>>> circuit(3)
array(0.)
>>> circuit(5)
array(1.)

Note that AutoGraph results in additional
restrictions, in particular whenever global state is involved. Please refer to the
:doc:`AutoGraph guide <catalyst:dev/autograph>`
for a complete discussion of the supported and unsupported use-cases.

For more details on using the :func:`~.qjit` decorator and Catalyst
with PennyLane, please refer to the Catalyst
:doc:`quickstart guide <catalyst:dev/quick_start>`,
as well as the :doc:`sharp bits and debugging tips <catalyst:dev/sharp_bits>`
page for an overview of the differences between Catalyst and PennyLane, and
how to best structure your workflows to improve performance when
using Catalyst.

Adding a compiler
-----------------

For any compiler packages seeking to be registered, it is imperative that they
expose the ``entry_points`` metadata under the designated group name
``pennylane.compilers``, with the following entry points:

- ``context``: Path to the compilation evaluation context manager.
  This context manager should have the method ``context.is_tracing()``,
  which returns ``True`` if called within a program that is being traced
  or captured.

- ``ops``: Path to the compiler operations module. This operations module
  may contain compiler specific versions of PennyLane operations,
  for example :func:`~.cond`, :func:`~.measure`, and :func:`~.adjoint`.
  Within a JIT context, PennyLane operations may dispatch to these functions.

- ``qjit``: Path to the JIT decorator provided by the compiler.
  This decorator should have the signature ``qjit(fn, *args, **kwargs)``,
  where ``fn`` is the function to be compiled.

In order to support applying the ``qjit`` decorator with and without arguments,

.. code-block:: python

    @qml.qjit
    def function(x, y):
        ...

    @qml.qjit(verbose=True, additional_args, ...)
    def function(x, y):
        ...

you should ensure that the ``qjit`` decorator itself returns a decorator
if no function is provided:

.. code-block:: python

    def qjit(fn=None, **kwargs):
        if fn is not None:
            return compile_fn(fn, **kwargs)

        def wrapper_fn(fn):
            return compile_fn(fn, **kwargs)

        return wrapper_fn

"""

from .compiler import available_compilers, available, active_compiler, active

from .qjit_api import qjit
