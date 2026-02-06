# AiHub - AI Gateway 管理平台

一个统一的AI模型网关管理平台，支持多个AI提供商（OpenAI、Anthropic、Google、Kiro）的账号管理、负载均衡和使用统计。

## 功能特性

### 核心功能
- 🔄 **多提供商支持**：OpenAI、Anthropic、Google Gemini、AWS Kiro
- 🎯 **智能负载均衡**：自动选择可用账号，支持优先级配置
- 📊 **实时统计**：请求数、Token消耗、用量趋势可视化
- 🔐 **用户管理**：API Key管理、配额控制
- 💳 **账号池管理**：批量导入、用量监控、自动刷新

### 🛡️ 风控防护系统（NEW）
- 🌐 **代理池管理**：支持HTTP/SOCKS5，智能IP轮换，防止IP封禁
- ⏱️ **多级速率限制**：全局/账号/用户三级限流，防止触发API限制
- 🎭 **指纹伪装**：50+真实浏览器指纹，模拟真实用户行为
- 💊 **健康监控**：实时监控账号状态，自动降级和恢复
- 📈 **风险检测**：智能识别异常，自动调整策略

### 管理功能
- **渠道管理**：配置不同AI提供商的渠道
- **账号管理**：管理每个渠道的API账号池
- **用户管理**：创建用户、分配配额
- **统计分析**：请求趋势、Token消耗、Top用户排行

### 界面特性
- 🌓 **亮色/暗色主题**：自动适配用户偏好
- 📱 **响应式设计**：支持桌面和移动端
- 📈 **数据可视化**：Chart.js图表展示趋势
- 🎨 **现代化UI**：卡片式设计、进度条展示

## 快速开始

### 环境要求
- Python 3.10+
- aiohttp
- aiosqlite

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd AiHub

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑.env文件，设置ADMIN_KEY

# 启动服务
python main.py
```

### 访问

打开浏览器访问：`http://localhost:8000`

首次访问需要输入管理密钥（在.env中配置的ADMIN_KEY）

### 🛡️ 启用风控系统（推荐用于生产环境）

```bash
# 1. 复制配置模板
cp risk_control_config.json.example risk_control_config.json

# 2. 编辑配置文件，启用所需功能
# 3. 重启服务
python main.py
```

详细配置请参考：[风控系统快速开始](./docs/QUICK_START_RISK_CONTROL.md)

## 项目结构

```
AiHub/
├── models/          # 数据模型（Account, Channel, User, Log）
├── providers/       # AI提供商实现
├── server/          # Web服务器（API, Routes, Middleware）
├── converters/      # 请求/响应格式转换
├── utils/           # 工具函数（Logger, Token计算）
├── static/          # 前端静态文件
├── logs/            # 日志文件
├── main.py          # 入口文件
└── config.py        # 配置文件
```

## API文档

### 认证
所有API请求需要在Header中包含：
```
X-Admin-Key: <your-admin-key>
```

### 主要端点

#### 渠道管理
- `GET /api/channels` - 获取所有渠道
- `POST /api/channels` - 创建渠道
- `PUT /api/channels/{id}` - 更新渠道
- `DELETE /api/channels/{id}` - 删除渠道

#### 账号管理
- `GET /api/channels/{id}/accounts` - 获取渠道账号
- `POST /api/channels/{id}/accounts` - 添加账号
- `POST /api/channels/{id}/accounts/import` - 批量导入
- `POST /api/accounts/{id}/refresh-usage` - 刷新用量

#### 用户管理
- `GET /api/users` - 获取所有用户
- `POST /api/users` - 创建用户
- `DELETE /api/users/{id}` - 删除用户

#### 统计数据
- `GET /api/stats?days=7` - 获取统计数据
- `GET /api/logs` - 获取请求日志

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
# 管理密钥
ADMIN_KEY=your-secret-key

# 数据库路径
DATABASE_PATH=aihub.db

# 服务器配置
HOST=0.0.0.0
PORT=8000
```

### 支持的AI提供商

#### OpenAI
- 模型：gpt-4, gpt-4-turbo, gpt-3.5-turbo等
- 需要：API Key

#### Anthropic
- 模型：claude-3-opus, claude-3-sonnet等
- 需要：API Key

#### Google Gemini
- 模型：gemini-pro, gemini-pro-vision等
- 需要：API Key

#### AWS Kiro (CodeWhisperer)
- 模型：基于Claude的模型
- 需要：AWS Builder ID认证
- 支持：自动刷新用量、免费额度统计

## 开发

### 添加新的AI提供商

1. 在`providers/`目录创建新文件
2. 继承`BaseProvider`类
3. 实现`chat()`方法
4. 在`providers/__init__.py`中注册

### 运行测试

```bash
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

## 📋 TODO 待实现功能

### ✅ 已完成功能

