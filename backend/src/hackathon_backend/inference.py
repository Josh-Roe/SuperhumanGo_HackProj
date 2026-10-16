"""Optional CPU ONNX boundary. No model, training, or task-specific API is bundled."""

from importlib.util import find_spec
from pathlib import Path
from typing import Any


class OnnxRunner:
    def __init__(self, model_path: Path | None) -> None:
        self._model_path = model_path
        self._session: Any = None

    @property
    def configured(self) -> bool:
        """Configuration readiness only; it does not certify a model or its outputs."""
        return bool(
            self._model_path
            and self._model_path.is_file()
            and find_spec("onnxruntime") is not None
            and find_spec("numpy") is not None
        )

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run named NumPy-compatible inputs; caller owns preprocessing and output validation."""
        if not self.configured:
            raise RuntimeError("Install the ml extra and configure a local ONNX model first")
        import numpy as np
        import onnxruntime as ort

        if self._session is None:
            self._session = ort.InferenceSession(
                str(self._model_path), providers=["CPUExecutionProvider"]
            )
        expected = {item.name for item in self._session.get_inputs()}
        if set(inputs) != expected:
            raise ValueError("Input names must exactly match the configured model inputs")
        results = self._session.run(None, {key: np.asarray(value) for key, value in inputs.items()})
        return {
            output.name: value
            for output, value in zip(self._session.get_outputs(), results, strict=True)
        }
