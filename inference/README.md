# Optional C++ ONNX CPU smoke runner

This is an optional, independent C++17 boundary for a future exported model. The app uses the Python backend by default. No model, serving API, training pipeline, GPU setup, or performance claim is included.

Install CMake 3.20+, a C++17 compiler, and an official ONNX Runtime CPU release matching your platform from [Microsoft's releases](https://github.com/microsoft/onnxruntime/releases). Keep its `include/` headers and `lib/` native library together.

```sh
cmake -S inference -B inference/build -DONNXRUNTIME_ROOT=/absolute/path/to/onnxruntime
cmake --build inference/build --config Release
inference/build/onnx_runner /absolute/path/to/model.onnx 1,3,224,224
```

Run from the repository root. On multi-configuration generators the executable may be in `inference/build/Release/`. The shared library must remain available to the OS loader; on Linux set `LD_LIBRARY_PATH` to the release's `lib/` directory if required. Use a matching runtime and headers. The current runner targets Linux/macOS paths; Windows wide-character model path handling is future work.

The runner supports exactly one float32 tensor input, checks the supplied dimensions against static model dimensions, bounds input allocation to 100 million elements, and runs zero-valued input on the default CPU provider. It prints output names and sizes for a smoke check. Replace zero input with task-specific preprocessing and validate results before integrating a product endpoint. Real performance comparisons require the chosen model, representative inputs, matching thread counts and runtime options, and measured latency; C++ alone does not establish an optimization.
