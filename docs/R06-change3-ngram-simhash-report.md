# R06 Change 3 — n-gram 与 SimHash 报告

## 总体结果

Change 3 已完成。交付纯字符 n-gram 多重集合 Dice 主相似度、64-bit 稳定 SimHash、Hamming/辅助分数、R03 adapter 的算法级调用，以及合成数据 benchmark。未实现 R05 counts/ratios、有效新增、comparison class、Builder、Store、Replay、sidecar 或任何在线接入。

## Git 基线

- branch: `main...origin/main`
- HEAD/RPD 初始 TID commit: `afc41d8f279e0218d892f7973d3e39b2d86bdf90`
- R05 固定实现基线: `f02209c`
- TID 1.1 Corrective 与 Change 2 的未提交文件在开始时均已核验，且可归属为 Change 2；没有无法归属的 tracked 修改。
- Change 3 仅修改 `ocr_similarity.py`、`tests/test_ocr_similarity.py`，新增 `tests/benchmark_r06_similarity.py` 与本报告；未修改 `ocr_records.py`、R03 或 R04 生产代码。

## 输入与主相似度

算法级 record API 只接受两侧 `normalization_status=completed` 且 `comparison_text` 为 `str`；它直接按 Python Unicode code point 使用已有 comparison text，不进行 NFC/NFKC、lower、空白/标点/UI/数字/短词删除、分词或纠错。

主实现对 n=`(2,3,4)` 以 `Counter` 保存每个 character n-gram occurrence；Counter key 是 code-point tuple，因此保留重复次数而非 set membership。对每个 n：

```text
Dice = 2 * sum(min(left[g], right[g])) / (sum(left.values()) + sum(right.values()))
```

双方无特征的 n 从聚合排除；单侧无特征为 0；其余冻结权重 0.20/0.30/0.50 仅在可用 n 上重新归一化。结果仅为浮点边界夹到 `[0,1]`，不按业务阈值 round。测试包含重复字符/重复短语，证明计数不会退化为 set。

双空返回 1.0，单空返回 0.0；双方非空而所有 n 无特征时，相同短文本为 1.0、不同为 0.0。算法不生成最终 `comparison_class`。

## 长度、R03 与 SimHash

任一输入超过 100,000 code points 时，主分数为 null、warning 为 `comparison_text_too_long`；spy 测试确认该路径没有进入 n-gram Counter。输入不截断且原 R04 证据不变。

算法级 pair signals 复用 Change 2 `compare_r03_exact_hash()`，只读取 persisted R03 hash/version，返回 true/false/null 和固定 warning；没有第二套 hash。

SimHash 使用非空文本的 3-gram occurrence；长度 1—2 使用整个文本 fallback。每个 feature 的 bytes 为 `b"r06-simhash-3gram-v1\\0" + feature.encode("utf-8")`，哈希为 SHA-256 前 8 bytes、big-endian uint64；bit vote 为 1→+1、0→-1，`vote > 0` 才置位。输出为 16 位小写 hex；空文本为 null。Hamming 是 XOR `bit_count()`，辅助分数为 `1 - distance / 64`，且不参与主分数。

Golden: `SimHash("C++") = 09a2fb5099b81c5a`；`abc`/`abd` 的 Hamming distance 为 28、辅助分数为 0.5625。

## 确定性与测试

子进程测试覆盖默认、`PYTHONHASHSEED=1`、`PYTHONHASHSEED=777` 和重复进程；文本含 Unicode、技术符号、重复 n-gram、长度 1 fallback 与长度 2 fallback，输出逐字节一致。

`python -m unittest tests.test_ocr_similarity -v`: PASS，12 tests。测试还覆盖相同/单字变化、前后/中间新增、完全不同、中文/英文/混合、emoji、组合 Unicode、C++/C#/.NET/SLG+X/0-1/2D/3D、空/短/边界文本、非法 config、长度拒绝、R03 adapter 和 reference resolver。

## Benchmark

方法：release interpreter、`perf_counter_ns`、每场景预热 3 次、正式 25 次、inclusive p95；fixture 在计时外构造。每个 pair 同时执行主 n-gram 与 SimHash，峰值通过 `tracemalloc` 测量。

| 场景 | p50 ms | p95 ms | peak KiB | 结果 |
|---|---:|---:|---:|---|
| 20k exact same | 5.94 | 7.14 | 71.96 | ≤15 PASS |
| 20k 50% changed | 9.57 | 10.84 | 81.63 | ≤15 PASS |
| 20k repeated n-gram | 5.17 | 6.72 | 100.51 | ≤15 PASS |
| Unicode pair | 7.61 | 9.68 | 246.47 | observation |
| 100k boundary | 60.32 | 64.33 | 592.38 | bounded |
| 100001 reject | 0.01 | 0.01 | 1.80 | rejected |
| 8 adjacent pure pairs | 12.25 | 14.01 | 31.36 | ≤100 PASS |

所有性能 gate 通过，最大测得峰值 592.38 KiB，小于 16 MiB。没有改变 n、权重、阈值或执行跨 candidate cache。

## 回归、隔离与 Git 状态

- `python -m unittest discover -s tests -q`: PASS，666 tests。
- R04/R05 benchmarks、compileall、pip check 和 `git diff --check` 均通过。
- 未读取正文；`logs/simple_brush.log` 和 `data/ocr_runs` 的 filename/size/mtime/SHA-256 inventory 与 Change 2 结束时一致。
- 未执行 git add、commit、push、tag 或 release。既有未跟踪 `README.md`、`docs/project-review.zip`、`venv-packages-before-reinstall.txt` 保持不变。

## 是否允许进入 Change 4

**允许进入 Change 4，但本聊天框在 Change 3 后停止，等待维护者审阅。**
