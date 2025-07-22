import os
import json
import re
import platform
import sys
from pathlib import Path
import jsonschema
from jsonschema import validate, Draft7Validator


class ConfigReader:
    # 内嵌的默认 Schema
    _DEFAULT_SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Energyfy Config Schema",
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "description": "你的学号，会用这个学号的统一认证平台账号发送请求"
            },
            "password": {
                "type": "string",
                "description": "统一认证平台密码"
            },
            "check_interval": {
                "type": "integer",
                "minimum": 0,
                "description": "余额检查间隔时间（秒），0表示单次检查后退出"
            },
            "alert_balance": {
                "type": "number",
                "minimum": 0,
                "description": "余额告警阈值（单位：元），可以填小数，低于此值触发通知"
            },
            "smtp": {
                "type": "object",
                "description": "SMTP邮件服务器配置，用于发送余额告警邮件",
                "properties": {
                    "server": {
                        "type": "string",
                        "format": "hostname",
                        "description": "SMTP服务器主机名或IP地址"
                    },
                    "port": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 65535,
                        "description": "SMTP服务器端口号"
                    },
                    "username": {
                        "type": "string",
                        "description": "SMTP认证用户名"
                    },
                    "password": {
                        "type": "string",
                        "description": "SMTP认证密码"
                    },
                    "security": {
                        "type": "string",
                        "enum": ["ssl", "tls", "none"],
                        "description": "连接安全协议：ssl(强制SSL)、tls(STARTTLS)、none(无加密)"
                    }
                },
                "required": ["server", "port", "username", "password", "security"],
                "additionalProperties": False
            },
            "queries": {
                "type": "array",
                "minItems": 1,
                "description": "监控配置列表，每个元素对应一个宿舍的监控设置",
                "items": {
                    "type": "object",
                    "description": "具体的监控设置，请在下方编辑",
                    "properties": {
                        "room_name": {
                            "type": "string",
                            "description": "房间编号,研究生0开头，本科生1开头，剩下是楼栋+宿舍号。"
                        },
                        "recipients": {
                            "type": "array",
                            "minItems": 1,
                            "description": "邮件通知收件人列表",
                            "items": {
                                "type": "string",
                                "format": "email",
                                "description": "有效的电子邮件地址"
                            }
                        },
                        "server_chan": {
                            "type": "object",
                            "description": "Server酱配置，详情请访问https://sc3.ft07.com/",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "description": "是否启用Server酱推送"
                                },
                                "recipients": {
                                    "type": "array",
                                    "minItems": 1,
                                    "description": "Server酱推送收件人列表，如未启用可留空",
                                    "items": {
                                        "type": "object",
                                        "description": "两项都必须填",
                                        "properties": {
                                            "uid": {
                                                "type": "string",
                                                "description": "Server酱用户UID"
                                            },
                                            "sendkey": {
                                                "type": "string",
                                                "description": "Server酱发送密钥"
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

    def __init__(self, config_path=None):
        """
        初始化配置读取器
        :param config_path: 可选的配置文件路径
            默认:
                Windows: %APPDATA%/Energyfy/configs/active
                Linux/Unix: ~/.config/Energyfy/configs/active
            指定路径: 跳过符号链接检查，使用内嵌Schema验证
        """
        self.config = None
        self.schema = None
        self.is_custom_config = config_path is not None

        # 确定配置文件路径
        if config_path is None:
            if platform.system() == "Windows":
                appdata = os.getenv('APPDATA')
                if not appdata:
                    raise RuntimeError("无法获取 %APPDATA% 环境变量")
                config_path = Path(appdata) / "Energyfy" / "configs" / "active"
            else:  # Linux/Unix/Mac
                home = Path.home()
                config_path = home / ".config" / "Energyfy" / "configs" / "active"

        self.config_path = Path(config_path)
        self._load_config()
        self._load_schema()
        self.validate()

    def _load_config(self):
        """加载并解析JSON配置文件"""
        # 检查文件是否存在
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {self.config_path}\n"
                "请确保路径正确且文件已创建"
            )

        # 对于默认配置路径，检查是否为符号链接
        if not self.is_custom_config and not self.config_path.is_symlink():
            print(
                f"警告: {self.config_path} 不是符号链接，"
                "建议使用符号链接指向实际配置文件",
                file=sys.stderr
            )

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except json.JSONDecodeError as e:
            # 提供更友好的错误位置信息
            line, col = self._find_error_position(e.doc, e.pos)
            raise RuntimeError(
                f"配置文件格式错误: {self.config_path}\n"
                f"错误位置: 行 {line} 列 {col}\n"
                f"错误信息: {e.msg}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"读取配置文件失败: {self.config_path}\n"
                f"错误原因: {str(e)}"
            ) from e

    def _find_error_position(self, doc, pos):
        """计算JSON解码错误的行号和列号"""
        if pos is None or doc is None:
            return 1, 1

        # 计算行号和列号
        line = doc.count('\n', 0, pos) + 1
        col = pos - doc.rfind('\n', 0, pos)
        return line, col

    def _load_schema(self):
        """加载JSON Schema进行验证"""
        # 对于自定义配置路径，使用内嵌Schema
        if self.is_custom_config:
            self.schema = self._DEFAULT_SCHEMA
            return

        # 对于默认配置路径，从文件加载Schema
        schema_path = self.config_path.parent.parent / "schema.json"

        # 检查schema文件是否存在
        if not schema_path.exists():
            print(
                f"警告: Schema文件不存在: {schema_path}\n"
                "将使用内嵌Schema进行验证",
                file=sys.stderr
            )
            self.schema = self._DEFAULT_SCHEMA
            return

        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                self.schema = json.load(f)
        except json.JSONDecodeError as e:
            print(
                f"警告: Schema文件格式错误: {schema_path}\n"
                f"错误位置: 行 {e.lineno} 列 {e.colno}\n"
                f"错误信息: {e.msg}\n"
                "将使用内嵌Schema进行验证",
                file=sys.stderr
            )
            self.schema = self._DEFAULT_SCHEMA
        except Exception as e:
            print(
                f"警告: 读取Schema文件失败: {schema_path}\n"
                f"错误原因: {str(e)}\n"
                "将使用内嵌Schema进行验证",
                file=sys.stderr
            )
            self.schema = self._DEFAULT_SCHEMA

    def get(self, key_path, default=None):
        """
        使用点分路径获取配置值
        :param key_path: 点分路径字符串 (e.g. "smtp.server")
        :param default: 找不到配置时的默认值
        :return: 配置值或默认值
        """
        if not self.config:
            return default

        keys = key_path.split('.')
        current = self.config

        try:
            for key in keys:
                # 尝试处理数组索引
                if isinstance(current, list) and key.isdigit():
                    index = int(key)
                    if index >= len(current):
                        return default
                    current = current[index]
                elif isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current
        except (KeyError, IndexError, TypeError):
            return default

    def validate(self):
        """使用JSON Schema验证配置"""
        if not self.schema:
            raise RuntimeError("无法加载JSON Schema进行验证")

        # 创建自定义格式检查器
        format_checker = jsonschema.FormatChecker()

        # 添加邮箱格式验证
        @format_checker.checks("email")
        def validate_email(instance):
            if not isinstance(instance, str):
                return False
            # 更严格的邮箱格式正则表达式
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return re.match(pattern, instance) is not None

        # 添加主机名格式验证
        @format_checker.checks("hostname")
        def validate_hostname(instance):
            if not isinstance(instance, str):
                return False
            # 主机名格式验证 (RFC 1123)
            pattern = r'^[a-zA-Z0-9-]{1,63}(\.[a-zA-Z0-9-]{1,63})*$'
            return re.match(pattern, instance) is not None

        # 验证配置
        try:
            # 使用更详细的验证器
            validator = Draft7Validator(
                self.schema,
                format_checker=format_checker
            )

            # 收集所有错误
            errors = sorted(validator.iter_errors(self.config), key=lambda e: e.path)

            if errors:
                error_messages = []
                for error in errors:
                    # 构建详细的错误路径
                    path = self._format_error_path(error.path)

                    # 添加错误消息
                    message = f"{path}: {error.message}"

                    # 添加上下文信息
                    context = self._get_error_context(error)
                    if context:
                        message += f" | {context}"

                    error_messages.append(message)

                raise ValueError(
                    "配置验证失败，发现以下错误:\n" +
                    "\n".join(error_messages)
                )

            return True

        except jsonschema.exceptions.SchemaError as e:
            raise ValueError(
                f"Schema错误: {e.message}\n"
                "请检查Schema文件是否正确"
            ) from e

    def _format_error_path(self, path):
        """格式化错误路径为易读形式"""
        if not path:
            return "根对象"

        parts = []
        for part in path:
            if isinstance(part, int):
                parts.append(f"[{part}]")
            else:
                if parts:
                    parts.append(f".{part}")
                else:
                    parts.append(str(part))

        return "".join(parts)

    def _get_error_context(self, error):
        """获取错误上下文信息"""
        # 枚举错误
        if "enum" in error.schema:
            options = ", ".join(map(str, error.schema["enum"]))
            return f"有效选项: {options}"

        # 范围错误
        if "minimum" in error.schema and "maximum" in error.schema:
            min_val = error.schema["minimum"]
            max_val = error.schema["maximum"]
            return f"有效范围: {min_val} - {max_val}"

        # 类型错误
        if "type" in error.schema:
            expected = error.schema["type"]
            if isinstance(expected, list):
                expected = "或".join(expected)
            return f"期望类型: {expected}"

        # 格式错误
        if "format" in error.schema:
            return f"期望格式: {error.schema['format']}"

        return ""

    def __str__(self):
        """返回配置摘要信息"""
        if not self.config:
            return "未加载配置"

        summary = f"配置文件: {self.config_path}\n"
        summary += f"用户名: {self.get('username', '未设置')}\n"
        summary += f"检查间隔: {self.get('check_interval', '未设置')}秒\n"
        summary += f"告警阈值: {self.get('alert_balance', '未设置')}元\n"

        queries = self.get('queries', [])
        summary += f"监控房间数: {len(queries)}\n"

        if queries:
            summary += "房间列表:\n"
            for i, query in enumerate(queries):
                room = query.get('room_name', '未知房间')
                recipients = len(query.get('recipients', []))
                summary += f"  {i + 1}. {room} (收件人: {recipients})\n"

        return summary


# 使用示例
if __name__ == "__main__":
    try:
        # 使用默认配置
        print("正在加载默认配置文件...")
        default_config = ConfigReader()
        print(f"✅ 默认配置文件加载成功: {default_config.config_path}")
        print(default_config)

        # 使用自定义配置
        custom_path = input("\n输入自定义配置文件路径(留空跳过): ").strip()
        if custom_path:
            print(f"正在加载自定义配置文件: {custom_path}")
            custom_config = ConfigReader(config_path=custom_path)
            print(f"✅ 自定义配置文件加载成功")
            print(custom_config)

        print("\n✅ 所有配置验证通过")

    except FileNotFoundError as e:
        print(f"❌ 文件未找到: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"❌ 配置验证失败: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"❌ 运行时错误: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 未知错误: {str(e)}", file=sys.stderr)
        sys.exit(1)
