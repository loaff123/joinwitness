# JoinWitness

**在执行 CSV 连接之前，先看清它会增加多少行、重复计算多少金额。**

JoinWitness 是面向开发者和数据分析师的本地命令行预检工具。提供两个 CSV、连接键和预期关系后，它会计算精确的结果行数，检查重复键与未匹配行，并生成可离线打开的 HTML 报告和 JSON 结果。

**当前状态：**0.1.0，采用 [MIT 许可证](../LICENSE)。请从本仓库或自行构建的 wheel 安装；尚未发布到 PyPI。

[English](../README.md) · [完整语义说明](SEMANTICS.md) · [隐私说明](PRIVACY.md) · [同类工具对比](COMPARISON.md)

## 四笔订单为什么会变成八行

演示数据包含四笔订单，金额分别为 `100`、`90`、`-30`、`90`，合计 `250`。

客户表中，前三个订单的客户分别出现 3 次、2 次、2 次；第四个订单没有匹配客户。左连接会得到 `3 + 2 + 2 + 1 = 8` 行，金额合计变为 `510`。

- 有符号的重复金额为 `260`
- 重复贡献的绝对金额为 `320`
- 一笔负金额的重复部分抵消了正金额的增加
- 右侧客户键重复，因此违反 `many-to-one` 预期

只核对净金额变化容易漏掉问题。JoinWitness 会同时展示重复行数、有符号重复金额和绝对重复金额，不会先生成整个连接结果。

## 安装

需要 Python 3.10 或更高版本。克隆仓库后，建议先创建虚拟环境：

```sh
git clone https://github.com/loaff123/joinwitness.git
cd joinwitness
python -m venv .venv
# macOS / Linux
. .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1
python -m pip install .
joinwitness --help
```

也可以安装从本仓库构建的 wheel：

```sh
python -m pip install /path/to/joinwitness-0.1.0-py3-none-any.whl
```

运行预检不需要网络。安装时可能需要下载 Jinja2/MarkupSafe 依赖；从源码安装还可能下载构建工具。完全离线安装需先准备兼容的依赖 wheel，再通过 pip 的 `--no-index --find-links /path/to/wheelhouse` 安装。

## 快速体验

```sh
joinwitness demo --output demo
```

目标目录必须不存在或为空。命令会生成两个合成 CSV、`audit.json` 配置、`report.html` 和 `report.json`。用浏览器打开 `demo/report.html` 即可查看结果。

演示故意包含不符合多对一关系的数据。`demo` 成功创建文件时返回 `0`；它的报告仍会标出质量失败。用 `run` 重跑该配置时，会按质量结果返回 `1`。

## 预检自己的文件

以下示例将左表的 `customer_id` 与右表的 `id` 对应：

```sh
joinwitness audit orders.csv customers.csv \
  --left-key customer_id --right-key id \
  --expect many-to-one --how left \
  --amount amount \
  --html report.html --json report.json
```

- `--expect`：`one-to-one`（一对一）、`one-to-many`（一对多）、`many-to-one`（多对一）、`many-to-many`（多对多）
- `--how`：`inner`（内连接）或 `left`（左连接）
- `--amount`：需要跟踪的左表金额列；可省略
- `--max-output-rows N`：预计结果超过 N 行时失败
- `--fail-on-unmatched`：任意一侧有未匹配行时失败，包括 NULL 键行
- `--fail-on-expansion`：任意已匹配左行被重复时失败

关系检查覆盖两侧所有非 NULL 键，包括没有匹配到对方的键。多对一要求右侧唯一；一对多要求左侧唯一。允许多对多不会自动保证金额可加，需根据业务意图选择额外的失败规则。

### 组合键

按相同顺序重复键参数：

```sh
joinwitness audit orders.csv customers.csv \
  --left-key customer_id --left-key region \
  --right-key id --right-key region \
  --expect many-to-one --how left \
  --html report.html --json report.json
```

这会比较 `(customer_id, region)` 与 `(id, region)`。两侧键列数量必须相同；任一分量为 NULL 时，整行不参与匹配。

### 保存配置并重跑

```sh
joinwitness audit orders.csv customers.csv \
  --left-key customer_id --right-key id \
  --expect many-to-one --how left \
  --amount amount --fail-on-expansion \
  --save-config audit.json \
  --html report.html --json report.json

joinwitness run audit.json --force
```

