# AiHub - AI Gateway 管理平台

[English](./README_EN.md) | 简体中文

一个统一的AI模型网关管理平台，支持多个AI提供商的账号管理、负载均衡、风控防护和使用统计。

## 功能特性

### 核心功能
- 🔄 **多提供商支持**：OpenAI、Anthropic、Google Gemini、AWS Kiro、智谱GLM
- 🎯 **智能负载均衡**：自动选择可用账号，支持优先级和权重配置
- 📊 **实时统计**：请求数、Token消耗、用量趋势可视化
- 🔐 **用户认证系统**：邮箱注册、邀请码、Token管理、配额控制
- 💳 **账号池管理**：批量导入、用量监控、自动刷新、健康检查

### 🛡️ 风控防护系统
- 🌐 **代理池管理**：支持HTTP/HTTPS/SOCKS4/SOCKS5，四种绑定策略（STICKY/RANDOM/ROUND_ROBIN/LEAST_USED）
- ⏱️ **多级速率限制**：全局/账号/用户三级限流，支持RPM/TPM限制，令牌桶算法
- 🎭 **指纹伪装**：50+真实浏览器指纹，User-Agent轮换，Chrome Client Hints支持
- 💊 **健康监控**：实时监控账号状态，自动降级和恢复，风险等级评估
- 📈 **风险检测**：智能识别异常，自动调整策略

### 高级功能
- 🔄 **格式转换**：支持OpenAI、Claude、Gemini等多种API格式互转
- 💾 **Prompt Cache**：支持Claude Prompt Caching，降低成本
- 🗜️ **上下文压缩**：滑动窗口/摘要/混合策略，优化长对话
- 📝 **内容清理**：自动清理特殊字符、规范化空格、修复代码格式
- 🎯 **模型管理**：动态启用/禁用模型，支持模型定价配置

### 管理功能
- **提供商管理**：配置不同AI提供商的优先级、权重、启用状态
- **账号管理**：管理每个提供商的API账号池，支持批量导入
- **用户管理**：创建用户、分配配额、邀请码系统
- **Token管理**：API Key生成、配额设置、使用统计
- **统计分析**：请求趋势、Token消耗、Top用户排行、模型使用分布

### 界面特性
- 🌓 **亮色/暗色主题**：自动适配用户偏好
- 📱 **响应式设计**：支持桌面和移动端
- 📈 **数据可视化**：Chart.js图表展示趋势
- 🎨 **现代化UI**：卡片式设计、进度条展示、实时更新

## 快速开始

### 环境要求
- Python 3.10+
- aiohttp >= 3.9.0
- aiosqlite >= 0.19.0
- httpx >= 0.27.0
- bcrypt >= 4.0.0
- python-dotenv >= 1.0.0

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd AiHub

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑.env文件，设置必要的配置项

# 启动服务
python main.py
```

### 首次使用

1. 打开浏览器访问：`http://localhost:8000`
2. 使用默认超级管理员账号登录：
   - 邮箱：`admin@aihub.local`
   - 密码：`admin123456`
3. 登录后可以创建邀请码，邀请其他用户注册

### 🛡️ 启用风控系统（推荐用于生产环境）

```bash
# 1. 复制配置模板
cp risk_control_config.json.example risk_control_config.json

# 2. 编辑配置文件，启用所需功能
# 3. 重启服务
python main.py
```

## 项目结构

