# AiHub vs New-API 详细对比分析

基于本地 E:/new-api 项目的实际代码分析

---

## 📊 核心架构对比

| 维度 | AiHub | New-API |
|------|-------|---------|
| **语言** | Python 3.14 + aiohttp | Go 1.x + Gin |
| **数据库** | SQLite (aiosqlite) | SQLite/MySQL/PostgreSQL (GORM) |
| **缓存** | 无 | Redis (可选) |
| **前端** | 原生JS + Chart.js | React + Ant Design |
| **部署** | 直接运行 | Docker + 二进制 |
| **代码量** | ~5000行 | ~50000行+ |

---

## 🔍 功能详细对比

### 1. 令牌(Token)管理系统 🔴

#### New-API 的 Token 模型
```go
type Token struct {
    Id                 int
    UserId             int
    Key                string         // sk-xxx格式
    Status             int            // 1启用 2禁用 3已用尽 4已过期
    Name               string
    CreatedTime        int64
    AccessedTime       int64
    ExpiredTime        int64          // -1表示永不过期
    RemainQuota        int            // 剩余额度
    UnlimitedQuota     bool           // 无限额度
    ModelLimitsEnabled bool           // 模型限制开关
    ModelLimits        string         // 可用模型列表
    AllowIps           *string        // IP白名单
    UsedQuota          int            // 已用额度
    Group              string         // 令牌分组
    CrossGroupRetry    bool           // 跨分组重试
}
```

#### AiHub 的 User 模型
```python
class User:
    id: int
    username: str
    api_key: str              # 简单的API Key
    quota: int                # 配额
    enabled: int              # 启用状态
    created_at: datetime
    input_tokens: int         # 输入token统计
    output_tokens: int        # 输出token统计
    total_tokens: int         # 总token统计
```

**差距：**
- ❌ 缺少令牌过期时间
- ❌ 缺少无限额度选项
- ❌ 缺少模型限制功能
- ❌ 缺少IP白名单
- ❌ 缺少令牌分组
- ❌ 缺少跨分组重试
- ❌ 缺少令牌状态管理（已用尽、已过期等）

---

### 2. 渠道(Channel)管理系统 🔴

#### New-API 的 Channel 模型
```go
type Channel struct {
    Id                 int
    Type               int            // 渠道类型（OpenAI/Claude/Gemini等）
    Key                string         // API Key（支持多Key）
    Status             int            // 状态
    Name               string
    Weight             *uint          // 权重（负载均衡）
    ResponseTime       int            // 响应时间（ms）
    BaseURL            *string        // 自定义Base URL
    Balance            float64        // 余额（USD）
    BalanceUpdatedTime int64
    Models             string         // 支持的模型列表
    Group              string         // 渠道分组
    UsedQuota          int64          // 已用额度
    ModelMapping       *string        // 模型映射配置
    StatusCodeMapping  *string        // 状态码映射
    Priority           *int64         // 优先级
    AutoBan            *int           // 自动封禁
    Tag                *string        // 标签
    Setting            *string        // 额外设置
    ParamOverride      *string        // 参数覆盖
    HeaderOverride     *string        // Header覆盖
    ChannelInfo        ChannelInfo    // 多Key信息
}

type ChannelInfo struct {
    IsMultiKey             bool
    MultiKeySize           int
    MultiKeyStatusList     map[int]int      // 每个Key的状态
    MultiKeyDisabledReason map[int]string   // 禁用原因
    MultiKeyDisabledTime   map[int]int64    // 禁用时间
    MultiKeyPollingIndex   int              // 轮询索引
    MultiKeyMode           constant.MultiKeyMode
}
```

#### AiHub 的 Channel 模型
```python
class Channel:
    id: int
    name: str
    type: str              # openai/claude/gemini/kiro
    models: str            # JSON字符串
    enabled: int
    priority: int
    created_at: datetime
```

**差距：**
- ❌ 缺少权重配置（负载均衡）
- ❌ 缺少响应时间统计
- ❌ 缺少余额查询
- ❌ 缺少模型映射功能
- ❌ 缺少状态码映射
- ❌ 缺少自动封禁机制
- ❌ 缺少多Key支持
- ❌ 缺少参数/Header覆盖
- ❌ 缺少渠道分组

