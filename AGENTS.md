# Instructions for Coding Agents

## Working style
- First inspect the repository, its existing conventions, current state, and available hardware/runtime information.
- For a substantial task, provide a short plan before editing.
- Make the smallest useful change that completes the current milestone.
- Prefer a working vertical slice over scaffolding for imagined future features.
- Do not rewrite unrelated files or introduce broad refactors without a clear reason.
- If a requirement is ambiguous and materially affects architecture, ask one concise question. Otherwise state a reasonable assumption and proceed.

## Architecture
- Keep speech recognition, LLM/provider access, speech synthesis, conversation orchestration, and business logic behind small, explicit interfaces.
- Avoid hard-coding one model or provider into the whole application.
- Local-only mode must not contact the network. Do not add silent cloud fallback.
- Make provider choice explicit in configuration and fail clearly if a configured provider is unavailable.
- Use timeouts, bounded retries, cancellation, and safe fallbacks.
- Never claim a business action succeeded until deterministic application code confirms it.
- Prefer standard library and existing dependencies when reasonable. Add a dependency only when it provides clear value.
- Do not add Redis, vector databases, microservices, containers, or orchestration infrastructure without a measured need.

## Privacy and security
- Never commit API keys, tokens, passwords, private audio, or personal caller data.
- Provide an `.env.example` for required environment variables, with placeholders only.
- Do not log secrets or raw audio by default.
- Make cloud use explicit. Document what data is sent to each external provider.
- Validate and constrain model-requested actions before execution.
- Do not use real customer data in tests.

## Model and dependency choices
- Do not assume a model will run acceptably on CPU or within available RAM. Check requirements and benchmark on the target machine.
- Verify current project maintenance, platform compatibility, and licenses before adopting a dependency.
- Check code, model-weight, voice-asset, and dependency licenses separately.
- Prefer MIT, Apache-2.0, or BSD-licensed core components where practical, and document exceptions.
- Treat hosted API free tiers as limited and subject to change. Do not rely on them without checking current terms and quotas.

## Testing and completion
- Add or update focused tests for behavior changed.
- Run relevant tests, linting, formatting, and type checks when configured and feasible.
- Never claim a test passed unless it was actually run and passed.
- Report commands run and their outcomes. Clearly distinguish verified facts from assumptions.
- For performance claims, record hardware, configuration, test sample, and measurement method.
- Keep documentation and example configuration synchronized with the implementation.
- Finish each task with:
  1. What changed.
  2. Files changed.
  3. Tests/commands run and results.
  4. Remaining risks or next step.

## Current project priority
Build and measure the smallest local English voice prototype first. Do not implement later roadmap items until the current milestone is working and reviewed.
