# NEED_TO_DO — Archived Session: Apr02.2026

> Archived from active NEED_TO_DO.md on 2026-04-05.
> All items below were completed during this session.

---

## Apr02.2026 — Disk cleanup, Model Manager UI, 32B AWQ upgrade

- [x] 磁盘清理：删除冗余模型文件，释放 20 GB（cogvideox5b HF 子目录 11GB + t5xxl HF 子目录 8.9GB + qwen2.5-1.5b 1.6GB）
      ✅ 已完成：models/ 46GB → 26GB，磁盘使用率 67% → 56%，可用空间 64GB → 84GB
      commit: `8b5cf46`

- [x] 选择「模型管理 UI」方案并实施，实现手动下载 HuggingFace 模型的界面
      ✅ 已完成：扩展现有 webapp，新增 /models 页面（方案1）；API: /api/models/list /download /progress /switch
      commit: `cad9916` / `122e2df`

- [x] 升级 LLM 到 Qwen2.5-32B-Instruct-AWQ（~19GB，全 GPU，约 12-15 tok/s）
      ✅ 已完成 2026-04-02：通过 /models 页面下载（19GB 5 shards）；docker-compose.yml + litellm_config.yaml 已更新；
         gpu_memory_utilization 0.7 → 0.95；max_model_len 16384 → 10800；ai_vllm 已重建加载 32B；
         ⚠️ context 窗口从 16384 降至 10800；⚠️ Whisper 现在不可与 32B 同时运行
      commit: `29fd9f6` / `202e06f` / `ab79c12`

---

## Mar31.2026 — WebUI 可用性

- [x] 我何时能够看见那个webui呢（没有webui我要如何使用这些服务呢）？我配的whisper/llm等
      ✅ Phase 2 webapp /models 页面已上线