```
AiHub/
├── models/              # 数据模型层
│   ├── database.py      # 数据库连接和操作
│   ├── account.py       # 账号模型
│   ├── channel.py       # 渠道模型（已废弃，使用provider）
│   ├── user.py          # 用户模型
│   ├── token.py         # Token模型
│   ├── auth.py          # 认证模型（邮箱验证、邀请码）
│   └── init_admin.py    # 初始化超级管理员
├── providers/           # AI提供商实现
│   ├── base.py          # 提供商基类
│   ├── openai.py        # OpenAI提供商
│   ├── anthropic.py     # Anthropic提供商
│   ├── google.py        # Google Gemini提供商
│   ├── kiro.py          # AWS Kiro提供商
│   └── glm.py           # 智谱GLM提供商
├── converters/          # 请求/响应格式转换器
│   ├── base.py          # 转换器基类
│   ├── openai.py        # OpenAI格式转换
│   ├── claude.py        # Claude格式转换
│   ├── gemini.py        # Gemini格式转换
│   ├── kiro.py          # Kiro格式转换
│   └── glm.py           # GLM格式转换
├── server/              # Web服务器
│   ├── app.py           # 应用入口和路由配置
│   ├── routes.py        # API路由处理（聊天接口）
│   ├── api.py           # 管理API（账号、用户、Token、统计）
│   ├── api_providers.py # 提供商管理API
│   ├── api_auth.py      # 认证API（注册、登录、邀请码）
│   ├── api_risk_control.py # 风控系统API
│   ├── middleware.py    # 中间件（认证、CORS、错误处理）
│   └── tasks.py         # 后台任务（清理过期数据）
├── utils/               # 工具函数
│   ├── logger.py        # 日志工具
│   ├── token_estimator.py # Token计数器
│   ├── risk_control.py  # 风控系统管理器
│   ├── proxy_manager.py # 代理池管理
│   ├── rate_limiter.py  # 速率限制器
│   ├── health_monitor.py # 健康监控
│   ├── fingerprint.py   # 浏览器指纹生成
│   ├── cache_handler.py # 缓存处理
│   └── context_compressor.py # 上下文压缩
├── static/              # 前端静态文件
│   ├── index.html       # 主管理界面
│   ├── login.html       # 登录页面
│   ├── register.html    # 注册页面
│   ├── risk-control.html # 风控管理界面
│   ├── css/             # 样式文件
│   ├── js/              # JavaScript文件
│   └── assets/          # 静态资源
├── logs/                # 日志文件目录
├── main.py              # 程序入口
├── config.py            # 配置文件
├── requirements.txt     # Python依赖
├── .env.example         # 环境变量模板
└── risk_control_config.json.example # 风控配置模板
```

## API文档

### 认证方式

#### 用户认证（推荐）
使用用户Token进行认证：
```
Authorization: Bearer <your-token>
```

#### 管理员认证（已废弃）
使用管理密钥进行认证：
```
X-Admin-Key: <your-admin-key>
```

### 主要端点

#### 认证相关
- `POST /api/auth/register` - 用户注册（需要邀请码）
- `GET /api/auth/verify-email` - 邮箱验证
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/logout` - 用户登出
- `GET /api/auth/me` - 获取当前用户信息
- `POST /api/auth/change-password` - 修改密码
- `GET /api/auth/tokens` - 获取用户的Token列表
- `POST /api/auth/invite-codes` - 创建邀请码（管理员）
- `GET /api/auth/invite-codes` - 获取邀请码列表（管理员）

#### 提供商管理
- `GET /api/providers` - 获取所有提供商
- `GET /api/providers/{type}` - 获取单个提供商信息
- `PUT /api/providers/{type}/config` - 更新提供商配置
- `GET /api/providers/{type}/models` - 获取提供商支持的模型
- `POST /api/providers/{type}/models` - 添加模型
- `DELETE /api/providers/{type}/models/{model}` - 删除模型

#### 账号管理
- `GET /api/providers/{type}/accounts` - 获取提供商的账号列表
- `POST /api/providers/{type}/accounts` - 添加账号
- `POST /api/providers/{type}/accounts/import` - 批量导入账号
- `DELETE /api/providers/{type}/accounts` - 清空账号
- `GET /api/accounts` - 获取所有账号
- `PUT /api/accounts/{id}` - 更新账号
- `DELETE /api/accounts/{id}` - 删除账号
- `POST /api/accounts/{id}/refresh-usage` - 刷新账号用量

#### 用户管理
- `GET /api/users` - 获取所有用户
- `POST /api/users` - 创建用户
- `PUT /api/users/{id}` - 更新用户
- `DELETE /api/users/{id}` - 删除用户

#### Token管理
- `GET /api/tokens` - 获取所有Token
- `POST /api/tokens` - 创建Token
- `PUT /api/tokens/{id}` - 更新Token
- `DELETE /api/tokens/{id}` - 删除Token
- `GET /api/tokens/stats` - Token使用统计

#### 统计与日志
- `GET /api/stats?days=7` - 获取统计数据
- `GET /api/logs` - 获取请求日志
- `GET /api/models/pricing` - 获取模型定价

#### 风控系统
- `GET /api/risk-control/status` - 获取风控系统状态
- `GET /api/risk-control/proxy-pool/stats` - 代理池统计
- `POST /api/risk-control/proxy-pool/add` - 添加代理
- `POST /api/risk-control/proxy-pool/health-check` - 代理健康检查
- `GET /api/risk-control/rate-limit/stats` - 速率限制统计
- `GET /api/risk-control/health-monitor/stats` - 健康监控统计
- `GET /api/risk-control/accounts/{id}/health` - 账号健康详情
- `POST /api/risk-control/accounts/{id}/degrade` - 手动降级账号
- `POST /api/risk-control/accounts/{id}/ban` - 手动封禁账号
- `POST /api/risk-control/accounts/{id}/recover` - 恢复账号
- `POST /api/risk-control/config` - 更新风控配置

#### AI接口（兼容OpenAI格式）
- `POST /v1/chat/completions` - 聊天补全（OpenAI格式）
- `POST /v1/messages` - 消息接口（Claude格式）
- `POST /v1/responses` - 响应接口
- `POST /v1beta/models/{model}:generateContent` - Gemini生成内容
- `POST /v1beta/models/{model}:streamGenerateContent` - Gemini流式生成
- `GET /v1/models` - 获取可用模型列表
- `GET /v1/models/{model}` - 获取单个模型信息

## Token计算

项目使用精确的Token估算算法，基于new-api的实现：

- **OpenAI模型**：使用OpenAI权重
- **Claude模型**：使用Claude权重
- **Gemini模型**：使用Gemini权重

支持的字符类型：
- 英文单词、数字、中文字符
- 符号、数学符号、Emoji
- URL分隔符、换行符、空格

## 配置说明

### 环境变量（.env）
```bash
# 服务器配置
HOST=0.0.0.0
PORT=8000

