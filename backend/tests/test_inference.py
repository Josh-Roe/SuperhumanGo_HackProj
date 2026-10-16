import pytest

from hackathon_backend.inference import OnnxRunner


def test_missing_model_fails_with_actionable_error(tmp_path):
    for model_path in (None, tmp_path / "missing.onnx"):
        runner = OnnxRunner(model_path)
        assert not runner.configured
        with pytest.raises(RuntimeError, match="Install the ml extra"):
            runner.run({})


def test_optional_cpu_onnx_boundary(tmp_path):
    np = pytest.importorskip("numpy", reason="Install the ml extra for CPU inference tests")
    pytest.importorskip("onnxruntime", reason="Install the ml extra for CPU inference tests")
    # Tiny serialized ONNX Identity graph: float32 x[1,2] -> y[1,2], opset 21, IR 10.
    # Test fixture only; no trained model is included in the product.
    identity = bytes.fromhex(
        "080a3a430a100a017812017922084964656e746974791205736d6f6b655a130a0178"
        "120e0a0c080112080a0208010a02080262130a0179120e0a0c080112080a020801"
        "0a02080242040a001015"
    )
    model_path = tmp_path / "identity.onnx"
    model_path.write_bytes(identity)
    runner = OnnxRunner(model_path)
    assert runner.configured
    inputs = np.array([[3.0, 7.0]], dtype=np.float32)
    np.testing.assert_array_equal(runner.run({"x": inputs})["y"], inputs)
    with pytest.raises(ValueError, match="Input names"):
        runner.run({"unknown": inputs})
