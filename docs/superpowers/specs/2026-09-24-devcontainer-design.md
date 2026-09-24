# Devcontainer and Compose Environment Design

## Goal

Provide a reproducible Docker Compose development environment for the distributed robot platform, with explicitly selectable GPU and no-GPU stacks. The development container includes Codex CLI and enables bypass permissions only inside that container.

## Requirements

- `docker compose -f compose.gpu.yaml up` starts the all-included GPU-capable stack.
- `docker compose -f compose.no-gpu.yaml up` starts the no-GPU stack.
- The logical development service is named `devcontainer` in both variants.
- Core Flask/mock dependencies are installed in every application image.
- Voice dependencies are isolated from the core image and only installed in the GPU-capable image.
- GPU access uses the NVIDIA Container Toolkit and does not require GPU access for the no-GPU stack.
- Codex credentials are supplied at runtime and are never copied into an image or committed.
- Codex bypass settings are scoped to the container's `CODEX_HOME`, not the host project configuration.
- The repository documentation explains build, start, shell, test, GPU selection, and credential setup.

## Architecture

`compose.gpu.yaml` and `compose.no-gpu.yaml` are independent, selectable Compose files. The GPU file defines the application, mock backends, GPU voice service, and GPU devcontainer. The no-GPU file defines the application, mock backends, and core devcontainer without installing CPU audio dependencies.

The Dockerfiles use a small core Python image for the Flask/mock application and a CUDA aarch64 image for voice development. The GPU devcontainer is based on the Compose-built voice image through a service `additional_contexts` reference, while the no-GPU devcontainer is based on the core image. Both install Node.js and Codex CLI, mount the repository at `/workspace`, and write Codex configuration into a named volume.

## Security

The container may use `approval_policy = "never"` and `sandbox_mode = "danger-full-access"` because the user's requested bypass is constrained to the disposable development container. The Docker socket, host home directory, and host Codex directory are not mounted. API keys are passed through environment variables or an ignored `.env` file at runtime.

## Verification

- Validate both Compose configurations with `docker compose config`.
- Confirm the default config requests an NVIDIA GPU and includes the voice service.
- Confirm the no-GPU config has no GPU device reservation and omits the voice service.
- Build the core and voice images when Docker/GPU support is available.
- Run the existing pytest suite in the default GPU-capable devcontainer when the host can build and run its ARM64 CUDA image.
