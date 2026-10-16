# Model artifacts

Place a team-trained/exported `.onnx` model here when one exists. Model binaries are ignored by Git. Record the source, license, preprocessing, input/output names and shapes, validation metrics, and checksum in the relevant model handoff.

Compose mounts this directory read-only at `/models`. Enable `INSTALL_ML=true` and set `ONNX_MODEL_PATH=/models/your-model.onnx` to load it with the optional Python CPU runtime. The C++ path is documented under `inference/`.

No trained model or claimed performance result is included in this scaffold.