---

### 3. 账号(Account)管理系统 🟡

#### New-API
- 渠道内的多个Key作为账号池
- 支持多Key轮询、随机、优先级等策略
- 自动健康检查和故障转移
- Key级别的状态管理

#### AiHub
```python
class Account:
    id: int
    channel_id: int
    name: str
    api_key: str
    enabled: int
    usage: int             # Kiro用量
    limit: int             # Kiro限额
    input_tokens: int
    output_tokens: int
    total_tokens: int
    created_at: datetime
```

**差距：**
- ❌ 缺少健康检查机制
- ❌ 缺少自动故障转移
- ❌ 缺少响应时间统计
- ✅ 有Token统计（New-API在Log中）
- ✅ 有Kiro用量管理（New-API没有）

---

### 4. 负载均衡与调度 🔴

#### New-API 的调度策略
```go
// relay/helper/channel.go
- 权重随机选择
- 优先级排序
- 响应时间优化
- 失败自动重试
- 跨分组重试
- 模型回退机制
```

#### AiHub 的调度
```python
# models/account.py
async def get_available_account(channel_id):
    # 简单随机选择
    accounts = await get_accounts_by_channel(channel_id)
    enabled = [a for a in accounts if a.enabled]
    return random.choice(enabled) if enabled else None
```

**差距：**
- ❌ 缺少权重配置
- ❌ 缺少优先级调度
- ❌ 缺少响应时间优化
- ❌ 缺少失败重试机制
- ❌ 缺少模型回退

---

### 5. 速率限制 🔴

#### New-API
```go
// middleware/rate_limit.go
- RPM (Requests Per Minute)
- TPM (Tokens Per Minute)
- 用户级别限制
- 令牌级别限制
- Redis分布式限流
```

#### AiHub
- ❌ 完全没有速率限制

**建议实现：**
```python
class RateLimiter:
    def __init__(self):
        self.user_requests = {}  # {user_id: [(timestamp, tokens)]}
    
    async def check_limit(self, user_id, rpm=60, tpm=100000):
        now = time.time()
        # 清理过期记录
        if user_id in self.user_requests:
            self.user_requests[user_id] = [
                (ts, tokens) for ts, tokens in self.user_requests[user_id]
                if now - ts < 60
            ]
        
        # 检查RPM
        if len(self.user_requests.get(user_id, [])) >= rpm:
            raise web.HTTPTooManyRequests(text="RPM limit exceeded")
        
        # 检查TPM
        total = sum(t for _, t in self.user_requests.get(user_id, []))
        if total >= tpm:
            raise web.HTTPTooManyRequests(text="TPM limit exceeded")
```

---

### 6. 模型倍率系统 🔴

#### New-API
```go
// model/pricing.go
type ModelPrice struct {
    Model              string
    Type               string  // 按次/按量
    ChannelType        int
    Input              float64 // 输入价格
    Output             float64 // 输出价格
    CompletionRatio    float64 // 倍率
}

// 内置价格表
var DefaultModelPrices = map[string]*ModelPrice{
    "gpt-4": {Input: 0.03, Output: 0.06, CompletionRatio: 15},
    "gpt-3.5-turbo": {Input: 0.0015, Output: 0.002, CompletionRatio: 1},
    "claude-3-opus": {Input: 0.015, Output: 0.075, CompletionRatio: 15},
}
```

#### AiHub
- ❌ 没有模型倍率系统
- ❌ 所有模型按相同价格计费

**建议实现：**
```python
MODEL_RATES = {
    "gpt-4": {"input": 0.03, "output": 0.06, "ratio": 15},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03, "ratio": 10},
    "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002, "ratio": 1},
    "claude-3-opus": {"input": 0.015, "output": 0.075, "ratio": 15},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015, "ratio": 3},
    "gemini-pro": {"input": 0.00025, "output": 0.0005, "ratio": 2},
}

def calculate_cost(model, input_tokens, output_tokens):
    rate = MODEL_RATES.get(model, {"ratio": 1})
    return (input_tokens + output_tokens) * rate["ratio"]
```

---

### 7. 模型映射 🔴

