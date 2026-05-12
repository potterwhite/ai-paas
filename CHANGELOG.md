# Changelog

## [2.3.0](https://github.com/potterwhite/ai-paas/compare/v2.2.1...v2.3.0) (2026-05-12)


### ✨ Added

* add /download page with yt-dlp NFS support ([c6f2766](https://github.com/potterwhite/ai-paas/commit/c6f276676701d65989239c3e4b9a8323dfbbb104))
* add cookie status UI to webapp ([6eeb17d](https://github.com/potterwhite/ai-paas/commit/6eeb17dfcf60d706fe3cf1d89f5c1ed70a24ccaa))
* add cookie status UI to webapp ([f50e559](https://github.com/potterwhite/ai-paas/commit/f50e559156d2af90ed190ee17c9f7d11a86c3cef))
* add Dockerfile for rag service ([a101381](https://github.com/potterwhite/ai-paas/commit/a10138143ee4dee1732b5d7dc33d709d2e39688e))
* add Gemma 4 26B AWQ download to prepare vllm ([7e7d796](https://github.com/potterwhite/ai-paas/commit/7e7d796e76e85126290ac7748ba00a69a2154c15))
* add init-wiki command to paas-controller.sh ([25cab08](https://github.com/potterwhite/ai-paas/commit/25cab082bd9d5ba495fcd122820a3ce5da37640a))
* add knowledge base UI for Vault RAG ([5fef1fb](https://github.com/potterwhite/ai-paas/commit/5fef1fb2a422a416b0a0af2daccf79fae82897fa))
* add rag service to docker-compose ([4dd1fb7](https://github.com/potterwhite/ai-paas/commit/4dd1fb7d11a1f06c04cb364761f9b397103aff82))
* add refresh spinner + human-friendly time format ([76a4c1d](https://github.com/potterwhite/ai-paas/commit/76a4c1d6b264cf46344534ad6f4f7cebc3d50b63))
* add tree view for media directory selection on download page ([4c288d3](https://github.com/potterwhite/ai-paas/commit/4c288d3e9ba945a6001a4602fe2377cf9d4758a5))
* add wiki batch ingest tool with time-window scheduling ([a1517b0](https://github.com/potterwhite/ai-paas/commit/a1517b00c6ae0283303fd77e56590d2a20471514))
* add Wiki query page to webapp ([363cfad](https://github.com/potterwhite/ai-paas/commit/363cfad05c3864fa9cc3eb23d2f8636846e3d545))
* add wiki runtime config (read-only toggle, model selection) ([5883c35](https://github.com/potterwhite/ai-paas/commit/5883c3530cddc4bffb95056f81e125a54077ecad))
* auto-manage wiki read-only mode during batch ingest ([6b721e3](https://github.com/potterwhite/ai-paas/commit/6b721e3ba3dea77332d2eea60dcce0a4990f593e))
* **comfyui:** add MuseTalk audio lip-sync workflow (07) + fix gitignore ([ab38ec7](https://github.com/potterwhite/ai-paas/commit/ab38ec73bb87653c4a1703ceca9fc93d488348b3))
* **comfyui:** support mp4 video sync and rename default files ([36cf8b6](https://github.com/potterwhite/ai-paas/commit/36cf8b6ec6c47619a5a511dd31a063d9e6b94428))
* **comfyui:** sync workflows on restart + improve I2V workflow ([702ed1a](https://github.com/potterwhite/ai-paas/commit/702ed1a7dcab16394898447c24d13ea3a2b1b6ec))
* complete Phase 1 Vault RAG - query/write APIs, ChromaDB indexing ([fe875bc](https://github.com/potterwhite/ai-paas/commit/fe875bc232d4b961d701968f13dfb0279568d319))
* **controller:** add rebuild-comfyui command + sync MuseTalk descriptions ([dc34e3b](https://github.com/potterwhite/ai-paas/commit/dc34e3bf8120fe5322e39938554fcc336002dd92))
* **controller:** add restart-all command to include profile-gated services ([90b6171](https://github.com/potterwhite/ai-paas/commit/90b6171ab34acbf54e2a418891e1f3e4000819c3))
* **controller:** add start-all and stop-all commands alongside restart-all ([03b2827](https://github.com/potterwhite/ai-paas/commit/03b2827f117b79e07f7b129573e1fc6157418c54))
* expand /download to multi-platform, multi-type with format selection ([2b3966a](https://github.com/potterwhite/ai-paas/commit/2b3966a41fc6585c38f1a170f28644e336ae1ae9))
* implement main.py - FastAPI entry point with /v1/vault/* routes ([fa73d67](https://github.com/potterwhite/ai-paas/commit/fa73d67e600e833fbd3ee8e07594e3e2b9201482))
* implement rag_engine.py - ChromaDB core logic ([97cf149](https://github.com/potterwhite/ai-paas/commit/97cf1497780760ec4908bbf547d8409c0b2dab98))
* implement vault_writer.py - write AI content back to Vault ([68f7140](https://github.com/potterwhite/ai-paas/commit/68f714002528e8f5a6c0fb88fd7244a8388f4334))
* implement Wiki engine for RAG service ([eac8ffb](https://github.com/potterwhite/ai-paas/commit/eac8ffb78b1f3f2f444946647fc22e49e79b96c0))
* improve RAG query quality ([d0c8d49](https://github.com/potterwhite/ai-paas/commit/d0c8d491d8159b97318d1333e9b1fdce75821e31))
* improve wiki error messages with actionable guidance ([897ac73](https://github.com/potterwhite/ai-paas/commit/897ac73f3231c95fadf6bf52388a573a2d1738df))
* integrate wiki-batch into paas-controller ([ead7a16](https://github.com/potterwhite/ai-paas/commit/ead7a16a9d1a6da390eb7b82176578195d7e2d4f))
* make header APP_NAME a clickable home link + document in .env.example ([2d96765](https://github.com/potterwhite/ai-paas/commit/2d96765ec771694891f84430c5508111fd58354d))
* make project name configurable via APP_NAME env var ([38b25f1](https://github.com/potterwhite/ai-paas/commit/38b25f1209d0349015b769b9e854511450159404))
* Phase 2 vault index management ([4c48d37](https://github.com/potterwhite/ai-paas/commit/4c48d3709e94a98f2a7e098f4f8dc6df98f35f29))
* Phase 3 RBAC permissions ([aab3053](https://github.com/potterwhite/ai-paas/commit/aab3053dc8e4d3b3bc91c001dd7eb728a581ec63))
* quantization scripts ([ba17670](https://github.com/potterwhite/ai-paas/commit/ba176707918de66fd776462e27fe344e5568d329))
* recursive dir scan with depth control + manual path input fallback ([81a9b70](https://github.com/potterwhite/ai-paas/commit/81a9b702ba1c8e5e76432ca100036fe4889cf928))
* redesign /download as 3-section smart page with URL probe ([d4a2e3a](https://github.com/potterwhite/ai-paas/commit/d4a2e3a8fb5f1627f432a3c297faf04af550d475))
* replace init-wiki and wiki-batch with unified wiki-vault command ([8fd9eea](https://github.com/potterwhite/ai-paas/commit/8fd9eea1ff86b1cce5a74db8f9fe593a7f06afc4))
* sync wiki config toggle to .env file ([3d3cc6d](https://github.com/potterwhite/ai-paas/commit/3d3cc6da39f0a6ad550895dfa3688cb2f2042ee9))
* **webapp:** implement Whisper AI subtitle generation for /download ([6612390](https://github.com/potterwhite/ai-paas/commit/6612390eb1a925d3964c0bb4cc46e89e298370fe))
* **webapp:** replace static dir scan with lazy-load tree for /download ([2f8d606](https://github.com/potterwhite/ai-paas/commit/2f8d606cee24c8b294cb222eb836e3c5cf291cdf))


### 🐛 Fixed

* always ask all interactive questions with defaults ([1be8a1f](https://github.com/potterwhite/ai-paas/commit/1be8a1fb966149601f197ec66842a331e1b75984))
* always resume model download, skip confirmation ([f841bd3](https://github.com/potterwhite/ai-paas/commit/f841bd3812f65009bc2b21224f341bb2e0c7c593))
* auto-restart vLLM on reboot and fix wiki read-only detection ([f24a2ed](https://github.com/potterwhite/ai-paas/commit/f24a2ed5b3f8d006b626419c0c4cddb26d46be89))
* auto-resume incomplete model downloads ([10850cd](https://github.com/potterwhite/ai-paas/commit/10850cd24198d66f51c0164a23d57e54c249fd9a))
* check-deps verify VAULT_PATH and MEDIA_ROOT exist ([10a63df](https://github.com/potterwhite/ai-paas/commit/10a63df001780092a539b3a3b43e040c7c360cf2))
* comfyUI 5 workflow ([6056236](https://github.com/potterwhite/ai-paas/commit/60562369c2d1bd01009a70c3b5033b6e7d71dc20))
* **comfyui:** add MuseTalk Python 3.13 dependency install logic ([be85d50](https://github.com/potterwhite/ai-paas/commit/be85d5049bfb4125054360232f7156c89cd5c510))
* **comfyui:** auto-resize image to 720x480 and bundle default image for CogVideoX I2V workflow ([6349616](https://github.com/potterwhite/ai-paas/commit/6349616cd88652c11407ac20b45df2859b0d81d8))
* **comfyui:** connect CogVideoImageEncode to image_cond_latents not samples ([d9d8dac](https://github.com/potterwhite/ai-paas/commit/d9d8dacb04fdb26af659490b75002565d51514c2))
* **comfyui:** correct AdvancedLivePortrait input name motion_images → driving_images ([50e9dcf](https://github.com/potterwhite/ai-paas/commit/50e9dcfa629f5ca0e2310e0ddac7148646aa2b01))
* **comfyui:** fix 06 expression workflow for out-of-box use ([f7234e2](https://github.com/potterwhite/ai-paas/commit/f7234e2f380fe58f7b60899e57caf01491dc769a))
* **comfyui:** replace ImageResizeKJ with built-in ImageScale node ([835fd34](https://github.com/potterwhite/ai-paas/commit/835fd34eec004594fe7b8e7d7259088b7caa2eda))
* detect only new files after yt-dlp download, not pre-existing ones ([bf71208](https://github.com/potterwhite/ai-paas/commit/bf712089f970cb8222e40924306fbe6ce51d5440))
* export HF_TOKEN for huggingface-cli download ([0d2477e](https://github.com/potterwhite/ai-paas/commit/0d2477ed8ef895ab371519493b8f1e789ea0aae2))
* handle filename collisions in wiki page writes ([586a18a](https://github.com/potterwhite/ai-paas/commit/586a18a62b7e274c5ef9f046617da29df450af7e))
* handle unclosed LLM code blocks and meta file lint ([4cb59cb](https://github.com/potterwhite/ai-paas/commit/4cb59cb1b54a2bab17b901e5592b39c62b779214))
* improve download page UX — progress bar, transcribe toggle, log visibility ([7b2bfab](https://github.com/potterwhite/ai-paas/commit/7b2bfab9effe2a50d3197c646728d7528564f3b6))
* improve wiki query accuracy with path-aware index ([24547b8](https://github.com/potterwhite/ai-paas/commit/24547b8c7498bc9b66edfa737fbd652aa5ca9765))
* improve wiki-vault interactive UX ([3d8190b](https://github.com/potterwhite/ai-paas/commit/3d8190b55191cea63dd858eacd9d9e11656512cc))
* improve wiki-vault prompts with current time and custom path option ([a7b42c1](https://github.com/potterwhite/ai-paas/commit/a7b42c183d8791af2cbdc4bc480ae1a910f1c9f3))
* isolate PermissionError per dir in media-dirs scan, add tree-style display ([1e20c26](https://github.com/potterwhite/ai-paas/commit/1e20c26d71234d88adf70cb85d40c80d27e079f2))
* register model ID itself in MODEL_ALIASES ([00cd95b](https://github.com/potterwhite/ai-paas/commit/00cd95b67f1192c721baa4de4a32b29f926f1d1c))
* tune Gemma 4 vLLM config for 24GB VRAM ([aa1b1f1](https://github.com/potterwhite/ai-paas/commit/aa1b1f1c738d528e49f74b94a8d4344f5fd18e23))
* tune vLLM VRAM config and make wiki max_tokens configurable ([409375f](https://github.com/potterwhite/ai-paas/commit/409375f5bd77b28795e82eb6c6d6866813516c21))
* update vLLM to 0.20.1 and add --max-num-batched-tokens for Gemma 4 ([674001c](https://github.com/potterwhite/ai-paas/commit/674001cff4b1574205a07485d34e08f7ff9345db))
* update wiki page count in index.md on ingest ([aad94ea](https://github.com/potterwhite/ai-paas/commit/aad94ea07dd1d2541a4b30b9d7de6ffd7ea85fa4))
* update workflow 05 AdvancedLivePortrait param names to match plugin API ([6059a6f](https://github.com/potterwhite/ai-paas/commit/6059a6ffc231f9d56da3de7598650f1961271fcb))
* use git clone for model download (reliable resume) ([59ef631](https://github.com/potterwhite/ai-paas/commit/59ef631f375639a349e4f112e28872f7d9c2116c))
* use same folder icon for all directories in tree view ([86f5766](https://github.com/potterwhite/ai-paas/commit/86f576633963d1422cd2761caa32bc36df14b17e))
* use VAULT_PATH env var in docker-compose ([a6ce899](https://github.com/potterwhite/ai-paas/commit/a6ce899dd0d72474ce51e3ac35ec8e5d7463af75))

## [2.2.1](https://github.com/potterwhite/ai-paas/compare/v2.2.0...v2.2.1) (2026-04-14)


### 🐛 Fixed

* resolve cookie-manager build and runtime failures ([#12](https://github.com/potterwhite/ai-paas/issues/12)) ([27e12e1](https://github.com/potterwhite/ai-paas/commit/27e12e184def5a5895637b3c213b5e8fb3ed96f8))

## [2.2.0](https://github.com/potterwhite/ai-paas/compare/v2.1.1...v2.2.0) (2026-04-14)


### ✨ Added

* add yt-dlp cookie auto-renewal + fix CogVideoX latent format ([#10](https://github.com/potterwhite/ai-paas/issues/10)) ([6d0940a](https://github.com/potterwhite/ai-paas/commit/6d0940aff5190fc4284187a0d580ce28d6e322e8))

## [2.1.1](https://github.com/potterwhite/ai-paas/compare/v2.1.0...v2.1.1) (2026-04-13)


### 🐛 Fixed

* resolve ComfyUI workflow import errors + improve download UX ([#8](https://github.com/potterwhite/ai-paas/issues/8)) ([363bf3d](https://github.com/potterwhite/ai-paas/commit/363bf3d7e335a2d5bcaddf0335157a58199e34bd))

## [2.1.0](https://github.com/potterwhite/ai-paas/compare/v2.0.0...v2.1.0) (2026-04-12)


### ✨ Added

* add ComfyUI workflow browser ([5253a9f](https://github.com/potterwhite/ai-paas/commit/5253a9f343b7be19431d3e56bcf2461d8ffc9b26))
* add ComfyUI workflow browser — discover and download all 6 built-in workflows ([795c48c](https://github.com/potterwhite/ai-paas/commit/795c48c1d378627d7193744ed0c8894893d96d0f))

## [2.0.0](https://github.com/potterwhite/ai-paas/compare/v1.0.0...v2.0.0) (2026-04-12)


### ⚠ BREAKING CHANGES

* squashed full development history (Phase 1–4.7) into single initial commit.

### ✨ Added

* initial release — AI-PaaS private GPU compute platform v1.0.0 ([036ba70](https://github.com/potterwhite/ai-paas/commit/036ba7057d4d2c350c37ef394fc13e0f543f140b))


### 🐛 Fixed

* add license header to .bash file; exclude Dockerfile and .github from CI check ([6143a01](https://github.com/potterwhite/ai-paas/commit/6143a01a9a4d19fcc7a37ff1a36b9a7deeeb927d))
* add license header to .bash file; exclude Dockerfile and .github from CI check ([6143a01](https://github.com/potterwhite/ai-paas/commit/6143a01a9a4d19fcc7a37ff1a36b9a7deeeb927d))
* add license header to .bash file; exclude Dockerfile and .github from CI check ([d9bc62b](https://github.com/potterwhite/ai-paas/commit/d9bc62be7897a945bdec721d4f416014451d5668))
* use recursive glob patterns in license-check CI to match subdirectory files ([c136575](https://github.com/potterwhite/ai-paas/commit/c136575ecde81439954105e22118bad5e0a87848))
