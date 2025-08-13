import datetime

# 内嵌的默认 Schema
_DEFAULT_SCHEMA = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Energyfy Config Schema",
  "type": "object",
  "properties": {
    "username": {
      "type": "string",
      "description": "你的学号，会用这个学号的统一认证平台账号发送请求。"
    },
    "password": {
      "type": "string",
      "description": "统一认证平台密码。"
    },
    "check_interval": {
      "type": "integer",
      "default": 600,
      "minimum": 0,
      "description": "余额检查间隔时间（秒），0表示单次检查后退出。"
    },
    "alert_balance": {
      "type": "number",
      "default": 10,
      "minimum": 0,
      "description": "余额告警阈值（单位：元），可以填小数，低于此值触发通知。"
    },
    "smtp": {
      "type": "object",
      "description": "SMTP邮件服务器配置，用于发送余额告警邮件，详细信息可以到你使用的邮箱官网查询。",
      "properties": {
        "server": {
          "type": "string",
          "format": "hostname",
          "description": "SMTP服务器主机名或IP地址。如果你不知道是什么，可以尝试在域名前加上\"smtp\"，例如qq邮箱为smtp.qq.com，gmail为smtp.gmail.com。"
        },
        "port": {
          "type": "integer",
          "default": 465,
          "minimum": 1,
          "maximum": 65535,
          "description": "SMTP服务器端口号。"
        },
        "username": {
          "type": "string",
          "description": "SMTP认证用户名，一般为你的邮箱。"
        },
        "password": {
          "type": "string",
          "description": "SMTP认证密码。"
        },
        "security": {
          "type": "string",
          "enum": ["ssl", "tls", "none"],
          "description": "连接安全协议：ssl(强制SSL)、tls(STARTTLS)、none(无加密)。"
        }
      },
      "required": ["server", "port", "username", "password", "security"],
      "additionalProperties": False
    },
    "queries": {
      "type": "array",
      "minItems": 1,
      "description": "监控配置列表，每个元素对应一个宿舍的监控设置，可以添加多个宿舍。",
      "items": {
        "type": "object",
        "description": "具体的监控设置，请在下方编辑。",
        "properties": {
          "room_name": {
            "type": "string",
            "description": "房间编号,研究生0开头，本科生1开头，剩下是楼栋+宿舍号。例如，本科14栋514宿舍，编号为114514。"
          },
          "recipients": {
            "type": "array",
            "minItems": 1,
            "description": "邮件通知收件人列表。",
            "items": {
              "type": "string",
              "format": "email",
              "description": "收件人邮箱，请输入有效的电子邮件地址。"
            }
          },
          "server_chan": {
            "type": "object",
            "description": "Server酱配置，访问https://sc3.ft07.com/获取UUID和Sendkey。",
            "properties": {
              "enabled": {
                "type": "boolean",
                "description": "是否启用Server酱推送。"
              },
              "recipients": {
                "type": "array",
                "minItems": 1,
                "description": "Server酱推送收件人列表，如未启用可留空。",
                "items": {
                  "type": "object",
                  "description": "填入UUID和Sendkey，两项都必须填。",
                  "properties": {
                    "uid": {
                      "type": "string",
                      "description": "Server酱用户UID。"
                    },
                    "sendkey": {
                      "type": "string",
                      "description": "Server酱发送密钥。"
                    }
                  },
                  "required": ["uid", "sendkey"],
                  "additionalProperties": False
                }
              }
            },
            "required": ["enabled", "recipients"],
            "additionalProperties": False
          }
        },
        "required": ["room_name", "recipients", "server_chan"],
        "additionalProperties": False
      }
    }
  },
  "required": ["username", "password", "check_interval", "alert_balance", "smtp", "queries"],
  "additionalProperties": False
}


