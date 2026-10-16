// Optional CPU smoke runner: one float32 input, explicit positive dimensions, zero input.
// Task-specific preprocessing and a serving API must be added after the model is chosen.
#include <onnxruntime_cxx_api.h>

#include <cstdint>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char* argv[]) {
    try {
        if (argc != 3) {
            std::cerr << "Usage: onnx_runner model.onnx 1,3,224,224\n";
            return 2;
        }
        std::vector<int64_t> shape;
        std::stringstream dimensions(argv[2]);
        std::string dimension;
        size_t elements = 1;
        while (std::getline(dimensions, dimension, ',')) {
            size_t consumed = 0;
            const auto value = std::stoll(dimension, &consumed);
            if (consumed != dimension.size() || value < 1 ||
                static_cast<uint64_t>(value) > 100000000 / elements) {
                throw std::invalid_argument("Dimensions must be positive; limit 100M elements");
            }
            elements *= static_cast<size_t>(value);
            shape.push_back(value);
        }
        if (shape.empty() || std::string(argv[2]).back() == ',') {
            throw std::invalid_argument("Supply comma-separated positive dimensions");
        }

        Ort::Env environment(ORT_LOGGING_LEVEL_WARNING, "hackathon-onnx");
        Ort::SessionOptions options;
        options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        Ort::Session session(environment, argv[1], options);
        if (session.GetInputCount() != 1) {
            throw std::invalid_argument("Smoke runner supports exactly one input");
        }
        const auto input_type = session.GetInputTypeInfo(0);
        const auto input_info = input_type.GetTensorTypeAndShapeInfo();
        if (input_info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) {
            throw std::invalid_argument("Smoke runner requires a float32 tensor input");
        }
        const auto model_shape = input_info.GetShape();
        if (model_shape.size() != shape.size()) {
            throw std::invalid_argument("Input rank does not match the model");
        }
        for (size_t i = 0; i < shape.size(); ++i) {
            if (model_shape[i] >= 0 && model_shape[i] != shape[i]) {
                throw std::invalid_argument("Input dimensions do not match the model");
            }
        }
        Ort::AllocatorWithDefaultOptions allocator;
        const auto input_name = session.GetInputNameAllocated(0, allocator);
        const char* input_names[] = {input_name.get()};
        std::vector<Ort::AllocatedStringPtr> output_name_storage;
        std::vector<const char*> output_names;
        for (size_t i = 0; i < session.GetOutputCount(); ++i) {
            output_name_storage.push_back(session.GetOutputNameAllocated(i, allocator));
            output_names.push_back(output_name_storage.back().get());
        }
        std::vector<float> input(elements, 0.0F);
        auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
        auto tensor = Ort::Value::CreateTensor<float>(
            memory, input.data(), input.size(), shape.data(), shape.size());
        auto outputs = session.Run(Ort::RunOptions{nullptr}, input_names, &tensor, 1,
                                   output_names.data(), output_names.size());
        std::cout << "CPU smoke inference completed: " << outputs.size() << " output(s)\n";
        for (size_t i = 0; i < outputs.size(); ++i) {
            std::cout << output_names[i] << ": ";
            if (outputs[i].IsTensor()) {
                std::cout << outputs[i].GetTensorTypeAndShapeInfo().GetElementCount()
                          << " tensor elements\n";
            } else {
                std::cout << "non-tensor output\n";
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Inference failed: " << error.what() << '\n';
        return 1;
    }
}