# 数据库路径
DATABASE_PATH=aihub.db

# 日志级别
LOG_LEVEL=INFO

# 管理密钥（已废弃，使用用户认证系统）
ADMIN_KEY=your_admin_key_here

# 超级管理员配置
SUPER_ADMIN_EMAIL=admin@aihub.local
SUPER_ADMIN_PASSWORD=admin123456
SUPER_ADMIN_NAME=Super Admin

# 初始邀请码
INITIAL_INVITE_CODE=WELCOME2024

# 内容清理配置
CONTENT_CLEANING_ENABLED=true
CLEAN_SPECIAL_CHARS=true
NORMALIZE_WHITESPACE=true
FIX_CODE_FORMATTING=true
REMOVE_DEBUG_MARKERS=true

# Prompt Cache配置（Claude）
PROMPT_CACHE_ENABLED=true

# 上下文压缩配置
CONTEXT_COMPRESSION_ENABLED=false
CONTEXT_COMPRESSION_THRESHOLD=8000
CONTEXT_COMPRESSION_TARGET=4000
CONTEXT_COMPRESSION_STRATEGY=sliding_window  # sliding_window, summary, hybrid
```

### 支持的AI提供商

#### OpenAI
- 模型：gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o等
- 需要：API Key
- 特性：完整支持，流式响应

#### Anthropic (Claude)
- 模型：claude-3-opus, claude-3-sonnet, claude-3-haiku等
- 需要：API Key
- 特性：Prompt Caching支持

#### Google Gemini
- 模型：gemini-pro, gemini-pro-vision等
- 需要：API Key
- 特性：原生Gemini格式支持

#### AWS Kiro
- 模型：基于Claude的模型
- 需要：AWS Builder ID认证
- 特性：自动刷新用量、免费额度统计、OAuth设备流程

#### 智谱GLM
- 模型：glm-4, glm-4-plus, glm-3-turbo等
- 需要：API Key
- 特性：流式响应、格式转换

## 开发

### 添加新的AI提供商

1. 在`providers/`目录创建新文件（如`newprovider.py`）
2. 继承`BaseProvider`类并实现必要方法：
```python
from providers.base import BaseProvider

class NewProvider(BaseProvider):
    BASE_URL = "https://api.newprovider.com"
    
    def __init__(self):
        super().__init__(
            name="newprovider",
            display_name="New Provider",
            default_models=["model-1", "model-2"]
        )
    
    async def chat(self, account, model, messages, stream=False, **kwargs):
        # 实现聊天逻辑
        pass
```
3. 在`converters/`目录创建对应的转换器
4. 提供商会自动被发现和注册

### 添加新的格式转换器

1. 在`converters/`目录创建新文件
2. 继承`BaseConverter`类：
```python
from converters.base import BaseConverter

