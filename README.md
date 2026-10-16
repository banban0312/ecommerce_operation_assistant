# 电商运营助手

面向电商团队的商品运营工作台，覆盖店铺和商品档案、库存与竞品、AI 内容、异步素材、人工投放审批、经营复盘、表格导入和团队角色管理。

> 本仓库提供单机开发/演示部署。M1—M12 的代码能力在当前工程中；实现边界、外部服务依赖和设计差异见[实现状态说明](docs/实现状态说明.md)。PRD 与 Spec 保留在 [`docs/`](docs/README.md)。

## 新机器部署

以下流程从 GitHub 克隆开始，不依赖原电脑的 `.env`、数据库、Docker 卷或 IDE 文件。全新数据库没有默认账号或预置经营数据，管理员和演示数据按步骤创建。

### 1. 安装前置软件

- Git
- Docker Desktop（Windows 建议启用 WSL 2 后端和 Linux 容器），或已安装 Docker Engine 与 Compose v2 的 Linux/macOS
- PowerShell 7（运行仓库提供的初始化和验收脚本）
- 首次构建需要网络，以拉取容器基础镜像并安装锁定依赖

部署运行不要求本机另装 Python、uv 或 Node.js；这些工具仅用于不通过 Docker 进行本地开发与检查。

确认 Docker 引擎已启动：

```powershell
docker version
docker compose version
```

### 2. 克隆仓库

在 PowerShell 中执行：

```powershell
git clone https://github.com/banban0312/ecommerce_operation_assistant.git
Set-Location .\ecommerce_operation_assistant
```

克隆后的仓库根目录就是原本本地的 `code` 目录；在此处应能看到 `compose.yaml`、`api`、`web`、`scripts` 和本 README。不要再进入名为 `code` 的子目录。

### 3. 初始化本机配置

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-env.ps1
```

脚本从 `.env.example` 创建被 Git 忽略的 `.env`，并随机生成数据库密码和认证签名密钥。它不会覆盖已有 `.env`。默认启动不需要模型服务 API Key；登录并进入“系统设置”后再按需配置。不要把真实 `.env` 提交到 Git。

### 4. 构建并启动

```powershell
docker compose up -d --build --wait --wait-timeout 180
docker compose ps -a
```

首次构建会花一些时间。预期 `mysql`、`redis`、`api`、`worker`、`web` 为 `healthy`；`migrate` 执行数据库迁移后以退出码 0 结束，这是正常状态。

如果端口 `3000` 或 `8000` 已占用，在启动前编辑本机 `.env` 中的 `WEB_PORT` 或 `API_PORT`，再执行启动命令。Compose 只将 Web/API 绑定到本机回环地址，不会直接向局域网或公网开放。

### 5. 创建首个管理员

```powershell
docker compose exec api python -m app.bootstrap
```

按提示输入管理员邮箱、显示名称，并设置至少 12 位密码。密码输入时不会回显。**项目没有通用的默认账号或默认密码。** 首个管理员会同时获得默认工作区；之后通过 Web 的“成员管理”页面创建运营人员、主管或其他管理员。若数据库里已经有用户，初始化命令会拒绝重复创建。

### 6. 登录并准备演示数据

打开 [http://localhost:3000/login](http://localhost:3000/login)，使用刚设置的管理员凭据登录。

进入运营大盘，点击“准备演示数据”可以建立带有模拟标记的店铺、商品、库存、竞品和经营周期数据，便于浏览主要页面。演示数据会写入数据库；请在空数据库或没有真实经营记录的工作区中使用，不要把它当作真实经营记录。

管理员可通过以下页面继续操作：

| 页面 | 地址 | 主要用途 |
| --- | --- | --- |
| 运营大盘 | [http://localhost:3000](http://localhost:3000) | 店铺、商品概览、库存预警和演示数据入口 |
| 商品工作台 | [http://localhost:3000/products](http://localhost:3000/products) | 搜索商品、筛选店铺和库存、进入单品 |
| 导入中心 | [http://localhost:3000/imports](http://localhost:3000/imports) | 选择商品/SKU/经营数据的 CSV 或 Excel 模板，预览后确认导入 |
| Agent 中心 | [http://localhost:3000/agent](http://localhost:3000/agent) | 创建单品运营任务，查看步骤并处理审批 |
| 成员管理 | [http://localhost:3000/members](http://localhost:3000/members) | 管理员创建工作区成员并分配角色 |
| 系统设置 | [http://localhost:3000/settings](http://localhost:3000/settings) | 配置模型服务、店铺占位状态和任务规则 |

### 7. 验证服务

不登录时运行基础健康、数据库迁移和 Worker 往返检查：

```powershell
.\scripts\smoke.ps1
```

如需同时检查管理员登录、工作台访问和退出，在 PowerShell 凭据提示中输入账号：

```powershell
$credential = Get-Credential -Message '输入管理员账号和密码'
.\scripts\smoke.ps1 -Credential $credential
```

完整页面回归入口：

```powershell
.\scripts\p0-regression.ps1 -Credential $credential -ReportPath .\reports\p0-regression.json
```

检查报告放在 Git 忽略的 `reports/` 中，不包含密码。人工业务验收步骤见[验收清单](docs/validation/M9-P0验收记录.md)。

如果当前 PowerShell 会话禁止运行本机脚本，可先执行 `Set-ExecutionPolicy -Scope Process Bypass`，该设置只对当前终端进程生效。

### 8. 停止、重启和更新

```powershell
# 停止应用，但保留数据库、Redis 和素材卷
docker compose down

