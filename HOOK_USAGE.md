# Hook 通知使用说明

## 功能概述

当监控系统检测到买卖信号时，会自动发送 HTTP POST 请求到配置的 Hook URL，实现实时通知。

## 配置方法

### 1. 通过 Web 面板配置（推荐）

1. 访问 http://localhost:8701
2. 在左侧边栏找到"通知配置"区域
3. 填写相应的 Webhook URL
4. 点击"保存配置"

### 2. 直接编辑 config.yaml

```yaml
notification:
  console: true
  dingtalk_secret: 'SEC...'          # 钉钉签名 secret（以 SEC 开头）
  dingtalk_webhook: 'https://...'    # 钉钉 Webhook URL
  enabled: true
  hook_url: 'http://localhost:3000/notify'
  signal_threshold: 0.5
  wechat_webhook: ''
```

## 钉钉机器人配置详解

### 获取 Webhook 和 Secret

1. 在钉钉群聊中点击右上角设置
2. 选择"智能群助手" → "添加机器人"
3. 选择"自定义"（通过 Webhook 接入）
4. 设置机器人名称
5. **安全设置** 选择"签名"（推荐）
6. 复制生成的 Webhook URL 和 Secret

### Webhook URL 格式

```
https://oapi.dingtalk.com/robot/send?access_token=YOUR_ACCESS_TOKEN
```

### Secret 格式

```
SECxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

以 `SEC` 开头的字符串，用于 HMAC-SHA256 签名。

## Hook 数据格式

当有买卖信号时，系统会发送如下 JSON 数据：

```json
{
  "event": "trading_signal",
  "stock_code": "000001",
  "stock_name": "平安银行",
  "signal_type": "buy",
  "signal_score": 0.72,
  "decision": "买入",
  "price": 10.31,
  "reason": "买分=0.72, 卖分=0.25, RSI=45, 止损=3.8%, 止盈=9.5%",
  "timestamp": "2026-03-23 16:30:00"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| event | string | 事件类型，固定为 `trading_signal` |
| stock_code | string | 股票代码（6 位数字） |
| stock_name | string | 股票名称 |
| signal_type | string | 信号类型：`buy`/`sell`/`hold` |
| signal_score | float | 信号得分（0-1 之间） |
| decision | string | 决策结果：`买入`/`卖出`/`持有`等 |
| price | float | 当前价格 |
| reason | string | 信号原因详情 |
| timestamp | string | 时间戳（YYYY-MM-DD HH:MM:SS 格式） |

## 示例接收器

### Python Flask 示例

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/notify', methods=['POST'])
def notify():
    data = request.json
    print(f"收到信号：{data['stock_code']} - {data['decision']}")
    print(f"股票：{data['stock_name']}")
    print(f"价格：{data['price']}")
    print(f"原因：{data['reason']}")

    # 在这里添加你的处理逻辑
    # 例如：发送邮件、短信、推送到手机等

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
```

### Node.js Express 示例

```javascript
const express = require('express');
const app = express();

app.use(express.json());

app.post('/notify', (req, res) => {
    const data = req.body;
    console.log(`收到信号：${data.stock_code} - ${data.decision}`);
    console.log(`股票：${data.stock_name}`);
    console.log(`价格：${data.price}`);
    console.log(`原因：${data.reason}`);

    // 在这里添加你的处理逻辑
    res.json({ status: 'ok' });
});

app.listen(3000, () => {
    console.log('Hook 接收器运行在端口 3000');
});
```

### 使用 Serverless 函数（Vercel/Netlify）

```javascript
// api/notify.js
export default function handler(req, res) {
    if (req.method === 'POST') {
        const data = req.body;

        // 处理信号通知
        console.log('交易信号:', data);

        // 可以转发到其他服务，如：
        // - 发送邮件（使用 SendGrid、Mailgun 等）
        // - 发送短信（使用 Twilio 等）
        // - 推送到 Slack、Discord 等

        res.status(200).json({ status: 'ok' });
    } else {
        res.status(405).json({ error: 'Method not allowed' });
    }
}
```

## 使用场景

1. **实时推送通知**
   - 推送到手机（使用 Pushover、Bark 等）
   - 发送到即时通讯工具（Telegram、WhatsApp 等）

2. **数据记录与分析**
   - 记录所有信号到数据库
   - 进行信号准确性分析

3. **自动化交易**
   - 连接到券商 API 执行自动交易
   - 发送指令到交易机器人

4. **告警升级**
   - 强烈买入/卖出信号电话通知
   - 普通信号仅记录或推送

## 注意事项

1. **网络可达性**: Hook URL 必须是监控系统可以访问的地址
   - 本地测试可用 `http://localhost:3000/notify`
   - 生产环境建议使用公网地址或内网穿透

2. **响应要求**: 接收器应返回 HTTP 200 状态码表示成功接收

3. **超时设置**: 请求超时时间为 10 秒，请确保接收器能快速响应

4. **安全性**:
   - 建议使用 HTTPS
   - 可在 Hook URL 中添加 token 进行验证
   - 例如：`https://your-domain.com/notify?token=your-secret-token`

5. **重试机制**: 发送失败不会重试，请确保接收器稳定

## 多 Hook 支持

系统同时支持多种通知方式，可同时配置：
- `hook_url`: 通用 Webhook
- `wechat_webhook`: 企业微信机器人
- `dingtalk_webhook`: 钉钉机器人

所有配置的通知方式都会同时收到消息。
