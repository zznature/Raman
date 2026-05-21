# Autofocus 算法与实现说明

本文档说明 `raman/autofocus/` 模块的单点自动对焦算法、核心参数和代码结构。该模块不直接依赖相机 SDK、位移台 SDK 或 GUI，而是通过 `FrameProvider`、`ZStage`、`FocusStrategy` 三个协议接口接入外部硬件或测试替身。

## 目标

自动对焦的目标是在给定 Z 轴安全范围内，找到使图像 ROI 最清晰的 Z 位置。实现采用两阶段扫描：

1. 粗扫描：在当前位置附近用较大步长搜索大致峰值。
2. 细扫描：以粗扫描峰值为中心，用较小步长搜索精确峰值。
3. 亚步长估计：在细扫描峰值附近做三点抛物线插值，得到比扫描步长更细的 `z_best_um`。
4. 回程间隙补偿：最终移动先到目标点下方，再从同一方向接近目标点，减小机械 backlash 对重复定位的影响。

## 数据模型

主要模型定义在 `raman/autofocus/models.py`。

`ROI`

表示图像中的矩形感兴趣区域，坐标原点在图像左上角，`x` 向右，`y` 向下。对焦评分只在 ROI 内计算，因此 ROI 应覆盖有纹理、边缘或颗粒结构的区域，避免纯背景、过曝区域和明显运动区域。

`Frame`

表示一帧图像，包含：

- `image`: 2D 灰度图或 3D RGB/RGBA 图像。
- `timestamp`: 单调时钟时间戳。
- `seq`: 单调递增的帧编号。

`AutofocusParams`

控制扫描范围、步长、采样数量、超时和质量阈值。默认值包括：

- `coarse_range_um = 80.0`
- `coarse_step_um = 10.0`
- `fine_range_um = 15.0`
- `fine_step_um = 2.0`
- `frames_per_z = 3`
- `backlash_um = 3.0`
- `min_confidence = 0.2`
- `max_saturation_ratio = 0.01`
- `metric_name = "tenengrad"`

`FocusPoint`

表示某个 Z 位置的一次评分结果：

- `z_um`: Z 坐标。
- `score`: 清晰度评分。
- `saturation_ratio`: ROI 内低于低阈值或高于高阈值的饱和像素比例。

`ScanCurve`

保存一次粗扫描或细扫描的所有 `FocusPoint`。`best()` 返回评分最高的采样点。

`FocusResult`

保存最终状态、最佳 Z、最终验证分数、置信度、粗扫描曲线、细扫描曲线和错误消息。

## 图像预处理

预处理函数在 `raman/autofocus/roi.py`。

评分前会先执行：

1. `crop(image, roi)`: 截取 ROI，并检查 ROI 是否落在图像范围内。
2. `to_grayscale(image)`: 如果是 RGB/RGBA，按 ITU-R BT.601 权重转为灰度：

   `gray = 0.299 R + 0.587 G + 0.114 B`

3. `prepare(image, roi, blur=False)`: 裁剪、灰度化，并转为 `float32`。

模块中提供了 `gaussian_blur()`，但当前清晰度指标调用 `prepare(..., blur=False)`，默认不模糊。

饱和比例由 `saturation_ratio()` 计算。对 `uint8` 图像，像素值 `<= 2` 或 `>= 253` 被视为欠曝或过曝；对浮点图像使用对应的归一化阈值。

## 清晰度指标

清晰度评分定义在 `raman/autofocus/metrics.py`。所有指标都是“越大越清晰”。

`tenengrad`

默认指标。对 ROI 灰度图计算 Sobel 梯度：

`score = mean(Gx^2 + Gy^2)`

边缘越锐利，梯度能量越大，评分越高。该指标对显微图像的边缘和颗粒纹理较敏感，适合作为默认自动对焦指标。

`laplacian_variance`

先用 3x3 Laplacian 核计算二阶响应，再取方差：

`score = var(Laplacian(image))`

图像越清晰，高频响应越强，方差越大。

`brenner`

计算水平方向相隔两个像素的差分平方和，并按 ROI 像素数归一化：

`score = sum((I[:, x+2] - I[:, x])^2) / patch_size`

该指标实现简单，对横向纹理敏感。

`normalized_variance`

计算方差除以平均亮度：

`score = var(image) / mean(image)`

这种形式可以减弱整体亮度变化对评分的影响，但对低纹理区域仍可能不稳定。

`MetricStrategy`

`MetricStrategy(metric_name)` 根据字符串选择指标，并实现 `FocusStrategy.score(image, roi)` 接口。

## 扫描流程

扫描逻辑在 `raman/autofocus/scanner.py`，高层流程在 `raman/autofocus/controller.py`。

### 单点采样

`ZScanner.sample_score(z_um, roi)` 对一个 Z 位置执行：

1. 检查 `z_um` 是否在 `[z_min_um, z_max_um]` 内。
2. 调用 `stage.move_absolute_um(z_um)` 移动 Z 轴。
3. 调用 `stage.wait_settled(stage_timeout_ms)` 等待稳定。
4. 连续获取 `frames_per_z` 帧，且每帧必须晚于上一次采样时间。
5. 对每帧计算 ROI 清晰度和饱和比例。
6. 返回各帧评分中位数和饱和比例中位数。

