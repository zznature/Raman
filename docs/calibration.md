# Calibration 算法与实现说明

本文档说明 `raman/calibration/` 模块的图像配准、像素位移到位移台坐标的转换，以及 XY 修正量的计算原理。该模块用于根据参考图像和当前图像估计样品在视野中的平移，并给出应施加到 XY 位移台的反向补偿。

## 目标

显微镜或 Raman mapping 过程中，样品图像可能因为台面误差、回程间隙、热漂移或机械扰动发生 XY 偏移。`calibration` 模块解决两个问题：

1. 从两张图像估计当前图像相对参考图像的像素平移 `PixelShift(dx, dy)`。
2. 根据像素-位移台标定矩阵，将像素平移转换为应施加的台面修正 `StageShift(dx_um, dy_um)`。

当前实现假设两张图像之间主要是平移关系，不处理旋转、尺度变化、非线性畸变或明显形变。

## 坐标约定

像素坐标：

- `dx > 0`: 当前图像相对参考图像向右移动。
- `dy > 0`: 当前图像相对参考图像向下移动。

位移台坐标：

- `StageShift.dx_um` 和 `StageShift.dy_um` 使用位移台自身的微米坐标。
- 像素位移和台面位移之间由 2x2 矩阵定义，允许存在轴翻转、轴交换和轻微非正交。

`estimate_xy_correction()` 返回的是修正量，而不是测得的漂移量。若图像测得向右偏移，对应的台面修正是能抵消该偏移的反向移动。

## 数据模型

主要模型定义在 `raman/calibration/models.py`。

`ROI`

表示用于配准的图像区域。使用 ROI 可以排除边缘、遮挡、无纹理区域或会变化的区域，提高配准稳定性。

`PixelShift`

表示当前图像相对参考图像的像素平移：

- `dx`: 水平方向像素位移。
- `dy`: 垂直方向像素位移。

`StageShift`

表示位移台坐标系下的微米位移：

- `dx_um`
- `dy_um`

`ShiftResult`

保存图像配准结果：

- `shift`: 像素位移。
- `confidence`: 峰值置信度，范围 `[0, 1]`。
- `peak_value`: 相关峰值。
- `peak_position`: 相关峰在相关图中的位置。
- `roi`: 使用的 ROI。

## 图像预处理

预处理函数在 `raman/calibration/preprocessing.py`。

`prepare_image(image, roi=None, window=True)` 执行：

1. `crop(image, roi)`: 如果提供 ROI，则裁剪图像。
2. `to_grayscale(image)`: 将 2D 图像转为 `float32`，或将 RGB/RGBA 转为灰度：

   `gray = 0.299 R + 0.587 G + 0.114 B`

3. `normalize(image)`: 去均值并除以标准差：

   `I_norm = (I - mean(I)) / (std(I) + eps)`

   这样可以降低整体亮度和对比度变化对相位相关的影响。

4. `apply_hann_window(image)`: 默认施加二维 Hann 窗，减弱 FFT 周期边界带来的边缘伪影。

预处理后，参考图和当前图必须具有相同形状，否则 `estimate_translation()` 会抛出 `ValueError`。

## 相位相关算法

图像平移估计在 `raman/calibration/phase_correlation.py` 中实现，入口函数为 `estimate_translation(reference, moving, roi=None, upsample=True)`。

### 基本原理

若 `moving` 是 `reference` 的平移版本，二者在傅里叶域的相位差包含平移信息。相位相关通过归一化互功率谱去掉幅值，只保留相位：

`R = FFT(moving) * conj(FFT(reference))`

`C = R / max(abs(R), eps)`

`corr = IFFT(C)`

`abs(corr)` 的峰值位置对应两张图像之间的平移。

与普通互相关相比，相位相关对整体亮度缩放更不敏感，峰值通常更尖锐，适合估计平移。

### FFT 包裹位移

由于 FFT 相关是周期性的，峰值索引需要转换成有符号位移：

```text
if peak_index > size // 2:
    shift = peak_index - size
else:
    shift = peak_index
```

例如宽度为 512 的图像中，峰值 `peak_x = 509` 表示 `dx = -3`，而不是 `dx = 509`。

### 亚像素估计

当 `upsample=True` 时，实现在相关峰的 x 和 y 方向分别做一维三点二次曲线拟合：

`offset = 0.5 * (left - right) / (left - 2 * center + right)`

偏移被限制到 `[-1, 1]`。最终位移为整数峰值加上亚像素偏移。

该方法计算量小，适合快速修正。它不是完整的高精度频域上采样算法，因此在低信噪比、周期纹理或峰值不尖锐时，亚像素精度会下降。

## 置信度

`_peak_confidence()` 使用峰值相对旁瓣背景的 z-score 计算启发式置信度。

流程：

1. 在相关图中屏蔽峰值附近的 `5x5` 区域。
2. 对剩余区域计算平均值和标准差，作为旁瓣背景。
3. 计算：

   `z_score = max(0, (peak - background_mean) / background_std)`

4. 映射到 `[0, 1]`：

   `confidence = z_score / (z_score + 10)`

峰值越突出，置信度越接近 1。若图像重复纹理强、ROI 纹理不足、图像变化过大或运动不是纯平移，旁瓣会升高，置信度会降低。

## 像素与位移台坐标转换