class NewConverter(BaseConverter):
    def __init__(self):
        super().__init__("newprovider")
    
    def convert_request(self, request_data):
        # 转换请求格式
        pass
    
    def convert_response(self, response_data):
        # 转换响应格式
        pass
```

### 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio

# 运行测试
python -m pytest tests/
```

## 部署

### Docker部署（推荐）

```bash
docker build -t aihub .
docker run -d -p 8000:8000 -v ./data:/app/data aihub
```

### 系统服务

```bash
# 复制服务文件
sudo cp aihub.service /etc/systemd/system/

# 启动服务
sudo systemctl start aihub
sudo systemctl enable aihub
```

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 更新日志

### v1.2.0 (2026-02-11) 🎯 架构优化版本
- ✨ **提供商系统重构**
  - 从Channel模型迁移到Provider模型
  - 自动发现和注册提供商
  - 支持动态模型管理
  - 数据库存储模型配置
- 🔐 **完整的用户认证系统**
  - 邮箱注册和验证
  - 邀请码系统
  - Token管理和配额控制
  - 超级管理员初始化
- 🆕 **新增智谱GLM提供商**
  - 支持glm-4、glm-4-plus等模型
  - 流式响应支持
  - 格式转换器
- 🔧 **转换器系统优化**
  - 统一的BaseConverter基类
  - 支持OpenAI、Claude、Gemini、Kiro、GLM格式
  - 流式响应转换
- 📊 **增强的统计功能**
  - Token使用统计
  - 模型定价配置
  - 用户使用排行
- 🎨 **前端界面改进**
  - 登录/注册页面
  - 邮箱验证页面
  - 风控管理界面优化

### v1.1.0 (2026-02-06) 🛡️ 风控系统版本
- ✨ **新增完整的风控防护系统**
  - 🌐 代理池管理（支持多种协议和绑定策略）
  - ⏱️ 多级速率限制（RPM/TPM限制）
  - 🎭 请求指纹伪装（50+真实浏览器指纹）
  - 💊 账号健康监控（自动降级和恢复）
- 📚 完整的文档系统
  - 风控系统使用文档
  - 代理服务推荐指南
  - 快速开始指南
- 🔧 新增风控管理API
  - 代理池管理接口
  - 健康监控接口
  - 速率限制统计接口

### v1.0.0 (2026-02-05)
- ✨ 初始版本发布
- 🎨 现代化UI设计（亮色/暗色主题）
- 📊 完整的统计分析功能
- 🔄 支持4个主流AI提供商
- 💾 Token统计直接存储到数据库
- 📈 Chart.js可视化图表
- 🔐 完整的Token管理系统
- 🔄 跨分组重试机制
- ⏰ 自动过期清理任务

## 📋 功能状态

### ✅ 已完成功能

#### 1. 提供商系统
- [x] 自动发现和注册提供商
- [x] 支持5个AI提供商（OpenAI、Anthropic、Google Gemini、AWS Kiro、智谱GLM）
- [x] 动态模型管理
- [x] 优先级和权重配置
- [x] 数据库存储配置

#### 2. 用户认证系统
- [x] 邮箱注册和验证
- [x] 邀请码系统
- [x] Token管理和配额控制
- [x] 超级管理员初始化
- [x] 密码加密存储

#### 3. 风控防护系统
- [x] 代理池管理（HTTP/HTTPS/SOCKS4/SOCKS5）
- [x] 四种代理绑定策略（STICKY/RANDOM/ROUND_ROBIN/LEAST_USED）
- [x] 多级速率限制（全局/账号/用户）
- [x] RPM/TPM限制，令牌桶算法
- [x] 请求指纹伪装（50+真实浏览器指纹）
- [x] 账号健康监控（自动降级和恢复）
- [x] 风险等级评估

#### 4. 格式转换系统
- [x] 统一的BaseConverter基类
- [x] OpenAI、Claude、Gemini、Kiro、GLM格式转换
- [x] 流式响应转换
- [x] 请求/响应格式互转

#### 5. 高级功能
- [x] Prompt Cache支持（Claude）
- [x] 上下文压缩（滑动窗口/摘要/混合策略）
- [x] 内容清理（特殊字符、空格规范化、代码格式修复）
- [x] Token精确计算
- [x] 模型定价配置

#### 6. 统计与管理
- [x] 实时统计（请求数、Token消耗、用量趋势）
- [x] 用户使用排行
- [x] 模型使用分布
- [x] 请求日志记录
- [x] 账号批量导入
- [x] 自动刷新用量

