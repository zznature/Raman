# Raman 测量自动化

任务: 完成样品自动化 Raman mapping.
典型样品：高通量薄膜(如YBCO)

现有 Raman 仪器控制软件: Horiba LabSpec6

```
for each mapping point:
  -> move XYZ stage to planned XY and predicted Z
  -> run local autofocus if needed
  -> capture microscope image after Z change
  -> estimate XY image drift by phase correlation
  -> convert pixel drift to stage um correction
  -> apply XY correction through XYZStage
  -> optionally verify residual drift once
  -> trigger or coordinate LabSpec6 Raman acquisition
  -> store point metadata, focus result, correction, and image references
```

## 环境安装

Python 环境: Python 3.10

## 显微镜 Camera 图像采集

图像采集 camera 型号: IDS UI-358x

技术组合: `Python 3.10 + IDS Software Suite 4.96 + pyueye`.

IDS Software Suite 4.96 下载地址: https://www.hopetw.com/modules/news/article.php?storyid=83

DLL 文件目录: `C:\Program Files\IDS\uEye\develop\bin`.

初始功能设计: 基础采集功能 + 简单 GUI + 模块化项目结构.

## 采集Spectrum

配置采集参数和采集模式，完成采集Spectrum.

## 自动对焦(Autofocus)

### 目标

自动对焦应设计为独立模块，不直接耦合 GUI、相机 SDK 或位移台串口实现.模块只依赖三个抽象接口:

- `FrameProvider`: 获取当前显微镜图像帧，例如 IDS camera live view 的最新帧.
- `ZStage`: 读取当前位置、相对移动、绝对移动、等待运动完成.
- `FocusStrategy`: 输入图像和 ROI，输出清晰度评分，并根据扫描结果给出最佳 Z 位置.

这样可以先用离线图片或模拟 Z 轴测试自动对焦算法，再接入真实相机和位移台.


## 位移台控制

### 位移台通讯方式

控制器通讯: Serial.

连接端口: USB Serial Port (`COM3`).

编程指南: `assets\MC_NewtonLT06_编程指南.md`.