使用中位数可以降低偶发噪声、曝光跳变或单帧异常对曲线的影响。

### 粗扫描与细扫描

`ZScanner._scan()` 根据中心位置、范围和步长生成扫描网格：

`[center - range, center + range]`

实际范围会被裁剪到 `[z_min_um, z_max_um]`。网格通过 `np.arange(z_lo, z_hi + step_um * 0.5, step_um)` 生成，保证上边界附近的点能被包含。

扫描开始前，如果当前位置高于扫描起点，会先移动到 `z_lo - backlash_um` 附近，再向扫描起点方向前进。这样后续采样尽量从同一机械方向接近每个测量点，减小回程间隙造成的曲线偏差。

`coarse_scan()` 使用 `coarse_range_um` 和 `coarse_step_um`。

`fine_scan()` 使用 `fine_range_um` 和 `fine_step_um`。

## 峰值判断与抛物线插值

粗扫描完成后，控制器会先做质量检查：

1. 粗扫描点数必须至少为 3。
2. 最大值不能在扫描曲线两端，否则说明峰值可能在扫描范围外。
3. 峰值相对中位数的突出度必须足够：

   `prominence = (peak_score - median_score) / (median_score + 1e-9)`

   当前阈值为 `0.2`。低于阈值说明曲线太平，常见原因是 ROI 纹理不足、对焦范围没有覆盖焦点或图像质量异常。

细扫描完成后同样检查：

1. 点数至少为 3。
2. 最大值不能在曲线两端。

亚步长峰值由 `parabolic_peak()` 估计。对峰值点及其左右相邻点拟合一条等间隔抛物线：

设三个点分数为 `s_minus, s_zero, s_plus`，间距为 `dz`：

`denom = s_minus - 2 * s_zero + s_plus`

`delta = 0.5 * (s_minus - s_plus) / denom`

`z_peak = z_zero + delta * dz`

如果三点不是等间距、曲率过小或 `abs(delta) > 1.0`，说明拟合不可信，函数返回 `None`。控制器此时退回使用细扫描原始最大值位置。

## 最终移动与验证

得到 `z_best_um` 后，控制器执行 backlash 补偿移动：

1. `pre_z = max(z_best - backlash_um, z_min_um)`
2. 移动到 `pre_z` 并等待稳定。
3. 移动到 `z_best` 并等待稳定。

随后重新采样一次最终清晰度。如果最终分数低于细扫描最佳分数的 70%，返回 `LOW_CONFIDENCE`，因为这说明最终位置的实际图像质量没有复现扫描峰值，可能存在机械漂移、样品移动、相机帧滞后或曲线噪声。

## 置信度

当前置信度是一个启发式分数，范围为 `[0, 1]`：

1. 初始值为 `1.0`。
2. 如果粗扫描前三高分点中任意点的饱和比例超过 `max_saturation_ratio`，置信度乘以 `0.5`。
3. 置信度再乘以 `min(1.0, prominence)`。
4. 最终裁剪到 `[0, 1]`。

如果置信度低于 `min_confidence`，返回 `LOW_CONFIDENCE`；否则返回 `OK`。

## 失败状态

`FocusStatus` 可能取值：

- `OK`: 对焦成功。
- `NO_PEAK`: 扫描曲线没有可靠峰值，或峰值在边界。
- `LOW_CONFIDENCE`: 找到位置但质量验证或置信度不足。
- `OUT_OF_RANGE`: 扫描或目标位置超出 Z 轴安全范围。
- `STAGE_ERROR`: 位移台读数、移动或等待稳定失败。
- `FRAME_ERROR`: 相机帧获取超时。
- `ABORTED`: 预留状态，当前控制器流程中尚未主动使用。

## 实现结构

`models.py`

定义 ROI、Frame、协议接口、参数、扫描点、扫描曲线和结果类型。

`roi.py`

负责 ROI 裁剪、灰度化、饱和比例和基础预处理。

`metrics.py`

实现清晰度指标和 `MetricStrategy`。

`scanner.py`

负责 Z 轴扫描、单点采样、backlash 方向控制和三点抛物线插值。

`controller.py`

组织完整对焦流程，包括范围检查、粗扫、曲线质量判断、细扫、最终移动、验证和结果状态生成。

## 调参建议

`coarse_range_um`

应覆盖初始位置可能偏离真实焦点的最大范围。若经常出现粗扫描峰值在边界，应增大该值或改善初始 Z 位置。

`coarse_step_um`

决定粗定位速度与可靠性。步长过大会错过窄峰，过小会增加扫描时间。

`fine_range_um`

应覆盖粗扫描峰值的不确定性。若细扫描峰值常出现在边界，应增大该值。

`fine_step_um`

决定最终定位分辨率。较小步长更精细，但扫描更慢。

`frames_per_z`

图像噪声大或相机曝光不稳定时可以增大。机械和样品稳定时可减小以提升速度。

`metric_name`

默认 `tenengrad` 通常适合有边缘/颗粒纹理的显微图像。若样品纹理方向性明显或噪声较强，可比较 `laplacian_variance`、`brenner` 和 `normalized_variance` 的曲线形状。

`backlash_um`

应大于 Z 轴实际回程间隙。如果设置过小，重复定位可能受机械间隙影响；设置过大则增加移动时间。

`min_confidence`

提高该值会更保守，减少误对焦，但可能增加失败率。