def generate_html_email(roomname, balance, min_balance):
    # 主题色 - 科技蓝
    theme_color = "#3498db"
    # 警告色 - 红色
    alert_color = "#e74c3c"

    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UESTC-Energyfy 余额告警通知</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; color: #333; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 20px auto; background-color: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden;">
        <!-- 头部 -->
        <div style="background-color: {theme_color}; padding: 25px; text-align: center;">
            <h1 style="color: #fff; margin: 0; font-size: 24px; font-weight: 500;">UESTC-Energyfy 余额告警通知</h1>
        </div>

        <!-- 内容区 -->
        <div style="padding: 30px;">
            <p style="font-size: 16px; margin-top: 0; line-height: 1.6;">
                尊敬的用户：<br>
                系统检测到您的宿舍 <strong style="color: {theme_color};">{roomname}</strong> 的电费余额
                <strong style="color: {alert_color};">已低于预设阈值 {min_balance} 元</strong>。
            </p>

            <!-- 余额显示 -->
            <div style="margin: 30px 0; text-align: center; padding: 25px 0; border-top: 1px solid #eee; border-bottom: 1px solid #eee;">
                <p style="font-size: 15px; color: #777; margin: 0 0 10px;">当前电费余额</p>
                <div style="font-size: 48px; font-weight: 700; color: {alert_color}; line-height: 1.2;">
                    {balance} <span style="font-size: 24px;">元</span>
                </div>
            </div>

            <!-- 提示信息 -->
            <div style="background-color: #f9f9f9; padding: 20px; border-radius: 6px; margin: 25px 0;">
                <p style="font-size: 15px; margin: 0; color: #555; line-height: 1.6;">
                    ⚠️ 为避免影响正常用电，请及时充值。<br>
                </p>
            </div>

            <!-- 操作按钮 -->
            <div style="text-align: center; margin: 30px 0 20px;">
                <a href="https://eportal.uestc.edu.cn/qljfwapp/sys/lwUestcDormElecPrepaid/index.do"  rel="noreferrer"
                   style="background-color: {theme_color}; 
                          color: #fff; 
                          text-decoration: none; 
                          padding: 14px 35px; 
                          border-radius: 4px; 
                          font-weight: 500; 
                          font-size: 16px;
                          display: inline-block;
                          transition: background-color 0.2s;">
                    立即充值
                </a>
            </div>

            <!-- 联系信息 -->
            <p style="font-size: 14px; color: #777; text-align: center; margin: 20px 0 0;">
                如有疑问，别有疑问。
            </p>
        </div>

        <!-- 页脚 -->
        <div style="background-color: #f5f5f5; padding: 20px; text-align: center; font-size: 13px; color: #999; border-top: 1px solid #eee;">
            <p style="margin: 5px 0;">本邮件为系统自动发送，请勿直接回复</p>
            <p style="margin: 5px 0;">UESTC-Energyfy &copy; {datetime.datetime.now().year}</p>
        </div>
    </div>
</body>
</html>
    """
    return html_content

def generate_text_email(roomname, balance, min_balance):
    text_content = f"""
UESTC-Energyfy 余额告警通知
========================================

尊敬的 {roomname} 宿舍用户：

系统检测到您的宿舍电费余额已低于预设阈值 {min_balance} 元。

当前电费余额：{balance} 元

----------------------------------------
[重要提示]
为避免影响正常用电，请及时充值。
----------------------------------------

立即充值：
请访问：https://eportal.uestc.edu.cn/qljfwapp/sys/lwUestcDormElecPrepaid/index.do

如有疑问，别有疑问。。

========================================
本邮件为系统自动发送，请勿直接回复
UESTC-Energyfy © {datetime.datetime.now().year}
========================================
"""
    return text_content.strip()

def generate_markdown_notification(roomname, balance, min_balance):
    markdown_content = f"""
# ⚡ UESTC-Energyfy 余额告警通知

---

## 尊敬的 {roomname} 宿舍用户

系统检测到您的宿舍电费余额 **已低于预设阈值 {min_balance} 元**。

### 🔋 当前电费余额
```diff
- {balance} 元
```

---

## ⚠️ 重要提示
> 为避免影响正常用电，请及时充值。  

---

## 🚀 立即充值
[点击进入充值页面](https://eportal.uestc.edu.cn/qljfwapp/sys/lwUestcDormElecPrepaid/index.do)


---

UESTC-Energyfy © {datetime.datetime.now().year}
"""
    return markdown_content.strip()