#### 7. 前端界面
- [x] 亮色/暗色主题
- [x] 响应式设计
- [x] Chart.js数据可视化
- [x] 登录/注册/验证页面
- [x] 风控管理界面

---

## 📋 TODO 待实现功能

### 🔴 高优先级（核心功能）

#### 1. 模型倍率系统
- [ ] 不同模型不同计费倍率
- [ ] 内置价格表（GPT-4: 15倍，GPT-3.5: 1倍等）
- [ ] 自定义倍率配置
- [ ] 成本计算优化

#### 2. 模型映射功能
- [ ] 请求模型映射到实际模型
- [ ] gpt-4 → gpt-4-turbo 自动映射
- [ ] 成本优化配置
- [ ] 透明切换

#### 3. 负载均衡增强
- [x] 权重配置（已完成）
- [x] 优先级调度（已完成）
- [ ] 响应时间优化
- [ ] 最少使用策略

#### 4. 健康检查系统
- [ ] 自动测试提供商可用性
- [ ] 响应时间统计
- [ ] 自动禁用故障提供商
- [ ] 余额查询

### 🟡 中优先级（增强功能）

#### 5. 更多AI提供商
- [ ] Azure OpenAI
- [ ] AWS Bedrock
- [ ] Vertex AI
- [ ] 文心一言
- [ ] 通义千问
- [ ] 讯飞星火
- [ ] Kimi
- [ ] DeepSeek
- [ ] Moonshot
- [ ] Baichuan
- [ ] Minimax
- [ ] Doubao

#### 6. 更多API接口
- [ ] Images (DALL-E)
- [ ] Audio (Whisper, TTS)
- [ ] Video (Sora)
- [ ] Embeddings
- [ ] Rerank
- [ ] Realtime API (WebSocket)

#### 7. 提供商增强功能
- [ ] 多Key支持
- [ ] 参数覆盖
- [ ] Header覆盖
- [ ] 状态码映射
- [ ] 自动封禁机制

#### 8. 审计与日志
- [ ] 管理操作记录
- [ ] 操作类型分类
- [ ] 日志导出功能
- [ ] 日志搜索过滤

#### 9. 预算与告警
- [ ] 配额不足提醒
- [ ] Token使用告警
- [ ] 邮件通知
- [ ] Webhook通知

### 🟢 低优先级（可选功能）

#### 10. 支付系统
- [ ] 在线充值（易支付）
- [ ] Stripe集成
- [ ] 兑换码系统
- [ ] 充值记录

#### 11. 用户认证增强
- [ ] GitHub OAuth
- [ ] Discord OAuth
- [ ] 2FA双因素认证
- [ ] OIDC统一认证

#### 12. 缓存机制
- [ ] 相同请求缓存
- [ ] Redis集成
- [ ] 缓存策略配置

#### 13. 监控集成
- [ ] Prometheus监控
- [ ] 健康检查端点
- [ ] 性能指标导出

#### 14. Docker部署
- [ ] Dockerfile
- [ ] Docker Compose
- [ ] 多架构支持

#### 15. 前端优化
- [ ] 响应式设计优化
- [ ] 移动端适配
- [ ] 国际化支持
- [ ] 更多图表类型

#### 16. 数据导出
- [ ] 统计数据导出
- [ ] 日志导出
- [ ] 报表生成
- [ ] CSV/Excel格式

## 🎯 开发路线图

### Phase 1: 核心功能完善（当前）
1. ✅ 提供商系统重构
2. ✅ 用户认证系统
3. ✅ 风控防护系统
4. ✅ 格式转换系统
5. ✅ 高级功能（Prompt Cache、上下文压缩）
6. 🔄 模型倍率配置
7. 🔄 模型映射功能
8. 🔄 健康检查系统

### Phase 2: 功能扩展（中期）
1. 更多AI提供商接入
2. 更多API接口支持
3. 提供商增强功能
4. 审计与日志系统
5. 预算告警功能

### Phase 3: 生态完善（长期）
1. 支付系统集成
2. 监控与运维工具
3. Docker部署支持
4. 前端体验优化
5. 数据分析增强

---

## 📚 相关文档

- [缓存功能文档](./CACHE_FEATURES.md) - Prompt Cache和上下文压缩
- [实现总结](./IMPLEMENTATION_SUMMARY.md) - 技术实现细节

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License