**配置包含私有路径和列名，不是脱敏报告。** 提交到版本库或分享前务必检查。保存时尽可能使用相对配置目录的路径；Windows 跨盘时使用绝对路径。重跑时，相对输入路径按配置所在目录解析。

报告路径不写入配置。`audit` 和 `run` 默认在当前目录写入 `report.html` 与 `report.json`；已有文件需要 `--force` 才能替换。也可以指定新的输出路径保留旧报告。即使指定 `--force`，也不能覆盖输入 CSV 或正在运行的配置。输出目录需预先存在。

### 分隔符与 NULL

默认分隔符是逗号。两侧必须使用相同的分隔符；`--delimiter ';'` 可指定一个真实字符，字符串 `\t` 不会自动转成制表符。

默认只有空字符串是 NULL，CSV 中带引号的空字段 `""` 也一样。指定 `--null-value` 会**替换**默认列表；如果还想把空字段当作 NULL，请显式保留：

```sh
--null-value '' --null-value NULL
```

匹配区分大小写。默认情况下，`NULL`、`NA`、空格都是普通键值。NULL 永不匹配 NULL，组合键中任一字段为 NULL 也不匹配。

### 原始键样本

默认 HTML 和 JSON 不导出源文件路径、列名、原始键、源数据行或哈希。需要排查具体键时，可显式启用：

```sh
--samples 5
```

`N` 的范围为 0–100，是整个报告的原始键样本总预算，依次用于膨胀组、左侧未匹配键、右侧未匹配键。样本是诊断用的确定性选择，不是随机样本。启用后可能暴露客户 ID、邮箱等信息；分享前请检查。

## 如何理解退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | `audit` / `run` 的所有声明规则通过 |
| `1` | 预检已完成，但至少一个质量规则未通过 |
| `2` | 输入、配置或输出错误 |

`demo` 成功生成故意失败的演示时返回 `0`；用户中断返回 `130`。质量失败仍会生成可供检查的报告。

## 金额与精度

金额仅支持有限的普通十进制字符串，可带正负号；最多 38 位数字，其中小数部分最多 18 位。不支持首尾空格、指数写法、货币符号、千位分隔符、`NaN` 或无穷大。所有左表金额单元格都必须合法，包括未匹配行。

计算使用整数定点运算，不进行二进制浮点舍入。JSON 中金额是十进制字符串。工具不识别币种、不换汇，也不判断不同记录的金额是否适合相加。

内连接既可能丢弃未匹配金额，也可能重复已匹配金额，因此报告会区分丢弃、重复与净变化。零金额行重复时，金额不变，但重复行计数仍会反映问题。

## 支持范围与限制

- 输入为带表头的 UTF-8 CSV，支持初始 BOM、引号、引号内换行和指定分隔符
- 错误的 CSV、重复表头、缺失列、无效 UTF-8、非法金额等会报错，不会静默跳过
- 单字段上限为 131,072 个解码后的字符
- 键按原始文本精确比较，不自动转换类型、去空格、忽略大小写或进行 Unicode 归一化
- `001`、`1` 与 `1 ` 是三个不同的键
- 仅支持两个文件的内连接或左等值连接预检；不执行连接，不自动去重或修复，不支持 Excel、模糊连接、时间邻近连接或数据库查询
- 输入逐行扫描，但不同键的聚合信息保存在内存中；内存随不同键数量和键长度增长，不具备磁盘溢写能力

[语义说明](SEMANTICS.md)定义了全部计数公式和边界。[基准结果](../benchmarks/RESULTS.md)只代表实际测量的数据规模和环境，不是通用容量保证。

## 隐私与同类工具

运行过程完全在本地，不发送遥测、不调用在线模型，不修改输入文件。HTML 自包含，可离线打开。默认报告虽不含源标识，聚合数量和金额仍可能敏感。配置、错误输出和启用样本的报告需要单独检查。详见[隐私说明](PRIVACY.md)。

pandas 已提供连接关系验证和来源标记，qsv 提供更完整的 CSV 连接命令，getchatdata 也有本地连接预检工具。JoinWitness 侧重可离线审阅的报告、重复运行的配置和明确的质量策略，不宣称首创。详见[基于原始文档的对比](COMPARISON.md)。

开发贡献请参阅 [CONTRIBUTING.md](../CONTRIBUTING.md)。许可证见 [LICENSE](../LICENSE)。配置了 Windows CI 工作流不代表已在 Windows 上实际运行测试。