#### New-API
```go
// 支持模型映射配置
{
    "gpt-4": "gpt-4-turbo-2024-04-09",
    "gpt-3.5-turbo": "gpt-3.5-turbo-0125",
    "claude-3-opus": "claude-3-opus-20240229"
}
```

#### AiHub
- ❌ 没有模型映射功能

**建议实现：**
```python
# models/channel.py
class Channel:
    model_mapping: dict  # {"gpt-4": "gpt-4-turbo"}

def map_model(channel, requested_model):
    if channel.model_mapping:
        return channel.model_mapping.get(requested_model, requested_model)
    return requested_model
```

---

### 8. 重试与降级机制 🔴

#### New-API
```go
// relay/helper/retry.go
func RelayWithRetry(c *gin.Context, maxRetries int) {
    for i := 0; i < maxRetries; i++ {
        err := doRelay(c)
        if err == nil {
            return
        }
        
        // 标记渠道不健康
        MarkChannelUnhealthy(channelId)
        
        // 尝试其他渠道
        if i < maxRetries-1 {
            channel = GetNextChannel()
            continue
        }
    }
}
```

#### AiHub
- ❌ 没有重试机制
- ❌ 没有降级策略
- ❌ 失败后不会自动切换账号

**建议实现：**
```python
async def chat_with_retry(ctx, max_retries=3):
    for attempt in range(max_retries):
        try:
            account = await get_available_account(ctx.channel_id)
            if not account:
                raise Exception("No available account")
            
            provider = get_provider(ctx.channel.type)
            async for chunk in provider.chat(account.api_key, ctx.model, ctx.body):
                yield chunk
            return
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            
            # 标记账号不健康
            await mark_account_unhealthy(account.id)
            
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # 等待1秒后重试
                continue
            raise
```

---

### 9. 健康检查与监控 🔴

#### New-API
```go
// controller/channel-test.go
- 定期测试渠道可用性
- 响应时间统计
- 自动禁用故障渠道
- 余额查询
- Prometheus监控
```

#### AiHub
- ❌ 没有自动健康检查
- ❌ 没有响应时间统计
- ❌ 没有自动禁用机制
- ✅ 有Kiro用量刷新

**建议实现：**
```python
async def health_check_task():
    while True:
        channels = await get_all_channels()
        for channel in channels:
            if not channel.enabled:
                continue
            
            try:
                # 测试渠道
                start = time.time()
                await test_channel(channel)
                response_time = int((time.time() - start) * 1000)
                
                # 更新响应时间
                await update_channel_response_time(channel.id, response_time)
                
            except Exception as e:
                logger.error(f"Channel {channel.name} health check failed: {e}")
                # 自动禁用
                await disable_channel(channel.id, reason=str(e))
        
        await asyncio.sleep(300)  # 每5分钟检查一次
```

---

### 10. 支付与充值系统 🟡

#### New-API
```go
// controller/topup.go
- 易支付集成
- Stripe集成
- 兑换码系统
- 充值记录
- 余额管理
```

#### AiHub
- ❌ 没有支付系统
- ❌ 没有充值功能
- ✅ 有简单的配额管理

---

### 11. 用户认证系统 🟡

#### New-API
```go
// controller/
- 用户名密码登录
- GitHub OAuth
- Discord OAuth
- LinuxDO OAuth
- Telegram OAuth
- OIDC统一认证
- 2FA双因素认证
- Passkey支持
```

#### AiHub
- ✅ 管理密钥认证
- ❌ 没有OAuth
- ❌ 没有2FA

---

### 12. 日志与审计 🟡

#### New-API
```go
type Log struct {
    Id               int
    UserId           int
    CreatedAt        int64
    Type             int     // 1消费 2充值 3管理
    Content          string
    Username         string
    TokenName        string
    ModelName        string
    Quota            int
    PromptTokens     int
    CompletionTokens int
    ChannelId        int
}
```

#### AiHub
```python
class Log:
    id: int
    user_id: int
    channel_id: int
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    status: int
    created_at: datetime
```

**差距：**
- ❌ 缺少操作类型分类
- ❌ 缺少审计日志
- ❌ 缺少管理操作记录
- ✅ 有请求日志