#### 1. 风控防护系统 ✅
- [x] 代理池管理（支持HTTP/HTTPS/SOCKS5/SOCKS4）
- [x] 四种代理绑定策略（STICKY/RANDOM/ROUND_ROBIN/LEAST_USED）
- [x] 自动代理健康检查
- [x] 多级速率限制（全局/账号/用户）
- [x] RPM/TPM限制
- [x] 令牌桶算法实现
- [x] 请求指纹伪装（50+真实浏览器指纹）
- [x] User-Agent轮换
- [x] Chrome Client Hints支持
- [x] 账号健康度监控
- [x] 自动降级和恢复
- [x] 风险等级评估
- [x] 完整的管理API

### 🔴 高优先级（核心功能）

#### 2. 模型倍率系统
- [ ] 不同模型不同计费倍率
- [ ] 内置价格表（GPT-4: 15倍，GPT-3.5: 1倍等）
- [ ] 自定义倍率配置
- [ ] 成本计算优化

#### 3. 模型映射功能
- [ ] 请求模型映射到实际模型
- [ ] gpt-4 → gpt-4-turbo 自动映射
- [ ] 成本优化配置
- [ ] 透明切换

#### 4. 负载均衡增强
- [ ] 权重配置
- [ ] 优先级调度
- [ ] 响应时间优化
- [ ] 最少使用策略

#### 5. 健康检查系统
- [ ] 自动测试渠道可用性
- [ ] 响应时间统计
- [ ] 自动禁用故障渠道
- [ ] 余额查询

### 🟡 中优先级（增强功能）

#### 6. 更多AI提供商
- [ ] Azure OpenAI
- [ ] AWS Bedrock
- [ ] Vertex AI
- [ ] 文心一言
- [ ] 通义千问
- [ ] 讯飞星火
- [ ] 智谱AI
- [ ] Kimi
- [ ] DeepSeek
- [ ] Moonshot
- [ ] Baichuan
- [ ] Minimax
- [ ] Doubao

#### 7. 更多API接口
- [ ] Images (DALL-E)
- [ ] Audio (Whisper, TTS)
- [ ] Video (Sora)
- [ ] Embeddings
- [ ] Rerank
- [ ] Realtime API (WebSocket)

#### 8. 渠道增强功能
- [ ] 多Key支持
- [ ] 参数覆盖
- [ ] Header覆盖
- [ ] 状态码映射
- [ ] 自动封禁机制

#### 9. 审计与日志
- [ ] 管理操作记录
- [ ] 操作类型分类
- [ ] 日志导出功能
- [ ] 日志搜索过滤

#### 10. 预算与告警
- [ ] 配额不足提醒
- [ ] Token使用告警
- [ ] 邮件通知
- [ ] Webhook通知

### 🟢 低优先级（可选功能）

#### 11. 支付系统
- [ ] 在线充值（易支付）
- [ ] Stripe集成
- [ ] 兑换码系统
- [ ] 充值记录

#### 12. 用户认证增强
- [ ] GitHub OAuth
- [ ] Discord OAuth
- [ ] 2FA双因素认证
- [ ] OIDC统一认证

#### 13. 缓存机制
- [ ] 相同请求缓存
- [ ] Redis集成
- [ ] 缓存策略配置

#### 14. 监控集成
- [ ] Prometheus监控
- [ ] 健康检查端点
- [ ] 性能指标导出

#### 15. Docker部署
- [ ] Dockerfile
- [ ] Docker Compose
- [ ] 多架构支持

#### 16. Token功能增强
- [ ] Token使用趋势图表
- [ ] Token批量操作
- [ ] Token使用配额预警
- [ ] Token使用日志详情

#### 17. 前端优化
- [ ] 响应式设计优化
- [ ] 移动端适配
- [ ] 国际化支持
- [ ] 更多图表类型

#### 18. 数据导出
- [ ] 统计数据导出
- [ ] 日志导出
- [ ] 报表生成
- [ ] CSV/Excel格式

## 🎯 开发路线图

### Phase 1: 核心功能完善（优先）
1. 速率限制系统
2. 模型倍率配置
3. 模型映射功能
4. 健康检查系统
5. 负载均衡增强

### Phase 2: 功能扩展（中期）
1. 更多AI提供商接入
2. 更多API接口支持
3. 渠道增强功能
4. 审计与日志系统
5. 预算告警功能

### Phase 3: 生态完善（长期）
1. 支付系统集成
2. 监控与运维工具
3. Docker部署支持
4. 前端体验优化
5. 数据分析增强

---

## 📚 文档

### 核心文档
- [风控系统快速开始](./docs/QUICK_START_RISK_CONTROL.md) - 5分钟快速部署
- [风控系统使用文档](./docs/RISK_CONTROL_GUIDE.md) - 完整功能说明
- [代理服务推荐指南](./docs/PROXY_SERVICES_GUIDE.md) - 代理服务商选择

### 参考文档
- [与New-API功能对比](./COMPARISON_WITH_NEW_API.md)
- [Token实现文档](./TOKEN_IMPLEMENTATION.md)
- [UI/UX改进文档](./UI_UX_IMPROVEMENTS.md)
- [项目结构文档](./PROJECT_STRUCTURE.md)
