# Devcontainer and Compose Environment Design

## Goal

Provide a reproducible Docker Compose development environment for the distributed robot platform, with a GPU-capable default stack and an explicit no-GPU alternative. The development container includes Codex CLI and enables bypass permissions only inside that container.

## Requirements

- `docker compose up` starts the default all-included GPU-capable stack.
- `docker compose -f compose.yaml -f compose.no-gpu.yaml up` starts the no-GPU stack.
- The logical development service is named `devcontainer` in both variants.
- Core Flask/mock dependencies are installed in every application image.
- Voice dependencies are isolated from the core image and only installed in the GPU-capable image.
- GPU access uses the NVIDIA Container Toolkit and does not require GPU access for the no-GPU stack.
- Codex credentials are supplied at runtime and are never copied into an image or committed.
- Codex bypass settings are scoped to the container's `CODEX_HOME`, not the host project configuration.
- The repository documentation explains build, start, shell, test, GPU selection, and credential setup.

## Architecture

`compose.yaml` is the default GPU/all-included configuration. It defines the application, mock backends, GPU voice service, and `devcontainer`. `compose.no-gpu.yaml` overrides the services that differ for a CPU-only host and disables the voice service rather than installing CPU audio dependencies.

The Dockerfiles use a small core Python image for the Flask/mock application and a CUDA aarch64 image for voice development. The default devcontainer is based on the Compose-built voice image through a service `additional_contexts` reference, installs Node.js and Codex CLI, mounts the repository at `/workspace`, and writes its Codex configuration into a named volume. It therefore includes the GPU/voice dependencies needed to collect the full test suite and requests one NVIDIA GPU. The no-GPU override builds the same logical `devcontainer` service from the core image and resets both the voice build context and GPU reservation.

## Security

The container may use `approval_policy = "never"` and `sandbox_mode = "danger-full-access"` because the user's requested bypass is constrained to the disposable development container. The Docker socket, host home directory, and host Codex directory are not mounted. API keys are passed through environment variables or an ignored `.env` file at runtime.

## Verification

- Validate both Compose configurations with `docker compose config`.
- Confirm the default config requests an NVIDIA GPU and includes the voice service.
- Confirm the no-GPU merged config has no GPU device reservation and omits the voice service.
- Build the core and voice images when Docker/GPU support is available.
- Run the existing pytest suite in the default GPU-capable devcontainer when the host can build and run its ARM64 CUDA image.