---

### 13. 数据统计与可视化 🟡

#### New-API
- 实时数据看板
- 用量趋势图表
- 模型使用统计
- 渠道性能分析
- 用户消费排行
- 收入统计

#### AiHub
- ✅ 基础统计图表（Chart.js）
- ✅ 小时趋势
- ✅ Top用户
- ✅ 渠道统计
- ❌ 缺少收入统计
- ❌ 缺少模型分析

---

### 14. 提供商支持对比 🔴

| 提供商 | AiHub | New-API |
|--------|-------|---------|
| OpenAI | ✅ | ✅ |
| Azure OpenAI | ❌ | ✅ |
| Claude (Anthropic) | ✅ | ✅ |
| Google Gemini | ✅ | ✅ |
| AWS Bedrock | ❌ | ✅ |
| Vertex AI | ❌ | ✅ |
| 文心一言 | ❌ | ✅ |
| 通义千问 | ❌ | ✅ |
| 讯飞星火 | ❌ | ✅ |
| 智谱AI | ❌ | ✅ |
| Kimi | ❌ | ✅ |
| DeepSeek | ❌ | ✅ |
| Moonshot | ❌ | ✅ |
| Baichuan | ❌ | ✅ |
| Minimax | ❌ | ✅ |
| Doubao | ❌ | ✅ |
| Ollama | ❌ | ✅ |
| Cohere | ❌ | ✅ |
| Kiro | ✅ | ✅ |
| Midjourney | ❌ | ✅ |
| Suno | ❌ | ✅ |
| Dify | ❌ | ✅ |

**AiHub支持：4个**
**New-API支持：25+个**

---

### 15. API接口支持 🟡

#### New-API
- ✅ Chat Completions
- ✅ Responses (OpenAI新格式)
- ✅ Realtime API (WebSocket)
- ✅ Images (DALL-E)
- ✅ Audio (Whisper, TTS)
- ✅ Video (Sora)
- ✅ Embeddings
- ✅ Rerank
- ✅ Claude Messages
- ✅ Gemini Format

#### AiHub
- ✅ Chat Completions (流式)
- ❌ Responses
- ❌ Realtime API
- ❌ Images
- ❌ Audio
- ❌ Video
- ❌ Embeddings
- ❌ Rerank

---

### 16. 格式转换 🟡

#### New-API
```go
// relay/adaptor/
- OpenAI ⇄ Claude
- OpenAI → Gemini
- Gemini → OpenAI
- OpenAI ⇄ 国内大模型
- 思考内容转换
```

#### AiHub
```python
# converters/
- OpenAI → Claude ✅
- OpenAI → Gemini ✅
- OpenAI → Kiro ✅
- 反向转换 ❌
```

---

### 17. 部署与运维 🟡

#### New-API
- ✅ Docker镜像
- ✅ Docker Compose
- ✅ 二进制文件
- ✅ Systemd服务
- ✅ 环境变量配置
- ✅ 数据库迁移
- ✅ 健康检查端点
- ✅ Prometheus监控
- ✅ 优雅关闭

#### AiHub
- ❌ 没有Docker
- ❌ 没有二进制
- ✅ 直接运行
- ✅ 环境变量
- ✅ 数据库迁移
- ❌ 没有健康检查
- ❌ 没有监控
- ❌ 没有优雅关闭

---

## 📈 性能对比

| 指标 | AiHub (Python) | New-API (Go) |
|------|----------------|--------------|
| 启动时间 | ~1秒 | ~0.1秒 |
| 内存占用 | ~50MB | ~20MB |
| 并发处理 | 中等 (asyncio) | 高 (goroutine) |
| 请求延迟 | 中等 | 低 |
| CPU使用 | 中等 | 低 |

---

## 🎯 优先级改进建议

### 🔴 高优先级（核心功能，必须实现）

1. **令牌管理系统**
   - 令牌过期时间
   - 无限额度选项
   - 模型限制
   - IP白名单
   - 令牌分组

2. **速率限制**
   - RPM限制
   - TPM限制
   - 用户级别限流

3. **重试机制**
   - 失败自动重试
   - 账号故障转移
   - 健康状态管理