坐标变换定义在 `raman/calibration/stage_transform.py` 的 `PixelStageTransform`。

矩阵约定为：

```text
[dx_px, dy_px]^T = pixel_per_um @ [dx_um, dy_um]^T
```

也就是说，`pixel_per_um` 表示位移台移动 1 微米会在图像中造成多少像素位移。

类初始化时会检查矩阵必须是 `2x2`，并计算逆矩阵：

```text
um_per_pixel = inv(pixel_per_um)
```

如果矩阵奇异，抛出 `SingularTransformError`。

`stage_to_pixel(StageShift)`

将台面位移转换成图像像素位移。

`pixel_to_stage(PixelShift)`

将图像像素位移转换成等效台面位移。

因为使用完整 2x2 矩阵，该实现支持：

- X/Y 轴比例不同。
- 图像轴与台面轴方向相反。
- 图像轴与台面轴交换。
- 小角度非正交或旋转耦合。

## XY 修正量计算

高层入口是 `raman/calibration/xy_corrector.py` 中的 `estimate_xy_correction()`。

流程：

1. 调用 `estimate_translation(reference, current, roi)` 得到当前图像相对参考图像的像素位移。
2. 如果 `result.confidence < min_confidence`，抛出 `LowConfidenceError`。默认阈值为 `0.4`。
3. 调用 `transform.pixel_to_stage(result.shift)`，得到造成该像素偏移的等效台面位移。
4. 返回其相反数：

   ```text
   correction.dx_um = -measured_stage_shift.dx_um
   correction.dy_um = -measured_stage_shift.dy_um
   ```

原因是函数返回的是用于抵消图像偏移的修正移动，而不是样品已经漂移的方向。

## 典型使用流程

1. 采集或保存一张参考图像 `reference`。
2. 在后续时刻采集当前图像 `current`。
3. 选择包含稳定纹理的 ROI。
4. 使用已标定的 `pixel_per_um` 矩阵构造 `PixelStageTransform`。
5. 调用 `estimate_xy_correction()` 得到应施加到位移台的微米修正量。

示例：

```python
import numpy as np
from calibration.models import ROI
from calibration.stage_transform import PixelStageTransform
from calibration.xy_corrector import estimate_xy_correction

pixel_per_um = np.array([
    [1.25, 0.02],
    [-0.01, 1.23],
])

transform = PixelStageTransform(pixel_per_um)
roi = ROI(x=100, y=80, width=512, height=512)

correction = estimate_xy_correction(
    reference_image,
    current_image,
    transform,
    roi=roi,
    min_confidence=0.4,
)

# correction.dx_um / correction.dy_um 是应发送给 XY stage 的修正量。
```

## `pixel_per_um` 标定方法

要使用 `PixelStageTransform`，需要先获得像素与台面坐标之间的线性关系。推荐流程：

1. 固定样品和焦距，采集参考图像。
2. 控制位移台沿 X 方向移动已知距离，例如 `+10 um`，采集图像并估计像素位移。
3. 控制位移台沿 Y 方向移动已知距离，例如 `+10 um`，采集图像并估计像素位移。
4. 用两个已知台面位移及其对应像素位移组成矩阵列：

   ```text
   pixel_per_um[:, 0] = pixel_shift_for_stage_x_move / dx_um
   pixel_per_um[:, 1] = pixel_shift_for_stage_y_move / dy_um
   ```

如果做多组位移，可以用最小二乘拟合 2x2 矩阵，以降低单次测量噪声。

## 失败和误差来源

低置信度通常来自：

- ROI 纹理不足或接近纯色。
- 图像中有多个重复周期纹理，导致多个相关峰。
- 两张图像曝光、亮度、遮挡或焦距变化过大。
- 样品发生旋转、缩放、非线性形变，而不是纯平移。
- ROI 太小，频域分辨率和统计稳定性不足。
- 当前偏移超过半个 ROI 尺寸，FFT 周期相关可能产生歧义。

矩阵转换误差通常来自：

- `pixel_per_um` 标定时 Z 焦点变化或图像畸变。
- 位移台移动量不准确。
- 标定移动距离过小，像素位移被亚像素噪声主导。
- 图像坐标系和位移台坐标系符号约定没有核对。

## 实现结构

`models.py`

定义 ROI、PixelShift、StageShift 和 ShiftResult。

`preprocessing.py`

负责 ROI 裁剪、灰度化、标准化和 Hann 窗。

`phase_correlation.py`

实现傅里叶相位相关、FFT 包裹位移转换、亚像素二次插值和峰值置信度估计。

`stage_transform.py`

实现像素位移与台面位移之间的 2x2 线性变换。

`xy_corrector.py`

组合图像配准和坐标变换，输出可直接用于台面补偿的反向修正量。

## 使用建议

ROI 应选择有稳定纹理的位置，避免亮斑、饱和区域、视野边缘和样品形态变化明显的位置。

参考图和当前图应在相同曝光、相同倍率、相同 ROI 尺寸下比较。

若置信度经常低于阈值，先检查相关峰是否唯一，再调整 ROI、曝光和 `min_confidence`。

实际发送位移台命令前，建议用小步长验证 `pixel_per_um` 的符号和轴向。最直接的检查方式是：执行一次修正后重新采图，偏移量应明显变小，而不是变大。