# 再次启动已构建的服务
docker compose up -d --wait --wait-timeout 180

# 拉取当前 Git 代码并重建本机镜像
git pull
docker compose up -d --build --wait --wait-timeout 180
```

`docker compose down` 会保留数据卷。**不要运行 `docker compose down -v` 或删除 Docker volumes，除非明确要永久清空数据库和已上传素材。**

## 模型服务配置

核心页面、商品和库存功能不依赖外部模型。需要 AI 内容或媒体生成时，由管理员在“系统设置”填写服务地址、模型名称和密钥。Web 页面配置的工作区密钥会加密后保存在数据库；API 不会把密钥明文返回页面。`.env` 中同类 Provider 变量可作为未配置工作区服务时的默认凭据。

备份数据库时要同时安全备份原 `.env`：`AUTH_SECRET_KEY` 用来派生工作区密钥加密密钥，丢失后旧数据库中的工作区 Provider 密钥无法解密。恢复数据后如无法恢复原认证密钥，需要重新配置这些 Provider 密钥。参见[运行与数据恢复说明](docs/operations/运行与数据恢复.md)。

外部模型/媒体服务是否可用取决于供应商账号、额度、接口和模型权限。容器健康检查只验证本地服务，不代表外部模型或图像/视频真实生成已验收。

## 本地开发与检查

本地开发需要 Python 3.12、uv、Node.js 22 或更新版本。Docker 启动整套依赖后，可单独运行锁定依赖的静态检查、测试和生产构建：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

跳过依赖安装以加快重复检查：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -SkipInstall
```

常用依赖命令：

```powershell
uv sync --project api --locked
npm --prefix web ci
uv run --project api --locked pytest api/tests -q
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web run build
```

修改后端依赖时更新并提交 `api/pyproject.toml` 和 `api/uv.lock`；修改前端依赖时更新 `web/package-lock.json`。不要提交 `.venv`、`node_modules`、`.env`、数据库文件或测试报告。

## 目录结构

```text
api/                         FastAPI 应用、业务服务、Celery Worker、Alembic 迁移和测试
web/                         Next.js 页面、组件、样式和同源 API 转发路由
scripts/                     环境初始化、检查、冒烟测试、镜像归档脚本
docs/                        PRD、Spec、实现状态、运维说明和验收清单
compose.yaml                 本地 MySQL、Redis、API、Worker、Web 部署
.env.example                 无密钥的本地配置模板
```

## 文档入口

- [文档目录](docs/README.md)
- [产品需求 PRD](docs/requirements/PRD.md)
- [技术设计 Spec](docs/architecture/SPEC.md)
- [设计与实现状态差异](docs/实现状态说明.md)
- [运行与数据恢复](docs/operations/运行与数据恢复.md)
- [P0 人工验收清单](docs/validation/M9-P0验收记录.md)

## 常见问题

**Docker 报 `dockerDesktopLinuxEngine` pipe 不存在**：先启动 Docker Desktop，确认 Linux 容器引擎正常，再检查 `docker version` 是否能显示 Server 信息。

**服务未变健康**：运行 `docker compose ps -a` 和 `docker compose logs --tail 100 mysql redis migrate api worker web` 查看具体服务日志。修正 `.env` 或端口后用 `docker compose up -d --build --wait --wait-timeout 180` 重试。

**忘记管理员密码**：项目没有可公开复用的默认密码。当前版本没有密码重置页面；若已有管理员仍可登录，可从成员管理按需创建新管理员。保留现有数据库后，不要再次运行首个管理员初始化命令。