4. **模型倍率**
   - 不同模型不同计费
   - 价格配置

5. **模型映射**
   - 请求模型映射到实际模型
   - 成本优化

### 🟡 中优先级（增强功能）

6. **负载均衡**
   - 权重配置
   - 优先级调度
   - 响应时间优化

7. **健康检查**
   - 自动测试渠道
   - 响应时间统计
   - 自动禁用故障渠道

8. **渠道增强**
   - 多Key支持
   - 参数覆盖
   - 状态码映射

9. **更多提供商**
   - Azure OpenAI
   - 国内大模型（通义千问、文心一言等）

10. **审计日志**
    - 管理操作记录
    - 操作类型分类

### 🟢 低优先级（可选功能）

11. **支付系统**
    - 在线充值
    - 兑换码

12. **OAuth认证**
    - GitHub/Discord登录
    - 2FA

13. **Docker部署**
    - Dockerfile
    - Docker Compose

14. **监控集成**
    - Prometheus
    - 健康检查端点

15. **更多API**
    - Images
    - Audio
    - Embeddings

---

## ✅ AiHub的优势

虽然功能不如New-API完善，但AiHub也有独特优势：

### 1. **Python生态**
- 易于学习和维护
- 丰富的第三方库
- 快速开发迭代

### 2. **轻量级**
- 代码简洁（~5000行 vs 50000行+）
- 易于理解和定制
- 无需编译

### 3. **Kiro深度集成**
- 完善的Kiro支持
- 用量自动刷新
- 免费额度统计

### 4. **现代UI**
- 美观的卡片式设计
- 亮色/暗色主题
- 响应式布局

### 5. **快速部署**
- 无需Docker
- 直接运行
- 配置简单

---

## 🚀 实施路线图

### Phase 1: 核心功能（2-3周）

**Week 1: 令牌系统**
- [ ] Token过期时间
- [ ] 无限额度
- [ ] 模型限制
- [ ] IP白名单

**Week 2: 速率限制与重试**
- [ ] RPM/TPM限制
- [ ] 失败重试机制
- [ ] 健康状态管理

**Week 3: 计费系统**
- [ ] 模型倍率配置
- [ ] 模型映射
- [ ] 成本计算

### Phase 2: 增强功能（2-3周）

**Week 4: 负载均衡**
- [ ] 权重配置
- [ ] 优先级调度
- [ ] 响应时间统计

**Week 5: 健康检查**
- [ ] 自动测试任务
- [ ] 故障自动禁用
- [ ] 余额查询

**Week 6: 渠道增强**
- [ ] 多Key支持
- [ ] 参数覆盖
- [ ] 更多提供商

### Phase 3: 可选功能（按需）

- [ ] Docker部署
- [ ] 支付系统
- [ ] OAuth认证
- [ ] 监控集成
- [ ] 更多API接口

---

## 📝 总结

### 当前状态
AiHub已经实现了AI网关的**基础功能**，适合：
- 个人使用
- 小团队（<10人）
- 学习和研究
- 快速原型

### 主要差距
与New-API相比，主要缺少：
1. **企业级功能**（令牌管理、速率限制、重试机制）
2. **高级调度**（负载均衡、健康检查、故障转移）
3. **完善的计费**（模型倍率、价格配置）
4. **更多提供商**（国内大模型、Azure等）

### 发展建议

**如果目标是个人/小团队使用：**
- 当前功能已经足够
- 可以按需添加Phase 1的核心功能

**如果目标是企业级应用：**
- 必须实现Phase 1的所有功能
- 建议实现Phase 2的增强功能
- 考虑使用Go重写以提升性能

**如果想保持轻量级：**
- 专注核心功能，不要盲目追求功能完整性
- 保持代码简洁易懂
- 发挥Python生态优势

---

## 🎯 推荐优先实现的5个功能

基于实用性和重要性，建议优先实现：

1. **速率限制** - 防止滥用，保护系统
2. **重试机制** - 提高可用性和稳定性
3. **模型倍率** - 合理计费，成本控制
4. **令牌过期** - 安全管理，权限控制
5. **健康检查** - 自动化运维，减少人工干预

这5个功能实现后，AiHub将具备**生产环境**的基本要求。
