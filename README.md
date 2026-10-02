# model-converter

将 DirectX 遗留的 `.x` 模型（含骨骼蒙皮动画）转换为 glTF 2.0 二进制格式 `.glb`。

实现完全基于本机 Blender：以 headless 模式调用 Blender，使用官方
`io_directx_x` 导入器读取 `.x`（几何、材质、骨骼、蒙皮权重、动画），再用
Khronos 官方 glTF 2.0 导出器写出 `.glb`。输出的 glb 规范、加载器兼容性最好
（组件类型天然为 UNSIGNED_BYTE 关节 / UNSIGNED_SHORT 索引、蒙皮网格挂在
骨骼根下），无需任何后处理。

## 目录结构

```
model_converter/
├── main.py            # CLI 入口
├── converter.py       # 核心逻辑（定位 blender.exe、进程调度、glb 校验）
├── blender_bridge.py  # Blender 端脚本（blender -b 加载，批量导入/导出）
├── samples/           # 用于测试的 .x 样例（从 ProjectZomboid media/models_X 复制）
└── output/            # 生成的 .glb（已 gitignore）
```

## 前置条件

1. 安装 Blender 5.x（本机路径：`C:\Program Files\Blender Foundation\Blender 5.2\`）。
2. 在 Blender 中通过 **Edit → Preferences → Get Extensions** 安装并启用官方
   **DirectX X Format (.x)** 扩展（扩展 ID `io_directx_x`，位于用户配置目录
   `%APPDATA%\Blender Foundation\Blender\5.2\extensions\blender_org\io_directx_x`，
   不在安装目录内）。

`blender.exe` 的查找顺序：`BLENDER_EXE` 环境变量 → 默认安装路径 →
`Blender Foundation` 目录下其他版本 → `PATH`。

## 使用

```bash
# 转换单个文件
python main.py samples/BeerBottle.X

# 转换整个目录（递归处理所有子目录中的 .x/.X），
# 输出目录中按相同结构创建子目录；非 .x 文件默认复制到对应位置
python main.py samples -o output

# 忽略非 .x 文件，不复制
python main.py samples -o output --non-x ignore
```

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `-o, --output` | 输出目录（默认 `./output`） |
| `--blender PATH` | `blender.exe` 路径（默认 `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`）。未指定时依次回退到 `BLENDER_EXE` 环境变量、`Blender Foundation` 目录下其他版本、`PATH`；显式指定但路径不存在则直接报错 |
| `-j, --jobs N` | 并行 Blender 进程数（默认 CPU 核心数；批量转换时显著加速，内存不足可调小） |
| `--existing {overwrite,skip}` | 目标文件已存在时的行为：`overwrite` 直接覆盖（默认），`skip` 跳过该文件不转换 |
| `--non-x {ignore,copy}` | 源目录中非 `.x` 文件的处理：`copy` 复制到输出目录对应位置（默认），`ignore` 忽略 |

转换过程中会在终端显示进度条（仅交互终端）。转换完成后会输出每个模型的
摘要（mesh / skin / animation 数量），用于确认动画是否被保留：`skins` 与
`animations` 均 > 0 表示骨骼蒙皮动画已写入 glb。

## 并行转换

默认按 CPU 核心数并行启动多个 headless Blender 进程，每个文件独立转换，
互不影响（单个文件失败不会中断整体）。可通过 `-j` 调整并行度：

```bash
# 只开 2 个 Blender 进程（内存受限时）
python main.py samples -o output -j 2
```

## 说明与已知限制

- **纹理**：`.x` 内仅引用纹理文件名（如 `BeerBottle.png`），而 ProjectZomboid
  的纹理打包在 `texturepacks` 里，不是松散 PNG，所以导出的 glb 里是外部 URI
  引用（`"uri": "BeerBottle.png"`）而非内嵌数据。几何和动画不受影响。
- **静态网格**：Blender 导入器会为 `.x` 的 Frame 层级建立单骨骼 armature，
  无动画网格因此报告为 `skinned (no clips)`（结构上更忠实于原文件，对加载器
  无副作用）。
- **坐标系**：`.x` 为左手系，glTF 为右手系。Blender 的 io_directx_x 导入器与
  glTF 导出器均会自行处理轴转换（导入 Forward=Z / Up=Y，导出默认 +Y up）。
- **单位**：模型单位按原样保留，glTF 规范单位为米，实际缩放需按项目需要调整。
